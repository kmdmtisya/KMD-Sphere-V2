import 'package:decimal/decimal.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/input/decimal_input.dart';
import 'package:wealthsphere_app/features/calculator/domain/forecast_input_limits.dart';
import 'package:wealthsphere_app/features/goals/application/goal_form.dart';
import 'package:wealthsphere_app/features/goals/data/goal_repository.dart';
import 'package:wealthsphere_app/features/goals/domain/goal_models.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';

import '../../helpers/demo_overrides.dart';

final DateTime today = DateTime(2026, 10, 9);
final DecimalInput en = DecimalInput('en');

GoalDraft draft({
  String name = 'Car',
  String target = '20000',
  DateTime? date,
  String contribution = '300',
  String base = '5',
  String conservative = '',
  String growth = '',
  String contributionGrowth = '',
  String inflation = '',
  String fee = '',
}) => GoalDraft(
  name: name,
  target: target,
  targetDate: date ?? DateTime(2028, 1, 1),
  contribution: contribution,
  baseReturn: base,
  conservativeReturn: conservative,
  growthReturn: growth,
  contributionGrowth: contributionGrowth,
  inflation: inflation,
  annualFee: fee,
);

GoalValidation check(GoalDraft d, {Iterable<String> others = const []}) =>
    validateGoal(d, today: today, input: en, otherNames: others);

void main() {
  group('validateGoal', () {
    test('accepts a valid goal and parses it exactly', () {
      final r = check(
        draft(
          conservative: '3',
          growth: '7',
          contributionGrowth: '2',
          inflation: '2.5',
          fee: '0.5',
        ),
      );
      expect(r.isValid, isTrue, reason: '${r.issues}');
      final g = r.value!;
      expect(g.name, 'Car');
      expect(g.target.amount, Decimal.parse('20000'));
      expect(g.target.currencyCode, 'USD');
      expect(g.assumptions.contribution.amount, Decimal.parse('300'));
      expect(g.assumptions.baseReturnPercent, Decimal.parse('5'));
      expect(g.assumptions.conservativeReturnPercent, Decimal.parse('3'));
      expect(g.assumptions.growthReturnPercent, Decimal.parse('7'));
      expect(g.assumptions.inflationPercent, Decimal.parse('2.5'));
      expect(g.assumptions.annualFeePercent, Decimal.parse('0.5'));
    });

    test('optional fields left blank become zero or none', () {
      final g = check(draft()).value!;
      expect(g.assumptions.conservativeReturnPercent, isNull);
      expect(g.assumptions.growthReturnPercent, isNull);
      expect(g.assumptions.contributionGrowthPercent, Decimal.zero);
      expect(g.assumptions.inflationPercent, Decimal.zero);
      expect(g.assumptions.annualFeePercent, Decimal.zero);
    });

    test('a blank form lists every required field', () {
      final r = check(const GoalDraft());
      expect(r.issues.keys.toSet(), {
        GoalField.name,
        GoalField.target,
        GoalField.targetDate,
        GoalField.contribution,
        GoalField.baseReturn,
      });
      expect(r.value, isNull);
    });

    test('no return rate is pre-filled or suggested', () {
      const empty = GoalDraft();
      expect(empty.baseReturn, isEmpty);
      expect(empty.conservativeReturn, isEmpty);
      expect(empty.growthReturn, isEmpty);
    });

    test(
      'the name is trimmed, 1 to 100 characters and unique ignoring case',
      () {
        expect(
          check(draft(name: '   ')).issues[GoalField.name]!.kind,
          GoalIssueKind.nameRequired,
        );
        expect(
          check(draft(name: 'x' * 101)).issues[GoalField.name]!.kind,
          GoalIssueKind.nameTooLong,
        );
        expect(check(draft(name: 'x' * 100)).isValid, isTrue);
        expect(check(draft(name: '  Car  ')).value!.name, 'Car');
        expect(
          check(
            draft(name: 'car'),
            others: ['Car'],
          ).issues[GoalField.name]!.kind,
          GoalIssueKind.nameTaken,
        );
      },
    );

    test('the target is 0.01 to 10 billion with at most 2 decimals', () {
      IssueKind? kind(String t) =>
          check(draft(target: t)).issues[GoalField.target]?.input?.kind;
      expect(kind('0'), IssueKind.tooLow);
      expect(kind('0.01'), isNull);
      expect(kind('10000000000'), isNull);
      expect(kind('10000000001'), IssueKind.tooHigh);
      expect(kind('100.123'), IssueKind.tooManyDecimals);
      expect(kind('abc'), IssueKind.invalid);
      expect(kind(''), IssueKind.required);
    });

    test('the contribution may be zero but not above the limit', () {
      IssueKind? kind(String t) =>
          check(draft(contribution: t))
              .issues[GoalField.contribution]
              ?.input
              ?.kind;
      expect(kind('0'), isNull);
      expect(kind('10000000'), isNull);
      expect(kind('10000001'), IssueKind.tooHigh);
      expect(kind('-1'), IssueKind.tooLow);
    });

    test('return rates may be negative within -20 to 50', () {
      IssueKind? kind(String t) =>
          check(draft(base: t)).issues[GoalField.baseReturn]?.input?.kind;
      expect(kind('-20'), isNull);
      expect(kind('-20.01'), IssueKind.tooLow);
      expect(kind('50'), isNull);
      expect(kind('50.01'), IssueKind.tooHigh);
    });

    test('conservative may not exceed base and growth may not be below it', () {
      final bad = check(draft(base: '5', conservative: '6', growth: '4'));
      expect(
        bad.issues[GoalField.conservativeReturn]!.input!.kind,
        IssueKind.conservativeAboveBase,
      );
      expect(
        bad.issues[GoalField.growthReturn]!.input!.kind,
        IssueKind.growthBelowBase,
      );
      expect(
        check(draft(base: '5', conservative: '5', growth: '5')).isValid,
        isTrue,
      );
    });

    test('inflation, fee and contribution growth use the forecast limits', () {
      expect(
        check(draft(inflation: '30.01')).issues
            .containsKey(GoalField.inflation),
        isTrue,
      );
      expect(
        check(draft(fee: '5.01')).issues.containsKey(GoalField.annualFee),
        isTrue,
      );
      expect(
        check(draft(contributionGrowth: '20.01')).issues
            .containsKey(GoalField.contributionGrowth),
        isTrue,
      );
      expect(
        check(draft(inflation: '30', fee: '5', contributionGrowth: '20'))
            .isValid,
        isTrue,
      );
    });

    test('the date must be after today and at most 60 years ahead', () {
      GoalIssueKind? kind(DateTime d) =>
          check(draft(date: d)).issues[GoalField.targetDate]?.kind;
      expect(kind(DateTime(2026, 10, 9)), GoalIssueKind.datePast);
      expect(kind(DateTime(2026, 10, 8)), GoalIssueKind.datePast);
      expect(kind(DateTime(2026, 10, 10)), isNull);
      expect(kind(DateTime(2086, 10, 9)), isNull);
      expect(kind(DateTime(2086, 10, 10)), GoalIssueKind.dateTooFar);
    });

    test('numbers follow the locale decimal separator', () {
      final de = DecimalInput('de');
      final r = validateGoal(
        draft(target: '20000,50', base: '5,5'),
        today: today,
        input: de,
      );
      expect(r.isValid, isTrue, reason: '${r.issues}');
      expect(r.value!.target.amount, Decimal.parse('20000.5'));
      expect(r.value!.assumptions.baseReturnPercent, Decimal.parse('5.5'));
      expect(
        validateGoal(
          draft(target: '20000.50'),
          today: today,
          input: de,
        ).issues.containsKey(GoalField.target),
        isTrue,
        reason: 'a dot is not the decimal separator in German',
      );
    });

    test('a draft built from a goal round-trips', () {
      final g = check(draft(conservative: '3', growth: '7', inflation: '2.5'))
          .value!;
      final goal = Goal(
        id: 'x',
        name: g.name,
        type: g.type,
        target: g.target,
        targetDate: g.targetDate,
        targetInTodaysMoney: g.targetInTodaysMoney,
        assumptions: g.assumptions,
      );
      final again = validateGoal(
        GoalDraft.from(goal, en),
        today: today,
        input: en,
      );
      expect(again.isValid, isTrue, reason: '${again.issues}');
      expect(again.value!.target.amount, g.target.amount);
      expect(again.value!.assumptions.growthReturnPercent, Decimal.parse('7'));
    });
  });

  group('GoalLimits', () {
    test('share the forecast limits with the calculator', () {
      expect(
        GoalLimits.of(GoalField.baseReturn),
        same(ForecastInputLimits.returnRate),
      );
      expect(
        GoalLimits.of(GoalField.inflation),
        same(ForecastInputLimits.inflation),
      );
      expect(
        GoalLimits.of(GoalField.annualFee),
        same(ForecastInputLimits.annualFee),
      );
      expect(
        GoalLimits.of(GoalField.contribution),
        same(ForecastInputLimits.monthlyContribution),
      );
    });

    test('name and date have no numeric limit', () {
      expect(() => GoalLimits.of(GoalField.name), throwsArgumentError);
      expect(() => GoalLimits.of(GoalField.targetDate), throwsArgumentError);
    });
  });

  group('models', () {
    test('goal types round-trip their API names and reject unknown ones', () {
      for (final t in GoalType.values) {
        expect(GoalType.parse(t.apiName), t);
      }
      expect(() => GoalType.parse('lottery'), throwsFormatException);
    });
  });

  group('DemoGoalRepository', () {
    late ProviderContainer container;
    late GoalRepository repo;

    setUp(() {
      container = ProviderContainer(overrides: demoOverrides());
      addTearDown(container.dispose);
      repo = container.read(goalRepositoryProvider);
    });

    GoalInput input(String name) => check(draft(name: name)).value!;

    test(
      'loads the demo goals, ordered by target date, with figures',
      () async {
        final all = await repo.goals();
        final dates = all.map((e) => e.goal.targetDate).toList();
        expect(dates, [...dates]..sort());
        expect(all.map((e) => e.goal.id).toSet(), {
          'g-home',
          'g-edu',
          'g-ret',
          'g-trip',
        });
        expect(all.every((e) => e.figures != null), isTrue);
        final trip = all.firstWhere((e) => e.goal.id == 'g-trip');
        expect(trip.figures!.status, GoalProgressStatus.behind);
        expect(trip.figures!.notice, contains('estimates'));
      },
    );

    test('statuses agree with the base scenario in the fixture', () async {
      for (final e in await repo.goals()) {
        final base = e.figures!.scenarios.firstWhere((s) => s.kind == 'base');
        expect(
          e.figures!.status == GoalProgressStatus.onTrack,
          base.reachesTarget,
          reason: e.goal.id,
        );
      }
    });

    test('a new goal has no figures and appears in the list', () async {
      final created = await repo.create(input('Car'));
      expect(created.figures, isNull);
      expect(created.goal.name, 'Car');
      expect(await repo.goals(), hasLength(5));
      expect((await repo.goal(created.goal.id)).goal.name, 'Car');
    });

    test('changing a goal drops its stale figures', () async {
      final updated = await repo.update('g-home', input('Home deposit v2'));
      expect(updated.figures, isNull);
      expect((await repo.goal('g-home')).goal.name, 'Home deposit v2');
      expect(await repo.goals(), hasLength(4));
    });

    test('names stay unique, ignoring case', () async {
      await expectLater(
        repo.create(input('home DEPOSIT')),
        throwsA(
          isA<GoalRuleException>().having(
            (e) => e.rule,
            'rule',
            GoalRule.nameTaken,
          ),
        ),
      );
      // A goal may keep its own name.
      await repo.update('g-home', input('Home deposit'));
    });

    test('there is a limit of 50 goals', () async {
      for (var i = 0; i < maxGoals - 4; i++) {
        await repo.create(input('Goal $i'));
      }
      await expectLater(
        repo.create(input('One too many')),
        throwsA(
          isA<GoalRuleException>().having(
            (e) => e.rule,
            'rule',
            GoalRule.tooMany,
          ),
        ),
      );
    });

    test('an unknown goal is reported, not invented', () async {
      await expectLater(
        repo.goal('nope'),
        throwsA(
          isA<GoalRuleException>().having(
            (e) => e.rule,
            'rule',
            GoalRule.notFound,
          ),
        ),
      );
      await expectLater(
        repo.update('nope', input('X')),
        throwsA(
          isA<GoalRuleException>().having(
            (e) => e.rule,
            'rule',
            GoalRule.notFound,
          ),
        ),
      );
    });
  });
}

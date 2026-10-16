import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/network/asset_class_names.dart';
import 'package:wealthsphere_app/features/forecast/domain/forecast_models.dart';
import 'package:wealthsphere_app/features/goals/application/goal_form.dart';
import 'package:wealthsphere_app/features/goals/data/goal_repository.dart';
import 'package:wealthsphere_app/features/goals/data/live_goal_repository.dart';
import 'package:wealthsphere_app/features/goals/domain/goal_models.dart';
import 'package:wealthsphere_app/features/goals/presentation/goals_screen.dart';
import 'package:wealthsphere_app/features/more/data/live_more_repository.dart';
import 'package:wealthsphere_app/features/more/data/more_repository.dart';
import 'package:wealthsphere_app/features/more/presentation/income_screen.dart';
import 'package:wealthsphere_app/features/more/presentation/net_worth_screen.dart';
import 'package:wealthsphere_app/features/transactions/domain/ledger_entry.dart';
import 'package:wealthsphere_app/shared/design_system/components/transaction_tile.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/money.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/fake_api.dart';
import '../../helpers/pump_app.dart';

const notice =
    'Goal status and dates are estimates based on the assumptions shown. They '
    'are not guaranteed.';

Map<String, Object?> goalJson(String id, String name, String date) => {
  'id': id,
  'name': name,
  'goal_type': 'house_deposit',
  'target': usd('50000.00'),
  'target_date': date,
  'target_in_todays_money': false,
  'portfolio_id': 'p1',
  'assumptions': {
    'contribution': usd('500.00'),
    'contribution_frequency': 'monthly',
    'contribution_growth_percent': '0',
    'inflation_percent': '2.5',
    'annual_fee_percent': '0.5',
    'compounding_frequency': 'monthly',
    'returns': {'base': '6.00', 'conservative': null, 'growth': null},
  },
};

Map<String, Object?> progressJson(String id, {String status = 'on_track'}) => {
  'goal_id': id,
  'status': status,
  'reached': false,
  'overdue': false,
  'progress_percent': '42.10',
  'current_value': usd('21050.00'),
  'gap': usd('28950.00'),
  'months_left': 30,
  'scenarios': [
    {
      'kind': 'base',
      'annual_return_percent': '6.00',
      'projected_value': usd('51000.00'),
      'projected_value_real': usd('48000.00'),
      'reaches_target': true,
    },
  ],
  'required_contribution': null,
  'estimated_completion': '2029-02-01',
  'value_complete': true,
  'value_as_of': '2026-10-12T09:00:00Z',
  'notice': notice,
};

GoalInput input(String name) => GoalInput(
  name: name,
  type: GoalType.houseDeposit,
  target: Money(Decimal.parse('50000.00'), 'USD'),
  targetDate: DateTime(2029, 6, 1),
  targetInTodaysMoney: false,
  portfolioId: 'p1',
  assumptions: GoalAssumptions(
    contribution: Money(Decimal.parse('500'), 'USD'),
    contributionFrequency: Frequency.monthly,
    contributionGrowthPercent: Decimal.zero,
    inflationPercent: Decimal.parse('2.5'),
    annualFeePercent: Decimal.parse('0.5'),
    baseReturnPercent: Decimal.parse('6'),
  ),
);

void main() {
  late FakeApi api;
  late LiveGoalRepository goals;

  setUp(() {
    api = FakeApi();
    goals = LiveGoalRepository(api.dio());
  });

  group('goals', () {
    test('each goal carries the server figures and notice', () async {
      api
        ..json('GET /api/v1/goals', [
          goalJson('g2', 'Later', '2031-01-01'),
          goalJson('g1', 'House', '2029-06-01'),
        ])
        ..json('GET /api/v1/goals/g1/progress', progressJson('g1'))
        ..json(
          'GET /api/v1/goals/g2/progress',
          progressJson('g2', status: 'behind'),
        );
      final list = await goals.goals();
      expect([for (final e in list) e.goal.name], ['House', 'Later']);
      final house = list.first.figures!;
      expect(house.progressPercent, Decimal.parse('42.10'));
      expect(house.notice, notice);
      expect(house.estimatedCompletion, DateTime(2029, 2, 1));
    });

    test('a goal the server cannot measure is shown without figures', () async {
      api
        ..json('GET /api/v1/goals', [goalJson('g1', 'House', '2029-06-01')])
        ..json('GET /api/v1/goals/g1/progress', {
          'title': 'Validation failed',
          'status': 422,
        }, status: 422);
      final list = await goals.goals();
      expect(list.single.figures, isNull);
    });

    test('create sends amounts and rates as strings', () async {
      api
        ..json(
          'POST /api/v1/goals',
          goalJson('g9', 'Car', '2029-06-01'),
          status: 201,
        )
        ..json('GET /api/v1/goals/g9/progress', progressJson('g9'));
      await goals.create(input('Car'));
      final body =
          api.callsTo('POST', '/api/v1/goals').single.body!
              as Map<String, Object?>;
      expect(body['goal_type'], 'house_deposit');
      expect(body['target_date'], '2029-06-01');
      final a = body['assumptions']! as Map<String, Object?>;
      expect(a['inflation_percent'], '2.5');
      expect(a['returns'], {'base': '6'});
    });

    test('a duplicate name and the goal limit are told apart', () async {
      api.json('POST /api/v1/goals', {
        'status': 409,
        'detail': 'You already have a goal with this name.',
      }, status: 409);
      await expectLater(
        goals.create(input('Car')),
        throwsA(
          isA<GoalRuleException>().having(
            (e) => e.rule,
            'rule',
            GoalRule.nameTaken,
          ),
        ),
      );
      api.json('POST /api/v1/goals', {
        'status': 409,
        'detail': 'A user can have at most 50 goals.',
      }, status: 409);
      await expectLater(
        goals.create(input('Car')),
        throwsA(
          isA<GoalRuleException>().having(
            (e) => e.rule,
            'rule',
            GoalRule.tooMany,
          ),
        ),
      );
    });

    test('an unknown goal is not found', () async {
      await expectLater(
        goals.goal('nope'),
        throwsA(
          isA<GoalRuleException>().having(
            (e) => e.rule,
            'rule',
            GoalRule.notFound,
          ),
        ),
      );
    });

    test('update patches the goal and returns fresh figures', () async {
      api
        ..json('PATCH /api/v1/goals/g1', goalJson('g1', 'House+', '2029-06-01'))
        ..json('GET /api/v1/goals/g1/progress', progressJson('g1'));
      final e = await goals.update('g1', input('House+'));
      expect(e.goal.name, 'House+');
      expect(e.figures, isNotNull);
    });

    test(
      'a goal read on its own carries the version the server sent',
      () async {
        api
          ..on(
            'GET /api/v1/goals/g1',
            (_) => WithHeaders(200, goalJson('g1', 'House', '2029-06-01'), {
              'etag': '"v1"',
            }),
          )
          ..json('GET /api/v1/goals/g1/progress', progressJson('g1'));
        final e = await goals.goal('g1');
        expect(e.goal.etag, '"v1"');
      },
    );

    test('update sends the version being edited as If-Match', () async {
      api
        ..json('PATCH /api/v1/goals/g1', goalJson('g1', 'House+', '2029-06-01'))
        ..json('GET /api/v1/goals/g1/progress', progressJson('g1'));
      await goals.update('g1', input('House+'), ifMatch: '"v1"');
      expect(
        api.callsTo('PATCH', '/api/v1/goals/g1').single.header('if-match'),
        '"v1"',
      );
      await goals.update('g1', input('House+'));
      expect(
        api.callsTo('PATCH', '/api/v1/goals/g1').last.header('if-match'),
        isNull,
      );
    });

    test('a goal changed elsewhere is refused with its own rule', () async {
      api.json('PATCH /api/v1/goals/g1', {
        'title': 'Conflict',
        'status': 409,
        'detail': 'This record was changed somewhere else. Reload it and try your change again.',
      }, status: 409);
      await expectLater(
        goals.update('g1', input('House+'), ifMatch: '"old"'),
        throwsA(
          isA<GoalRuleException>().having(
            (x) => x.rule,
            'rule',
            GoalRule.changedElsewhere,
          ),
        ),
      );
    });
  });

  group('net worth and income', () {
    late LiveMoreRepository more;

    setUp(() {
      final dio = api.dio();
      more = LiveMoreRepository(
        dio,
        AssetClassNames(dio),
        () async => const [
          PortfolioRef(id: 'p1', name: 'Retirement', baseCurrency: 'USD'),
        ],
        () async => [
          LedgerEntry(
            id: 't1',
            portfolioId: 'p1',
            kind: TransactionKind.dividend,
            tradeDate: DateTime(2026, 9, 1),
            gross: Money(Decimal.parse('12.50'), 'USD'),
            source: 'manual',
            createdAt: DateTime.utc(2026, 9, 1),
            assetName: 'Acme',
          ),
          LedgerEntry(
            id: 't2',
            portfolioId: 'p1',
            kind: TransactionKind.buy,
            tradeDate: DateTime(2026, 9, 2),
            gross: Money(Decimal.parse('100.00'), 'USD'),
            source: 'manual',
            createdAt: DateTime.utc(2026, 9, 2),
          ),
          LedgerEntry(
            id: 't3',
            portfolioId: 'p1',
            kind: TransactionKind.interest,
            tradeDate: DateTime(2026, 9, 3),
            gross: Money(Decimal.parse('5.00'), 'USD'),
            source: 'manual',
            createdAt: DateTime.utc(2026, 9, 3),
            reversedById: 'r3',
          ),
        ],
      );
      api
        ..json('GET /api/v1/asset-classes', [
          {'code': 'stock', 'name': 'Stocks'},
        ])
        ..json('GET /api/v1/net-worth', {
          'currency': 'USD',
          'assets': usd('15000.00'),
          'liabilities': usd('3000.00'),
          'net_worth': usd('12000.00'),
          'assets_by_class': [
            {
              'asset_class': 'stock',
              'value': usd('15000.00'),
              'share_percent': '100.00',
            },
          ],
          'liability_lines': [
            {
              'id': 'l1',
              'name': 'Car loan',
              'liability_type': 'car_loan',
              'balance': usd('3000.00'),
              'value': usd('3000.00'),
              'balance_as_of': '2026-10-01',
            },
            {
              'id': 'l2',
              'name': 'Kenyan loan',
              'liability_type': 'personal_loan',
              'balance': {'amount': '50000.00', 'currency': 'KES'},
              'value': null,
              'balance_as_of': '2026-10-01',
            },
          ],
          'freshness': {'complete': false},
          'as_of': '2026-10-12T09:00:00Z',
        })
        ..json('GET /api/v1/income/summary', {
          'currency': 'USD',
          'monthly': usd('10.00'),
          'yearly': usd('120.00'),
          'yearly_gross': usd('130.00'),
          'portfolios': [
            {
              'portfolio_id': 'p1',
              'yearly': usd('120.00'),
              'value': usd('15000.00'),
            },
          ],
          'complete': true,
          'as_of': '2026-10-12T09:00:00Z',
        });
    });

    test('net worth uses the server totals, names and shares', () async {
      final nw = await more.netWorth();
      expect(nw.netWorth.amount, Decimal.parse('12000.00'));
      expect(nw.assets.items.single.label, 'Stocks');
      expect(nw.assets.items.single.sharePercent, Decimal.parse('100.00'));
      expect(nw.liabilities.total.amount, Decimal.parse('3000.00'));
      expect(
        nw.liabilities.items.last.value.currencyCode,
        'KES',
        reason: 'unconverted: the balance as it is, not a guessed conversion',
      );
      expect(nw.complete, isFalse);
    });

    test(
      'income lists the server totals and the latest real payments',
      () async {
        final income = await more.income();
        expect(income.yearly.amount, Decimal.parse('120.00'));
        expect(income.bySource.single.label, 'Retirement');
        expect(
          income.bySource.single.sharePercent,
          isNull,
          reason: 'not computed here',
        );
        expect(
          [for (final p in income.recent) p.transactionKind],
          [TransactionKind.dividend],
          reason: 'trades and reversed entries are not income',
        );
      },
    );

    testWidgets('net worth screen says when the total is incomplete', (
      tester,
    ) async {
      await tester.pumpApp(
        const NetWorthScreen(),
        overrides: demoOverrides(
          extra: [
            liveModeOverride(),
            moreRepositoryProvider.overrideWithValue(more),
          ],
        ),
        surfaceSize: const Size(400, 1600),
      );
      expect(find.text(r'$12,000.00'), findsWidgets);
      expect(find.textContaining('may be incomplete'), findsOneWidget);
    });

    testWidgets('income screen names the kind of each payment', (tester) async {
      await tester.pumpApp(
        const IncomeScreen(),
        overrides: demoOverrides(
          extra: [
            liveModeOverride(),
            moreRepositoryProvider.overrideWithValue(more),
          ],
        ),
        surfaceSize: const Size(400, 1600),
      );
      expect(find.textContaining('Dividend'), findsWidgets);
      expect(find.text('Retirement'), findsOneWidget);
    });
  });

  testWidgets('the goals list shows the server\'s assumption disclosure', (
    tester,
  ) async {
    api
      ..json('GET /api/v1/goals', [goalJson('g1', 'House', '2029-06-01')])
      ..json('GET /api/v1/goals/g1/progress', progressJson('g1'));
    await tester.pumpApp(
      const GoalsScreen(),
      overrides: demoOverrides(
        extra: [
          liveModeOverride(),
          goalRepositoryProvider.overrideWithValue(goals),
        ],
      ),
      surfaceSize: const Size(400, 1600),
    );
    expect(find.text(notice), findsOneWidget);
    expect(find.text('House'), findsWidgets);
  });
}

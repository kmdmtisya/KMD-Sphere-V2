import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/data/json_reader.dart';
import 'package:wealthsphere_app/features/ai_wealth/doctor/application/doctor_providers.dart';
import 'package:wealthsphere_app/features/ai_wealth/doctor/data/doctor_repository.dart';
import 'package:wealthsphere_app/features/ai_wealth/doctor/domain/doctor_models.dart';
import 'package:wealthsphere_app/features/ai_wealth/doctor/presentation/doctor_screen.dart';
import 'package:wealthsphere_app/features/portfolios/application/portfolio_providers.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';
import '../../helpers/strict_tap_target.dart';

class _EmptyDoctor implements DoctorRepository {
  @override
  Future<DoctorReport> report(String portfolioId) async => DoctorReport(
    asOf: DateTime.utc(2026, 10, 9, 8),
    findings: const [],
    scenarios: const [],
  );
}

ProviderContainer containerOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));

Future<void> pumpDoctor(
  WidgetTester tester, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
  void Function(String)? onAskAi,
  List<Override>? overrides,
  double height = 5000,
}) => tester.pumpApp(
  DoctorScreen(onAskAi: onAskAi),
  themeMode: mode,
  textScale: scale,
  textDirection: dir,
  overrides: overrides ?? demoOverrides(),
  surfaceSize: Size(400, height),
);

Future<void> accessibilityChecks(WidgetTester tester) async {
  expect(tester.takeException(), isNull);
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(const StrictTapTargetGuideline()));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
}

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('DemoDoctorRepository', () {
    late ProviderContainer container;
    late DoctorRepository repo;

    setUp(() {
      container = ProviderContainer(overrides: demoOverrides());
      addTearDown(container.dispose);
      repo = container.read(doctorRepositoryProvider);
    });

    test('every portfolio has a report whose scenarios resolve', () async {
      for (final id in ['consolidated', 'p-retire', 'p-growth', 'p-income']) {
        final r = await repo.report(id);
        expect(r.findings, isNotEmpty, reason: id);
        for (final f in r.findings) {
          expect(f.facts, isNotEmpty, reason: '$id ${f.id}');
          expect(f.title, isNotEmpty);
          for (final s in f.scenarioIds) {
            expect(r.scenario(s), isNotNull, reason: '$id ${f.id} -> $s');
          }
        }
        for (final s in r.scenarios) {
          expect(s.assumptions, isNotEmpty, reason: '$id ${s.id}');
          expect(s.effect, isNotEmpty);
        }
      }
    });

    test('an unknown portfolio is an error, not an invented report', () async {
      await expectLater(repo.report('nope'), throwsA(isA<DataLoadException>()));
    });

    test('an unknown kind or severity is rejected loudly', () {
      JsonReader finding({String kind = 'concentration', String sev = 'low'}) =>
          JsonReader({
            'id': 'f',
            'kind': kind,
            'severity': sev,
            'title': 't',
            'explanation': 'e',
            'facts': <dynamic>[],
            'scenario_ids': <dynamic>[],
          });
      expect(
        DoctorFinding.fromJson(finding()).kind,
        HealthFindingKind.concentration,
      );
      expect(
        () => DoctorFinding.fromJson(finding(kind: 'luck')),
        throwsFormatException,
      );
      expect(
        () => DoctorFinding.fromJson(finding(sev: 'doom')),
        throwsFormatException,
      );
    });

    test('kinds lists each present kind once, in a stable order', () async {
      final r = await repo.report('consolidated');
      expect(r.kinds, [
        HealthFindingKind.concentration,
        HealthFindingKind.currency,
        HealthFindingKind.liquidity,
        HealthFindingKind.volatility,
      ]);
    });
  });

  group('DoctorScreen', () {
    testWidgets('overview names every finding with its severity in words', (
      tester,
    ) async {
      await pumpDoctor(tester);
      expect(find.byType(PortfolioHealthCard), findsOneWidget);
      expect(find.text('Portfolio health'), findsOneWidget);
      expect(find.text('High risk'), findsWidgets);
      expect(find.text('Medium risk'), findsWidgets);
      expect(find.text('Low risk'), findsWidgets);
      expect(find.text('DEMO'), findsWidgets);
      expect(find.textContaining('not advice'), findsWidgets);
    });

    testWidgets('type chips count the findings and filter the detail list', (
      tester,
    ) async {
      await pumpDoctor(tester);
      expect(find.widgetWithText(ChoiceChip, 'All (4)'), findsOneWidget);
      expect(
        find.widgetWithText(ChoiceChip, 'Concentration (1)'),
        findsOneWidget,
      );
      expect(find.widgetWithText(ChoiceChip, 'Currency (1)'), findsOneWidget);
      expect(find.text('The figures behind it'), findsNWidgets(4));
      await tester.tap(find.widgetWithText(ChoiceChip, 'Currency (1)'));
      await tester.pumpAndSettle();
      expect(find.text('The figures behind it'), findsOneWidget);
      expect(find.text('Outside the portfolio currency'), findsOneWidget);
      await tester.tap(find.widgetWithText(ChoiceChip, 'All (4)'));
      await tester.pumpAndSettle();
      expect(find.text('The figures behind it'), findsNWidgets(4));
    });

    testWidgets('the chip choice is announced to screen readers', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpDoctor(tester);
      await tester.tap(find.widgetWithText(ChoiceChip, 'Currency (1)'));
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel('Currency (1), Selected'), findsOneWidget);
      handle.dispose();
    });

    testWidgets('shows the figures behind a finding', (tester) async {
      await pumpDoctor(tester);
      await tester.tap(find.widgetWithText(ChoiceChip, 'Concentration (1)'));
      await tester.pumpAndSettle();
      expect(find.text('Largest holding'), findsOneWidget);
      expect(find.text('30.0%'), findsWidgets);
      expect(find.text('Demo Global Equity Fund'), findsWidgets);
    });

    testWidgets(
      'a scenario opens a sheet with assumptions and what it would mean',
      (tester) async {
        await pumpDoctor(tester);
        await tester.tap(find.widgetWithText(ChoiceChip, 'Currency (1)'));
        await tester.pumpAndSettle();
        await tester.tap(find.textContaining('weakened 10%'));
        await tester.pumpAndSettle();
        expect(find.text('Assumptions'), findsOneWidget);
        expect(find.text('What it would mean'), findsOneWidget);
        expect(
          find.textContaining('The portfolio would be worth about'),
          findsOneWidget,
        );
        expect(find.textContaining('not a forecast or advice'), findsOneWidget);
        await tester.tap(find.text('Close'));
        await tester.pumpAndSettle();
        expect(find.text('What it would mean'), findsNothing);
      },
    );

    testWidgets('follows the selected portfolio', (tester) async {
      await pumpDoctor(tester);
      containerOf(tester)
          .read(selectedPortfolioIdProvider.notifier)
          .select('p-income');
      await tester.pumpAndSettle();
      expect(find.widgetWithText(ChoiceChip, 'All (2)'), findsOneWidget);
      expect(find.widgetWithText(ChoiceChip, 'Liquidity (1)'), findsNothing);
    });

    testWidgets('a filter that no longer exists falls back to All', (
      tester,
    ) async {
      await pumpDoctor(tester);
      final c = containerOf(tester);
      c
          .read(doctorKindFilterProvider.notifier)
          .select(HealthFindingKind.liquidity);
      c.read(selectedPortfolioIdProvider.notifier).select('p-income');
      await tester.pumpAndSettle();
      expect(find.text('The figures behind it'), findsNWidgets(2));
    });

    testWidgets(
      'no findings says so without claiming the portfolio is healthy',
      (tester) async {
        await pumpDoctor(
          tester,
          overrides: demoOverrides(
            extra: [doctorRepositoryProvider.overrideWithValue(_EmptyDoctor())],
          ),
        );
        expect(
          find.text('Nothing to flag from the checks that could be run.'),
          findsOneWidget,
        );
        expect(find.text('Look closer'), findsNothing);
        expect(find.textContaining('healthy'), findsNothing);
      },
    );

    testWidgets('offers no Buy, Sell, trade or rebalance action', (
      tester,
    ) async {
      final trading = RegExp(
        r'\b(buy|sell|trade|rebalance|invest now|execute|order)\b',
        caseSensitive: false,
      );
      await pumpDoctor(tester, onAskAi: (_) {});
      Future<void> check() async {
        final labels = [
          for (final b in tester.widgetList<ButtonStyleButton>(
            find.byWidgetPredicate((w) => w is ButtonStyleButton),
          ))
            if (b.child is Text) (b.child! as Text).data ?? '',
        ];
        expect(labels.where(trading.hasMatch), isEmpty);
        expect(find.byType(FloatingActionButton), findsNothing);
      }

      await check();
      for (final label in [
        'Concentration (1)',
        'Currency (1)',
        'Liquidity (1)',
        'Volatility (1)',
      ]) {
        await tester.tap(find.widgetWithText(ChoiceChip, label));
        await tester.pumpAndSettle();
        await check();
      }
      expect(
        find.text(
          'The Portfolio Doctor only describes and illustrates. It never places trades.',
        ),
        findsOneWidget,
      );
    });

    testWidgets('Ask AI passes the portfolio being checked', (tester) async {
      final asked = <String>[];
      await pumpDoctor(tester, onAskAi: asked.add);
      await tester.tap(find.text('Ask AI about these findings'));
      expect(asked, ['consolidated']);
    });

    testWidgets('failure shows an error with retry, then recovers', (
      tester,
    ) async {
      await pumpDoctor(
        tester,
        overrides: demoOverrides(
          behavior: const DemoBehavior(
            latency: Duration.zero,
            failNextCalls: 1,
          ),
        ),
      );
      expect(find.byType(PortfolioHealthCard), findsNothing);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.byType(PortfolioHealthCard), findsOneWidget);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpDoctor(
                tester,
                mode: mode,
                scale: scale,
                dir: dir,
                onAskAi: (_) {},
                height: 9000,
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }

    testWidgets('the scenario sheet meets the accessibility guidelines at 2x', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpDoctor(tester, scale: 2.0, height: 9000);
      await tester.tap(find.widgetWithText(ChoiceChip, 'Currency (1)'));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('weakened 10%'));
      await tester.pumpAndSettle();
      await accessibilityChecks(tester);
      handle.dispose();
    });
  });

  group('Routes', () {
    testWidgets('AI Wealth opens the Portfolio Doctor and back returns', (
      tester,
    ) async {
      await pumpRouterApp(tester, initialLocation: '/ai');
      await tester.tap(find.byTooltip('Portfolio Doctor'));
      await tester.pumpAndSettle();
      expect(find.byType(DoctorScreen), findsOneWidget);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.byType(DoctorScreen), findsNothing);
    });

    testWidgets(
      'a deep link opens it, and Ask AI scopes the chat to the portfolio',
      (tester) async {
        await pumpRouterApp(
          tester,
          initialLocation: '/ai/doctor',
          surfaceSize: const Size(400, 5000),
        );
        expect(find.byType(DoctorScreen), findsOneWidget);
        await tester.tap(find.text('Ask AI about these findings'));
        await tester.pumpAndSettle();
        expect(find.byType(DoctorScreen), findsNothing);
      },
    );
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/data/json_reader.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/application/opportunity_providers.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/data/opportunity_repository.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/domain/opportunity_models.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/presentation/compare_screen.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/presentation/opportunities_screen.dart';
import 'package:wealthsphere_app/features/calculator/application/calculator_providers.dart';
import 'package:wealthsphere_app/features/calculator/domain/forecast_input_limits.dart';
import 'package:wealthsphere_app/features/calculator/presentation/calculator_screen.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';
import '../../helpers/strict_tap_target.dart';

ProviderContainer containerOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));

Future<void> pumpIdeas(
  WidgetTester tester, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
  VoidCallback? onCompare,
  VoidCallback? onSimulated,
  List<Override>? overrides,
}) => tester.pumpApp(
  OpportunitiesScreen(onCompare: onCompare, onSimulated: onSimulated),
  themeMode: mode,
  textScale: scale,
  textDirection: dir,
  overrides: overrides ?? demoOverrides(),
  surfaceSize: const Size(400, 12000),
);

List<OpportunityCard> cards(WidgetTester tester) =>
    tester.widgetList<OpportunityCard>(find.byType(OpportunityCard)).toList();

Future<void> accessibilityChecks(WidgetTester tester) async {
  expect(tester.takeException(), isNull);
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(const StrictTapTargetGuideline()));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
}

/// Taps the n-th "Compare" button (0-based) on the ideas screen.
Future<void> tapCompare(WidgetTester tester, int n) async {
  final button = find.widgetWithText(OutlinedButton, 'Compare').at(n);
  await tester.ensureVisible(button);
  await tester.pumpAndSettle();
  await tester.tap(button);
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('OpportunityList', () {
    late ProviderContainer container;
    late OpportunityList list;

    setUp(() async {
      container = ProviderContainer(overrides: demoOverrides());
      addTearDown(container.dispose);
      list = await container
          .read(opportunityRepositoryProvider)
          .opportunities();
    });

    test('loads six ideas in five categories and says they are mock', () {
      expect(list.candidates, hasLength(6));
      expect(list.categories, hasLength(5));
      expect(list.notice, contains('DEMO'));
      expect(list.notice, contains('not live'));
    });

    test('every score is the sum of its factors, each within its maximum', () {
      for (final c in list.candidates.where((c) => c.score != null)) {
        expect(c.scoreFactors, hasLength(5), reason: c.id);
        expect(
          c.scoreFactors.fold<int>(0, (a, f) => a + f.points),
          c.score,
          reason: c.id,
        );
        for (final f in c.scoreFactors) {
          expect(
            f.points,
            inInclusiveRange(0, f.max),
            reason: '${c.id} ${f.label}',
          );
          expect(f.note, isNotEmpty);
        }
        expect(c.score, inInclusiveRange(0, 100));
      }
    });

    test('an idea without evidence has no score and nothing to simulate', () {
      final none = list.byId('o-new')!;
      expect(none.evidence, isEmpty);
      expect(none.score, isNull);
      expect(none.simulation, isNull);
      expect(none.scoreFactors, isEmpty);
    });

    test('every scored idea has evidence with a provider and a time', () {
      for (final c in list.candidates.where((c) => c.score != null)) {
        expect(c.evidence, isNotEmpty, reason: c.id);
        for (final e in c.evidence) {
          expect(e.provider, isNotEmpty);
          expect(e.label, isNotEmpty);
        }
        expect(c.risks, isNotEmpty);
      }
    });

    test('all ideas describe the same attributes, in the same order', () {
      final first = list.candidates.first.attributes
          .map((a) => a.label)
          .toList();
      for (final c in list.candidates) {
        expect(c.attributes.map((a) => a.label), first, reason: c.id);
      }
    });

    test('every idea belongs to a known category', () {
      final ids = list.categories.map((c) => c.id).toSet();
      for (final c in list.candidates) {
        expect(ids, contains(c.categoryId), reason: c.id);
      }
    });

    test('inCategory filters and keeps the order', () {
      expect(inCategory(list, null), hasLength(6));
      expect(inCategory(list, 'funds').map((c) => c.id), ['o-glb', 'o-new']);
      expect(inCategory(list, 'bonds').map((c) => c.id), ['o-gov']);
      expect(inCategory(list, 'nothing'), isEmpty);
    });

    test('a score without factors is rejected', () {
      final json = JsonCandidate.minimal(score: 50);
      expect(() => OpportunityCandidate.fromJson(json), throwsFormatException);
    });
  });

  group('CompareSelection', () {
    late ProviderContainer container;
    CompareSelection notifier() =>
        container.read(compareSelectionProvider.notifier);

    setUp(() {
      container = ProviderContainer();
      addTearDown(container.dispose);
    });

    test('adds, removes and keeps the order chosen', () {
      expect(notifier().toggle('a'), isTrue);
      expect(notifier().toggle('b'), isTrue);
      expect(container.read(compareSelectionProvider), ['a', 'b']);
      expect(notifier().toggle('a'), isTrue);
      expect(container.read(compareSelectionProvider), ['b']);
    });

    test('stops at the limit and says so', () {
      for (final id in ['a', 'b', 'c']) {
        expect(notifier().toggle(id), isTrue);
      }
      expect(notifier().toggle('d'), isFalse);
      expect(container.read(compareSelectionProvider), ['a', 'b', 'c']);
      expect(maxCompare, 3);
    });

    test('clear empties it', () {
      notifier().toggle('a');
      notifier().clear();
      expect(container.read(compareSelectionProvider), isEmpty);
    });
  });

  group('simulateInCalculator', () {
    /// A [WidgetRef] on a fresh container, plus the container.
    Future<(WidgetRef, ProviderContainer)> setup(WidgetTester tester) async {
      final container = ProviderContainer(overrides: demoOverrides());
      addTearDown(container.dispose);
      late WidgetRef captured;
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: Consumer(
            builder: (context, ref, _) {
              captured = ref;
              return const SizedBox();
            },
          ),
        ),
      );
      return (captured, container);
    }

    testWidgets(
      'writes the assumptions in the user number format and marks them',
      (tester) async {
        final (ref, container) = await setup(tester);
        final list = await container.read(opportunitiesProvider.future);
        expect(simulateInCalculator(ref, list.byId('o-glb')!, 'de'), isTrue);
        final inputs = container.read(calculatorInputsProvider)!;
        expect(inputs.text(CalculatorField.annualReturn), '7');
        expect(inputs.text(CalculatorField.initialInvestment), '5000');
        expect(inputs.text(CalculatorField.annualFee), '0,12');
        expect(inputs.text(CalculatorField.years), '20');
        final prefill = container.read(calculatorPrefillProvider)!;
        expect(prefill.sourceName, 'Demo Global Index ETF');
        expect(prefill.fields, contains(CalculatorField.annualReturn));
      },
    );

    testWidgets('an idea without assumptions hands over nothing', (
      tester,
    ) async {
      final (ref, container) = await setup(tester);
      final list = await container.read(opportunitiesProvider.future);
      expect(simulateInCalculator(ref, list.byId('o-new')!, 'en'), isFalse);
      expect(container.read(calculatorInputsProvider), isNull);
      expect(container.read(calculatorPrefillProvider), isNull);
    });
  });

  group('OpportunitiesScreen', () {
    testWidgets('says the ideas are DEMO and not live, and lists them', (
      tester,
    ) async {
      await pumpIdeas(tester);
      expect(find.textContaining('not live market data'), findsOneWidget);
      expect(cards(tester), hasLength(6));
      expect(cards(tester).every((c) => c.isDemo), isTrue);
      expect(find.text('6 ideas'), findsOneWidget);
      expect(find.text('DEMO'), findsWidgets);
    });

    testWidgets(
      'every card shows risk, evidence, as-of and a not-advice note',
      (tester) async {
        await pumpIdeas(tester);
        expect(find.byType(RiskLabel), findsNWidgets(6));
        expect(find.byType(DataAsOfLabel), findsNWidgets(6));
        expect(
          find.text(
            'For research only. Not advice, and returns are never guaranteed.',
          ),
          findsNWidgets(6),
        );
        expect(find.text('Evidence'), findsNWidgets(6));
      },
    );

    testWidgets('an idea without evidence says so and offers no Simulate', (
      tester,
    ) async {
      await pumpIdeas(tester);
      expect(
        find.text('No evidence yet. Do not rely on this idea.'),
        findsOneWidget,
      );
      final noEvidence = cards(tester).singleWhere((c) => c.evidence.isEmpty);
      expect(noEvidence.score, isNull);
      expect(noEvidence.onSimulate, isNull);
      expect(find.text('Simulate'), findsNWidgets(5));
    });

    testWidgets('a score is explained by its five factors', (tester) async {
      await pumpIdeas(tester);
      await tester.tap(find.text('How this score is made').first);
      await tester.pumpAndSettle();
      expect(find.textContaining('adds five factors'), findsOneWidget);
      expect(find.textContaining('Cost: 22 of 25.'), findsOneWidget);
    });

    testWidgets('category chips filter and announce the result', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpIdeas(tester);
      await tester.tap(find.widgetWithText(ChoiceChip, 'Bonds'));
      await tester.pumpAndSettle();
      expect(cards(tester), hasLength(1));
      expect(find.text('1 idea, in Bonds'), findsOneWidget);
      expect(find.bySemanticsLabel('1 idea, in Bonds'), findsOneWidget);
      expect(find.bySemanticsLabel('Bonds, Selected'), findsOneWidget);
      await tester.tap(find.widgetWithText(ChoiceChip, 'All'));
      await tester.pumpAndSettle();
      expect(cards(tester), hasLength(6));
      handle.dispose();
    });

    testWidgets('an unknown category falls back to All', (tester) async {
      await pumpIdeas(tester);
      containerOf(tester)
          .read(opportunityCategoryProvider.notifier)
          .select('gone');
      await tester.pumpAndSettle();
      expect(cards(tester), hasLength(6));
    });

    testWidgets(
      'Research opens a sheet with what it is, risks, evidence and a close',
      (tester) async {
        await pumpIdeas(tester);
        await tester.tap(find.widgetWithText(FilledButton, 'Research').first);
        await tester.pumpAndSettle();
        expect(find.text('DEMO-GLB · Demo Global Index ETF'), findsWidgets);
        expect(find.text('What it is'), findsOneWidget);
        expect(find.text('Things to check'), findsOneWidget);
        expect(find.byType(ResearchSheet), findsOneWidget);
        await tester.tap(find.text('Close'));
        await tester.pumpAndSettle();
        expect(find.byType(ResearchSheet), findsNothing);
      },
    );

    testWidgets('Compare marks ideas, shows the bar and needs at least two', (
      tester,
    ) async {
      var opened = 0;
      await pumpIdeas(tester, onCompare: () => opened++);
      expect(find.textContaining('Compare 1 selected'), findsNothing);
      await tapCompare(tester, 0);
      expect(find.text('In comparison'), findsOneWidget);
      expect(find.text('Compare 1 selected'), findsOneWidget);
      expect(
        find.text('Choose at least two ideas to compare.'),
        findsOneWidget,
      );
      final bar = find.widgetWithText(FilledButton, 'Compare 1 selected');
      expect(tester.widget<FilledButton>(bar).onPressed, isNull);

      await tapCompare(tester, 1);
      expect(find.text('Compare 2 selected'), findsOneWidget);
      await tester.tap(find.text('Compare 2 selected'));
      expect(opened, 1);
    });

    testWidgets('a fourth idea is refused with a message', (tester) async {
      await pumpIdeas(tester, onCompare: () {});
      for (var i = 0; i < 4; i++) {
        await tapCompare(tester, i);
      }
      expect(
        find.text('You can compare up to 3 ideas at a time.'),
        findsOneWidget,
      );
      expect(containerOf(tester).read(compareSelectionProvider), hasLength(3));
    });

    testWidgets('Clear selection empties the comparison', (tester) async {
      await pumpIdeas(tester, onCompare: () {});
      await tapCompare(tester, 0);
      await tester.tap(find.text('Clear selection'));
      await tester.pumpAndSettle();
      expect(find.text('In comparison'), findsNothing);
      expect(find.textContaining('selected'), findsNothing);
    });

    testWidgets('Simulate hands the assumptions over and navigates', (
      tester,
    ) async {
      var navigated = 0;
      await pumpIdeas(tester, onSimulated: () => navigated++);
      await tester.tap(find.widgetWithText(OutlinedButton, 'Simulate').first);
      await tester.pumpAndSettle();
      expect(navigated, 1);
      expect(
        containerOf(tester).read(calculatorPrefillProvider)?.sourceName,
        'Demo Global Index ETF',
      );
    });

    testWidgets('offers no Buy, Sell, trade or invest action', (tester) async {
      final trading = RegExp(
        r'\b(buy|sell|trade|invest now|execute|order)\b',
        caseSensitive: false,
      );
      await pumpIdeas(tester, onCompare: () {});
      await tapCompare(tester, 0);
      final labels = [
        for (final b in tester.widgetList<ButtonStyleButton>(
          find.byWidgetPredicate((w) => w is ButtonStyleButton),
        ))
          if (b.child is Text) (b.child! as Text).data ?? '',
      ];
      expect(labels.where(trading.hasMatch), isEmpty);
      expect(find.byType(FloatingActionButton), findsNothing);
      expect(
        find.text(
          'WealthSphere never places trades. These ideas are for research only.',
        ),
        findsOneWidget,
      );
    });

    testWidgets('failure shows an error with retry, then recovers', (
      tester,
    ) async {
      await pumpIdeas(
        tester,
        overrides: demoOverrides(
          behavior: const DemoBehavior(
            latency: Duration.zero,
            failNextCalls: 1,
          ),
        ),
      );
      expect(cards(tester), isEmpty);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(cards(tester), hasLength(6));
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpIdeas(
                tester,
                mode: mode,
                scale: scale,
                dir: dir,
                onCompare: () {},
                onSimulated: () {},
              );
              await tapCompare(tester, 0);
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }

    testWidgets('the research sheet meets the accessibility guidelines at 2x', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpIdeas(tester, scale: 2.0);
      await tester.tap(find.widgetWithText(FilledButton, 'Research').first);
      await tester.pumpAndSettle();
      await accessibilityChecks(tester);
      handle.dispose();
    });
  });

  group('CompareScreen', () {
    Future<void> pumpCompare(
      WidgetTester tester,
      List<String> ids, {
      double scale = 1.0,
      ThemeMode mode = ThemeMode.light,
      TextDirection dir = TextDirection.ltr,
      VoidCallback? onBack,
    }) async {
      await tester.pumpApp(
        CompareScreen(onBack: onBack),
        textScale: scale,
        themeMode: mode,
        textDirection: dir,
        overrides: demoOverrides(),
        surfaceSize: const Size(400, 6000),
      );
      final n = containerOf(tester).read(compareSelectionProvider.notifier);
      for (final id in ids) {
        n.toggle(id);
      }
      await tester.pumpAndSettle();
    }

    testWidgets('lays the facts side by side without ranking', (tester) async {
      await pumpCompare(tester, ['o-glb', 'o-gov']);
      expect(find.text('Risk'), findsOneWidget);
      expect(find.text('Research score'), findsOneWidget);
      expect(
        find.text('Demo Global Index ETF: Research score 78 of 100'),
        findsOneWidget,
      );
      expect(
        find.text('Demo Government Bond Fund: Research score 66 of 100'),
        findsOneWidget,
      );
      expect(find.text('Fees'), findsOneWidget);
      expect(find.text('Demo Global Index ETF: 0.12% a year'), findsOneWidget);
      expect(
        find.text('Demo Government Bond Fund: 0.15% a year'),
        findsOneWidget,
      );
      expect(find.textContaining('not a ranking or advice'), findsOneWidget);
      expect(find.textContaining('best'), findsNothing);
    });

    testWidgets('an idea without a score says so instead of a number', (
      tester,
    ) async {
      await pumpCompare(tester, ['o-glb', 'o-new']);
      expect(
        find.text('Demo Thematic Fund (new): No score (no evidence)'),
        findsOneWidget,
      );
    });

    testWidgets('fewer than two ideas asks for more and can go back', (
      tester,
    ) async {
      var back = 0;
      await pumpCompare(tester, ['o-glb'], onBack: () => back++);
      expect(
        find.text('Choose at least two ideas to compare.'),
        findsOneWidget,
      );
      await tester.tap(find.text('Back to ideas'));
      expect(back, 1);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        testWidgets(
          'meets the accessibility guidelines (${mode.name}, ${scale}x)',
          (tester) async {
            final handle = tester.ensureSemantics();
            await pumpCompare(
              tester,
              ['o-glb', 'o-gov', 'o-new'],
              scale: scale,
              mode: mode,
            );
            await accessibilityChecks(tester);
            handle.dispose();
          },
        );
      }
    }
  });

  group('Routes and the calculator hand-off', () {
    testWidgets('AI Wealth opens the ideas; Compare opens the comparison', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/ai',
        surfaceSize: const Size(400, 12000),
      );
      await tester.tap(find.byTooltip('Investment opportunities'));
      await tester.pumpAndSettle();
      expect(find.byType(OpportunitiesScreen), findsOneWidget);
      await tapCompare(tester, 0);
      await tapCompare(tester, 1);
      await tester.tap(find.text('Compare 2 selected'));
      await tester.pumpAndSettle();
      expect(find.byType(CompareScreen), findsOneWidget);
      expect(find.text('Compare ideas'), findsOneWidget);
    });

    testWidgets(
      'Simulate opens the calculator with marked, editable assumptions',
      (tester) async {
        await pumpRouterApp(
          tester,
          initialLocation: '/ai/opportunities',
          surfaceSize: const Size(400, 12000),
        );
        await tester.tap(find.widgetWithText(OutlinedButton, 'Simulate').first);
        await tester.pumpAndSettle();
        expect(find.byType(CalculatorScreen), findsOneWidget);
        expect(
          find.textContaining('Pre-filled from Demo Global Index ETF (DEMO)'),
          findsOneWidget,
        );
        String value(String field) => tester
            .widget<TextFormField>(find.byKey(ValueKey('field-$field')))
            .controller!
            .text;
        expect(value('initialInvestment'), '5000');
        expect(value('monthlyContribution'), '300');
        expect(value('annualReturn'), '7');
        expect(value('years'), '20');
        expect(
          find.text(
            'Example assumption from Demo Global Index ETF. Change it freely.',
          ),
          findsWidgets,
        );
        // They can be changed like any other input.
        await tester.enterText(
          find.byKey(const ValueKey('field-annualReturn')),
          '6',
        );
        expect(value('annualReturn'), '6');
      },
    );

    testWidgets('Clear removes the hand-off and restores the defaults', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/ai/opportunities',
        surfaceSize: const Size(400, 12000),
      );
      await tester.tap(find.widgetWithText(OutlinedButton, 'Simulate').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Clear'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Pre-filled from'), findsNothing);
      final defaults = ForecastInputLimits.defaults;
      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const ValueKey('field-initialInvestment')),
            )
            .controller!
            .text,
        defaults.initialInvestment.amount.toString().split('.').first,
      );
    });

    testWidgets('a hand-off updates a calculator that is already open', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/more/calculator',
        surfaceSize: const Size(400, 12000),
      );
      String value(String field) => tester
          .widget<TextFormField>(find.byKey(ValueKey('field-$field')))
          .controller!
          .text;
      expect(find.textContaining('Pre-filled from'), findsNothing);
      expect(value('annualReturn'), '8');

      // The More tab keeps the calculator alive; a hand-off from elsewhere must still show.
      final container = containerOf(tester);
      final list = await container.read(opportunitiesProvider.future);
      final gov = list.byId('o-gov')!.simulation!;
      container
          .read(calculatorInputsProvider.notifier)
          .replace(
            CalculatorInputs.defaults('en').copyWith(
              texts: {
                ...CalculatorInputs.defaults('en').texts,
                CalculatorField.annualReturn: gov.annualReturn.toString(),
              },
            ),
          );
      container
          .read(calculatorPrefillProvider.notifier)
          .set(
            const CalculatorPrefill(
              sourceName: 'Demo Government Bond Fund',
              fields: {CalculatorField.annualReturn},
            ),
          );
      await tester.pumpAndSettle();
      expect(value('annualReturn'), '4');
      expect(
        find.textContaining('Pre-filled from Demo Government Bond Fund'),
        findsOneWidget,
      );
    });

    testWidgets('a deep link opens the comparison, empty at first', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/ai/opportunities/compare',
        surfaceSize: const Size(400, 4000),
      );
      expect(find.byType(CompareScreen), findsOneWidget);
      expect(
        find.text('Choose at least two ideas to compare.'),
        findsOneWidget,
      );
    });
  });
}

/// Builds minimal candidate JSON for rejection tests.
abstract final class JsonCandidate {
  static JsonReader minimal({int? score}) => JsonReader({
    'id': 'x',
    'category': 'funds',
    'name': 'X',
    'symbol': 'DEMO-X',
    'asset_class': 'Fund',
    'summary': 's',
    'risk': 'low',
    'risks': <dynamic>[],
    'evidence': <dynamic>[],
    'as_of': '2026-10-09T08:00:00Z',
    'attributes': <dynamic>[],
    'research': <dynamic>[],
    'score': ?score,
  });
}

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/portfolios/application/holdings_query.dart';
import 'package:wealthsphere_app/features/portfolios/application/portfolio_providers.dart';
import 'package:wealthsphere_app/features/portfolios/presentation/holdings_screen.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';
import '../../helpers/strict_tap_target.dart';

HoldingSummary holding(
  String symbol,
  String name,
  String cls,
  String value,
  String change, {
  String? native,
  String nativeCurrency = 'USD',
}) => HoldingSummary(
  symbol: symbol,
  name: name,
  assetClass: cls,
  value: Money.parse(value, 'USD'),
  nativeValue: Money.parse(native ?? value, nativeCurrency),
  changePercent: Decimal.parse(change),
  asOf: DateTime.utc(2026, 10, 9),
);

List<String?> symbolsShown(WidgetTester tester) => [
  for (final row in tester.widgetList<InvestmentRow>(
    find.byType(InvestmentRow),
  ))
    row.symbol,
];

Future<void> pump(
  WidgetTester tester, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
}) async {
  await tester.pumpApp(
    const HoldingsScreen(),
    themeMode: mode,
    textScale: scale,
    textDirection: dir,
    surfaceSize: const Size(400, 1800),
  );
}

void main() {
  group('applyQuery', () {
    final all = [
      holding('B', 'Bond fund', 'Bonds', '300.00', '0.5'),
      holding('A', 'Alpha Equity', 'Equities', '300.00', '2.0'),
      holding('C', 'charlie equity', 'Equities', '100.00', '-1.0'),
    ];
    List<String?> run(HoldingsQuery q) => [
      for (final h in applyQuery(all, q)) h.symbol,
    ];

    test('sorts by value, ties by symbol', () {
      expect(run(const HoldingsQuery()), ['A', 'B', 'C']);
      expect(run(const HoldingsQuery(sort: HoldingSort.valueAsc)), [
        'C',
        'A',
        'B',
      ]);
    });

    test('sorts by name ignoring case, and by change', () {
      expect(run(const HoldingsQuery(sort: HoldingSort.nameAsc)), [
        'A',
        'B',
        'C',
      ]);
      expect(run(const HoldingsQuery(sort: HoldingSort.changeDesc)), [
        'A',
        'B',
        'C',
      ]);
      expect(run(const HoldingsQuery(sort: HoldingSort.changeAsc)), [
        'C',
        'B',
        'A',
      ]);
    });

    test('search matches name or symbol, ignoring case and spaces', () {
      expect(run(const HoldingsQuery(search: '  EQUITY ')), ['A', 'C']);
      expect(run(const HoldingsQuery(search: 'b')), ['B']);
      expect(run(const HoldingsQuery(search: 'zzz')), isEmpty);
    });

    test('filters by asset class and combines with search', () {
      expect(run(const HoldingsQuery(assetClass: 'Equities')), ['A', 'C']);
      expect(
        run(const HoldingsQuery(assetClass: 'Equities', search: 'alpha')),
        ['A'],
      );
      expect(assetClassesOf(all), ['Bonds', 'Equities']);
    });

    test('copyWith can clear the asset class and keeps the sort on clear', () {
      const q = HoldingsQuery(assetClass: 'Bonds', sort: HoldingSort.nameAsc);
      expect(q.copyWith(assetClass: null).assetClass, isNull);
      expect(q.copyWith(search: 'x').assetClass, 'Bonds');
      expect(q.isFiltered, isTrue);
      expect(const HoldingsQuery().isFiltered, isFalse);
    });
  });

  group('HoldingsScreen', () {
    testWidgets(
      'lists every holding by value with native and converted values',
      (tester) async {
        await pump(tester);
        expect(symbolsShown(tester).first, 'DEMO-GEQ');
        expect(symbolsShown(tester), hasLength(10));
        // DEMO-EMR is held in AED: both the converted and the native value are shown.
        final emr = tester.widget<InvestmentRow>(
          find.widgetWithText(InvestmentRow, 'DEMO-EMR'),
        );
        expect(emr.value?.currencyCode, 'USD');
        expect(emr.nativeValue?.currencyCode, 'AED');
        // A USD holding in a USD portfolio shows no second line.
        final geq = tester.widget<InvestmentRow>(
          find.widgetWithText(InvestmentRow, 'DEMO-GEQ'),
        );
        expect(geq.nativeValue, isNull);
        expect(find.text('Holdings'), findsOneWidget);
        expect(find.text('DEMO'), findsOneWidget);
      },
    );

    testWidgets('search narrows the list and announces the result', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pump(tester);
      await tester.enterText(find.byType(TextField), 'bond');
      await tester.pump();
      expect(symbolsShown(tester), ['DEMO-BND']);
      expect(
        find.text('1 investment, matching bond, sorted by Value, high to low'),
        findsOneWidget,
      );
      final live = tester.getSemantics(
        find.text('1 investment, matching bond, sorted by Value, high to low'),
      );
      expect(live.label, contains('1 investment'));
      expect(live.flagsCollection.isLiveRegion, isTrue);
      handle.dispose();
    });

    testWidgets('clearing the search restores the list', (tester) async {
      await pump(tester);
      await tester.enterText(find.byType(TextField), 'bond');
      await tester.pump();
      await tester.tap(find.byTooltip('Clear search'));
      await tester.pump();
      expect(symbolsShown(tester), hasLength(10));
      expect(find.byTooltip('Clear search'), findsNothing);
    });

    testWidgets(
      'asset class chips filter; selection is a word, not only colour',
      (tester) async {
        final handle = tester.ensureSemantics();
        await pump(tester);
        expect(find.widgetWithText(ChoiceChip, 'All'), findsOneWidget);
        await tester.tap(find.widgetWithText(ChoiceChip, 'Bonds'));
        await tester.pump();
        expect(symbolsShown(tester), ['DEMO-BND', 'DEMO-KTB']);
        expect(find.textContaining('in Bonds'), findsOneWidget);
        expect(
          tester.getSemantics(find.widgetWithText(ChoiceChip, 'Bonds')).label,
          'Bonds, Selected',
        );
        expect(
          tester.getSemantics(find.widgetWithText(ChoiceChip, 'All')).label,
          'All',
        );
        await tester.tap(find.widgetWithText(ChoiceChip, 'All'));
        await tester.pump();
        expect(symbolsShown(tester), hasLength(10));
        handle.dispose();
      },
    );

    testWidgets('sorting reorders and announces the new order', (tester) async {
      await pump(tester);
      await tester.tap(find.byTooltip('Sort'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Change, worst first'));
      await tester.pumpAndSettle();
      expect(symbolsShown(tester).first, 'DEMO-KEN'); // -1.10 is the lowest
      expect(
        find.text('10 investments, sorted by Change, worst first'),
        findsOneWidget,
      );
      await tester.tap(find.byTooltip('Sort'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Name, A to Z'));
      await tester.pumpAndSettle();
      expect(
        symbolsShown(tester).first,
        'DEMO-BND',
      ); // Demo Aggregate Bond Fund
    });

    testWidgets(
      'no match says so and clearing the filters brings the list back',
      (tester) async {
        await pump(tester);
        await tester.enterText(find.byType(TextField), 'no such thing');
        await tester.pump();
        expect(find.text('No matching investments'), findsOneWidget);
        expect(symbolsShown(tester), isEmpty);
        await tester.tap(find.text('Clear filters'));
        await tester.pump();
        expect(symbolsShown(tester), hasLength(10));
        expect(
          tester.widget<TextField>(find.byType(TextField)).controller!.text,
          isEmpty,
        );
      },
    );

    testWidgets('an empty portfolio shows the empty state', (tester) async {
      await tester.pumpApp(
        const HoldingsScreen(),
        overrides: demoOverrides(
          extra: [
            portfolioHoldingsProvider.overrideWith(
              (ref, id) async => <HoldingSummary>[],
            ),
          ],
        ),
      );
      expect(find.text('No investments yet'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
    });

    testWidgets('shows a skeleton while loading, then the list', (
      tester,
    ) async {
      await tester.pumpApp(
        const HoldingsScreen(),
        overrides: demoOverrides(
          behavior: const DemoBehavior(
            latency: Duration(seconds: 1),
            streamInterval: Duration.zero,
          ),
        ),
        settle: false,
      );
      await tester.pump();
      expect(find.byType(SkeletonLoader), findsOneWidget);
      await tester.pump(const Duration(seconds: 2));
      expect(find.byType(InvestmentRow), findsWidgets);
    });

    testWidgets('a failed load offers retry', (tester) async {
      await tester.pumpApp(
        const HoldingsScreen(),
        overrides: demoOverrides(
          behavior: const DemoBehavior(
            latency: Duration.zero,
            streamInterval: Duration.zero,
            failNextCalls: 1,
          ),
        ),
      );
      expect(find.byType(ErrorState), findsOneWidget);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.byType(InvestmentRow), findsWidgets);
    });

    testWidgets('switching the selected portfolio switches the list', (
      tester,
    ) async {
      await tester.pumpApp(
        const HoldingsScreen(),
        surfaceSize: const Size(400, 1800),
      );
      final container = ProviderScope.containerOf(
        tester.element(find.byType(HoldingsScreen)),
      );
      container.read(selectedPortfolioIdProvider.notifier).select('p-growth');
      await tester.pumpAndSettle();
      expect(symbolsShown(tester), ['DEMO-TEC', 'DEMO-KEN', 'DEMO-CRY']);
    });

    testWidgets('rows open when a handler is given', (tester) async {
      final opened = <String>[];
      await tester.pumpApp(
        HoldingsScreen(onOpen: (h) => opened.add(h.detailKey)),
        surfaceSize: const Size(400, 1800),
      );
      await tester.tap(find.widgetWithText(InvestmentRow, 'DEMO-BND'));
      expect(opened, ['DEMO-BND']);
    });

    testWidgets('is reachable at /portfolio/holdings with a back button', (
      tester,
    ) async {
      await pumpRouterApp(tester, initialLocation: '/portfolio');
      await tester.scrollUntilVisible(find.text('View all holdings'), 300);
      await tester.ensureVisible(find.text('View all holdings'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('View all holdings'));
      await tester.pumpAndSettle();
      expect(find.byType(HoldingsScreen), findsOneWidget);
      expect(find.byType(BackButton), findsOneWidget);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.byType(HoldingsScreen), findsNothing);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pump(tester, mode: mode, scale: scale, dir: dir);
              expect(tester.takeException(), isNull);
              await expectLater(
                tester,
                meetsGuideline(androidTapTargetGuideline),
              );
              await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
              await expectLater(
                tester,
                meetsGuideline(labeledTapTargetGuideline),
              );
              await expectLater(
                tester,
                meetsGuideline(const StrictTapTargetGuideline()),
              );
              await expectLater(tester, meetsGuideline(textContrastGuideline));
              handle.dispose();
            },
          );
        }
      }
    }
  });
}

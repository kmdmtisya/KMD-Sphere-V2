import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/alerts/data/alerts_repository.dart';
import 'package:wealthsphere_app/features/investments/application/investment_providers.dart';
import 'package:wealthsphere_app/features/investments/data/investment_repository.dart';
import 'package:wealthsphere_app/features/investments/presentation/investment_detail_screen.dart';
import 'package:wealthsphere_app/features/portfolios/presentation/holdings_screen.dart';
import 'package:wealthsphere_app/features/transactions/domain/ledger_entry.dart';
import 'package:wealthsphere_app/features/transactions/presentation/transaction_detail_screen.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';
import '../../helpers/strict_tap_target.dart';

const symbols = [
  'DEMO-GEQ',
  'DEMO-BND',
  'DEMO-EMR',
  'DEMO-CSH',
  'DEMO-TEC',
  'DEMO-KEN',
  'DEMO-CRY',
  'DEMO-DIV',
  'DEMO-KTB',
  'DEMO-REI',
];

ProviderContainer containerOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));

Future<void> pumpDetail(
  WidgetTester tester,
  String symbol, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
  void Function(dynamic)? onOpenTransaction,
}) => tester.pumpApp(
  InvestmentDetailScreen(symbol: symbol, onOpenTransaction: onOpenTransaction),
  themeMode: mode,
  textScale: scale,
  textDirection: dir,
  surfaceSize: const Size(400, 2800),
);

Future<void> openTab(WidgetTester tester, String label) async {
  await tester.tap(find.widgetWithText(ChoiceChip, label));
  await tester.pumpAndSettle();
}

Future<void> accessibilityChecks(WidgetTester tester) async {
  expect(tester.takeException(), isNull);
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(const StrictTapTargetGuideline()));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
}

const tabs = ['Fundamentals', 'Income', 'Position', 'Transactions', 'Research'];

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('DemoInvestmentRepository', () {
    late ProviderContainer container;
    late InvestmentRepository repo;

    setUp(() {
      container = ProviderContainer(overrides: demoOverrides());
      addTearDown(container.dispose);
      repo = container.read(investmentRepositoryProvider);
    });

    test(
      'every held investment has a complete, labelled-demo detail',
      () async {
        for (final symbol in symbols) {
          final d = await repo.detail(symbol);
          expect(d.symbol, symbol);
          expect(d.price!.amount, greaterThan(Decimal.zero));
          expect(d.price!.currencyCode, d.currency);
          expect(d.priceSource!.provider, isNotEmpty);
          expect(d.positions.single.quantity, greaterThan(Decimal.zero));
        }
      },
    );

    test('price history is ascending and ends at the latest price', () async {
      for (final symbol in symbols) {
        final d = await repo.detail(symbol);
        for (final period in investmentPeriods) {
          final s = await repo.priceHistory(symbol, period);
          expect(s.points.length, greaterThan(5), reason: '$symbol $period');
          for (var i = 1; i < s.points.length; i++) {
            expect(
              s.points[i].date.isAfter(s.points[i - 1].date),
              isTrue,
              reason: '$symbol $period is ascending',
            );
          }
          expect(s.points.last.value, d.price!.amount, reason: symbol);
          expect(s.currencyCode, d.currency);
        }
      }
    });

    test('an unknown symbol is an error, not an invented investment', () async {
      await expectLater(repo.detail('NOPE'), throwsA(isA<DataLoadException>()));
      await expectLater(
        repo.priceHistory('NOPE', investmentPeriods.first),
        throwsA(isA<DataLoadException>()),
      );
    });

    test('income and fundamentals may be absent', () async {
      expect((await repo.detail('DEMO-TEC')).income, isNull);
      expect((await repo.detail('DEMO-CSH')).fundamentals!.items, isEmpty);
      expect((await repo.detail('DEMO-CSH')).research, isEmpty);
    });
  });

  group('InvestmentDetailScreen', () {
    testWidgets('header shows name, price, change, source and as-of', (
      tester,
    ) async {
      await pumpDetail(tester, 'DEMO-GEQ');
      expect(find.text('Demo Global Equity Fund'), findsOneWidget);
      expect(find.text('DEMO-GEQ · Equities'), findsOneWidget);
      expect(find.text('\$104.20'), findsOneWidget);
      expect(find.text('Latest price per unit'), findsOneWidget);
      expect(find.byType(ChangeIndicator), findsWidgets);
      expect(find.byType(DataAsOfLabel), findsWidgets);
      expect(find.byType(EvidenceSourceChip), findsWidgets);
      expect(find.text('DEMO'), findsWidgets, reason: 'labelled DEMO');
    });

    testWidgets('a price source and an as-of time accompany every tab', (
      tester,
    ) async {
      await pumpDetail(tester, 'DEMO-GEQ');
      for (final tab in ['Fundamentals', 'Income', 'Position', 'Research']) {
        await openTab(tester, tab);
        // The header has one of each; the tab adds its own.
        expect(
          find.byType(DataAsOfLabel),
          findsAtLeastNWidgets(2),
          reason: tab,
        );
      }
      await openTab(tester, 'Fundamentals');
      expect(find.byType(EvidenceSourceChip), findsAtLeastNWidgets(2));
    });

    testWidgets('the period selector changes the chart range', (tester) async {
      await pumpDetail(tester, 'DEMO-GEQ');
      expect(containerOf(tester).read(investmentPeriodProvider).name, 'year');
      await tester.tap(find.text('1M'));
      await tester.pumpAndSettle();
      expect(containerOf(tester).read(investmentPeriodProvider).name, 'month');
      final series = await containerOf(tester).read(
        investmentHistoryProvider((
          symbol: 'DEMO-GEQ',
          period: investmentPeriods.first,
        )).future,
      );
      expect(series.points, hasLength(22));
    });

    testWidgets('fundamentals tab lists the facts', (tester) async {
      await pumpDetail(tester, 'DEMO-GEQ');
      expect(find.text('Expense ratio'), findsOneWidget);
      expect(find.text('0.20%'), findsOneWidget);
    });

    testWidgets('income tab shows yield, frequency and payments', (
      tester,
    ) async {
      await pumpDetail(tester, 'DEMO-GEQ');
      await openTab(tester, 'Income');
      expect(find.text('Yield'), findsOneWidget);
      expect(find.text('Quarterly'), findsOneWidget);
      expect(find.textContaining('Dividend · Sep 20, 2026'), findsOneWidget);
      expect(find.textContaining('not a forecast'), findsOneWidget);
    });

    testWidgets('position tab shows the server-calculated position', (
      tester,
    ) async {
      await pumpDetail(tester, 'DEMO-GEQ');
      await openTab(tester, 'Position');
      expect(find.text('Units held'), findsOneWidget);
      expect(find.text('\$42,000.00'), findsOneWidget);
      expect(find.textContaining('Calculated by the server'), findsOneWidget);
      expect(find.text('Value in USD'), findsNothing);
    });

    testWidgets('position shows the native value when the currency differs', (
      tester,
    ) async {
      await pumpDetail(tester, 'DEMO-KEN');
      await openTab(tester, 'Position');
      expect(find.text('Value in KES'), findsOneWidget);
      expect(find.text('\$8,340.00'), findsOneWidget);
    });

    testWidgets('transactions tab lists only this investment, newest first', (
      tester,
    ) async {
      final opened = <String>[];
      await pumpDetail(
        tester,
        'DEMO-GEQ',
        onOpenTransaction: (e) => opened.add((e as LedgerEntry).id),
      );
      await openTab(tester, 'Transactions');
      final tiles = tester
          .widgetList<TransactionTile>(find.byType(TransactionTile))
          .toList();
      expect(tiles.map((t) => t.kind), [
        TransactionKind.buy,
        TransactionKind.dividend,
        TransactionKind.sell,
      ]);
      await tester.tap(find.byType(TransactionTile).first);
      expect(opened, ['t-002']);
    });

    testWidgets('research notes carry their source and a disclaimer', (
      tester,
    ) async {
      await pumpDetail(tester, 'DEMO-GEQ');
      await openTab(tester, 'Research');
      expect(find.text('Broad equity exposure'), findsOneWidget);
      expect(find.byType(EvidenceSourceChip), findsAtLeastNWidgets(2));
      expect(find.textContaining('do not predict returns'), findsOneWidget);
    });

    testWidgets('missing data shows a plain empty message, not a blank tab', (
      tester,
    ) async {
      await pumpDetail(tester, 'DEMO-CSH');
      expect(
        find.text('No fundamentals are available for this investment.'),
        findsOneWidget,
      );
      await openTab(tester, 'Research');
      expect(
        find.text('No research notes for this investment.'),
        findsOneWidget,
      );
      await pumpDetail(tester, 'DEMO-TEC');
      await openTab(tester, 'Income');
      expect(
        find.text('This investment has not paid any income.'),
        findsOneWidget,
      );
      await openTab(tester, 'Transactions');
      expect(find.byType(TransactionTile), findsWidgets);
    });

    testWidgets('an investment with no transactions says so', (tester) async {
      await pumpDetail(tester, 'DEMO-EMR');
      await openTab(tester, 'Transactions');
      expect(
        find.text('No transactions for this investment yet.'),
        findsOneWidget,
      );
    });

    testWidgets('offers no Buy, Sell or trade action on any tab', (
      tester,
    ) async {
      final trading = RegExp(
        r'\b(buy|sell|trade|invest now|order)\b',
        caseSensitive: false,
      );
      await pumpDetail(tester, 'DEMO-GEQ');
      for (final tab in tabs) {
        await openTab(tester, tab);
        final labels = [
          for (final button in tester.widgetList<ButtonStyleButton>(
            find.byWidgetPredicate((w) => w is ButtonStyleButton),
          ))
            if (button.child is Text) (button.child! as Text).data ?? '',
        ];
        expect(labels.where(trading.hasMatch), isEmpty, reason: tab);
        expect(find.byType(FloatingActionButton), findsNothing, reason: tab);
      }
      expect(
        find.text('Informational only. WealthSphere does not place trades.'),
        findsOneWidget,
      );
    });

    testWidgets('the watchlist action toggles and announces', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpDetail(tester, 'DEMO-GEQ');
      expect(find.byTooltip('Add to watchlist'), findsOneWidget);
      await tester.tap(find.byTooltip('Add to watchlist'));
      await tester.pump();
      expect(find.text('Added to your watchlist'), findsOneWidget);
      expect(
        [
          for (final i in await containerOf(
            tester,
          ).read(watchlistRepositoryProvider).items())
            i.assetKey,
        ],
        ['DEMO-GEQ'],
      );
      await tester.pumpAndSettle();
      expect(find.byTooltip('Remove from watchlist'), findsOneWidget);
      await tester.tap(find.byTooltip('Remove from watchlist'));
      // The first message slides out before the second slides in.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 750));
      expect(find.text('Removed from your watchlist'), findsOneWidget);
      await tester.pumpAndSettle();
      expect(
        await containerOf(tester).read(watchlistRepositoryProvider).items(),
        isEmpty,
      );
      handle.dispose();
    });

    testWidgets('an unknown investment shows an error with retry', (
      tester,
    ) async {
      await pumpDetail(tester, 'NOPE');
      expect(find.text('Try again'), findsOneWidget);
    });

    testWidgets('a failed load recovers on retry', (tester) async {
      await tester.pumpApp(
        const InvestmentDetailScreen(symbol: 'DEMO-GEQ'),
        overrides: demoOverrides(
          behavior: const DemoBehavior(
            latency: Duration.zero,
            failNextCalls: 1,
          ),
        ),
        surfaceSize: const Size(400, 2800),
      );
      expect(find.text('Demo Global Equity Fund'), findsNothing);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.text('Demo Global Equity Fund'), findsOneWidget);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpDetail(
                tester,
                'DEMO-GEQ',
                mode: mode,
                scale: scale,
                dir: dir,
                onOpenTransaction: (_) {},
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }

    for (final tab in tabs.skip(1)) {
      testWidgets('$tab tab meets the accessibility guidelines at 2x', (
        tester,
      ) async {
        final handle = tester.ensureSemantics();
        await pumpDetail(
          tester,
          'DEMO-GEQ',
          scale: 2.0,
          onOpenTransaction: (_) {},
        );
        await openTab(tester, tab);
        await accessibilityChecks(tester);
        handle.dispose();
      });
    }
  });

  group('Routes', () {
    testWidgets('tapping a holding opens its investment, with back', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/portfolio/holdings',
        surfaceSize: const Size(400, 1800),
      );
      expect(find.byType(HoldingsScreen), findsOneWidget);
      await tester.tap(find.widgetWithText(InvestmentRow, 'DEMO-GEQ'));
      await tester.pumpAndSettle();
      expect(find.byType(InvestmentDetailScreen), findsOneWidget);
      expect(find.text('Demo Global Equity Fund'), findsWidgets);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.byType(HoldingsScreen), findsOneWidget);
    });

    testWidgets('a deep link opens the investment', (tester) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/portfolio/holdings/DEMO-BND',
        surfaceSize: const Size(400, 1800),
      );
      expect(find.byType(InvestmentDetailScreen), findsOneWidget);
      expect(find.text('Demo Aggregate Bond Fund'), findsWidgets);
    });

    testWidgets('a transaction on the Transactions tab opens that entry', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/portfolio/holdings/DEMO-GEQ',
        surfaceSize: const Size(400, 2800),
      );
      await tester.tap(find.widgetWithText(ChoiceChip, 'Transactions'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(TransactionTile).first);
      await tester.pumpAndSettle();
      expect(find.byType(TransactionDetailScreen), findsOneWidget);
    });
  });
}

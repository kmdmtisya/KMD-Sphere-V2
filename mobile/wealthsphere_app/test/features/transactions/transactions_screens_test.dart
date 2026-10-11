import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/portfolios/application/portfolio_providers.dart';
import 'package:wealthsphere_app/features/transactions/application/ledger_view.dart';
import 'package:wealthsphere_app/features/transactions/data/transaction_repository.dart';
import 'package:wealthsphere_app/features/transactions/domain/ledger_entry.dart';
import 'package:wealthsphere_app/features/transactions/presentation/add_transaction_screen.dart';
import 'package:wealthsphere_app/features/transactions/presentation/transaction_detail_screen.dart';
import 'package:wealthsphere_app/features/transactions/presentation/transactions_screen.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';
import '../../helpers/strict_tap_target.dart';

final DateTime fixedToday = DateTime(2026, 10, 9, 12);

List<Override> overrides() =>
    demoOverrides(extra: [todayProvider.overrideWithValue(fixedToday)]);

List<TransactionTile> tiles(WidgetTester tester) =>
    tester.widgetList<TransactionTile>(find.byType(TransactionTile)).toList();

ProviderContainer containerOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));

Future<void> pumpList(
  WidgetTester tester, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
  void Function(LedgerEntry)? onOpen,
  VoidCallback? onAdd,
}) => tester.pumpApp(
  TransactionsScreen(onOpen: onOpen, onAdd: onAdd),
  themeMode: mode,
  textScale: scale,
  textDirection: dir,
  overrides: overrides(),
  surfaceSize: const Size(400, 6000),
);

Future<void> pumpDetail(
  WidgetTester tester,
  String id, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
  void Function(String)? onOpenEntry,
  void Function(LedgerEntry)? onAddCorrected,
}) => tester.pumpApp(
  TransactionDetailScreen(
    entryId: id,
    onOpenEntry: onOpenEntry,
    onAddCorrected: onAddCorrected,
  ),
  themeMode: mode,
  textScale: scale,
  textDirection: dir,
  overrides: overrides(),
  surfaceSize: const Size(400, 1800),
);

Future<void> pumpAdd(
  WidgetTester tester, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
  LedgerEntry? correctionOf,
  void Function(String)? onOpenEntry,
  VoidCallback? onDone,
}) => tester.pumpApp(
  AddTransactionScreen(
    correctionOf: correctionOf,
    onOpenEntry: onOpenEntry,
    onDone: onDone,
  ),
  themeMode: mode,
  textScale: scale,
  textDirection: dir,
  overrides: overrides(),
  surfaceSize: const Size(400, 2400),
);

Future<void> chooseFromDropdown(
  WidgetTester tester,
  String label,
  String option,
) async {
  await tester.tap(find.widgetWithText(DropdownButtonFormField<String>, label));
  await tester.pumpAndSettle();
  await tester.tap(find.text(option).last);
  await tester.pumpAndSettle();
}

Future<void> chooseKind(WidgetTester tester, String option) async {
  await tester.tap(
    find.widgetWithText(DropdownButtonFormField<TransactionKind>, 'Type'),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text(option).last);
  await tester.pumpAndSettle();
}

Future<void> pickToday(WidgetTester tester) async {
  await tester.tap(find.text('Select a date'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

Finder field(String label) => find.widgetWithText(TextField, label);

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

  group('Transactions list', () {
    testWidgets('groups the ledger by month, newest first', (tester) async {
      await pumpList(tester);
      for (final month in [
        'October 2026',
        'September 2026',
        'August 2026',
        'July 2026',
      ]) {
        expect(find.text(month), findsOneWidget);
      }
      expect(
        tester.getTopLeft(find.text('October 2026')).dy,
        lessThan(tester.getTopLeft(find.text('September 2026')).dy),
      );
      expect(tiles(tester), hasLength(16));
      expect(find.text('16 entries'), findsOneWidget);
      expect(find.text('DEMO'), findsWidgets, reason: 'labelled DEMO');
    });

    testWidgets('a reversed entry is struck and its reversal is linked', (
      tester,
    ) async {
      await pumpList(tester);
      final reversed = tiles(tester).where((t) => t.reversed).toList();
      expect(reversed, hasLength(1));
      expect(reversed.single.kind, TransactionKind.buy);
      expect(find.text('Reversed'), findsOneWidget);
      expect(
        find.textContaining('Reversal of Demo Aggregate Bond Fund'),
        findsOneWidget,
      );
    });

    testWidgets('a reversal moves cash the opposite way to its original', (
      tester,
    ) async {
      await pumpList(tester);
      final reversal = tiles(tester).firstWhere(
        (t) => t.assetName == 'Reversal of Demo Aggregate Bond Fund',
      );
      expect(reversal.direction, CashDirection.inflow);
      final original = tiles(tester).firstWhere((t) => t.reversed);
      expect(original.direction, CashDirection.outflow);
    });

    testWidgets('filter chips only list groups that have entries', (
      tester,
    ) async {
      await pumpList(tester);
      for (final label in [
        'All',
        'Trades',
        'Cash',
        'Income',
        'Fees and taxes',
      ]) {
        expect(find.widgetWithText(ChoiceChip, label), findsOneWidget);
      }
      expect(find.widgetWithText(ChoiceChip, 'Other'), findsNothing);
    });

    testWidgets('choosing a chip filters, announces and keeps month groups', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpList(tester);
      await tester.tap(find.widgetWithText(ChoiceChip, 'Trades'));
      await tester.pumpAndSettle();
      expect(tiles(tester), hasLength(7));
      expect(
        tiles(tester).every(
          (t) =>
              t.kind == TransactionKind.buy || t.kind == TransactionKind.sell,
        ),
        isTrue,
      );
      expect(find.text('7 entries, showing Trades'), findsOneWidget);
      expect(
        find.bySemanticsLabel('7 entries, showing Trades'),
        findsOneWidget,
      );
      expect(find.bySemanticsLabel('Trades, Selected'), findsOneWidget);
      await tester.tap(find.widgetWithText(ChoiceChip, 'All'));
      await tester.pumpAndSettle();
      expect(tiles(tester), hasLength(16));
      handle.dispose();
    });

    testWidgets('follows the selected portfolio', (tester) async {
      await pumpList(tester);
      containerOf(tester)
          .read(selectedPortfolioIdProvider.notifier)
          .select('p-growth');
      await tester.pumpAndSettle();
      expect(tiles(tester), hasLength(4));
      expect(find.text('4 entries'), findsOneWidget);
    });

    testWidgets('a filter that no longer matches falls back to All', (
      tester,
    ) async {
      await pumpList(tester);
      final container = containerOf(tester);
      container.read(txFilterProvider.notifier).select(TxFilter.income);
      container.read(selectedPortfolioIdProvider.notifier).select('p-growth');
      await tester.pumpAndSettle();
      // The Growth portfolio has no income, so the list shows everything instead of nothing.
      expect(tiles(tester), hasLength(4));
      expect(find.text('4 entries'), findsOneWidget);
    });

    testWidgets('rows open and the add button calls back', (tester) async {
      final opened = <String>[];
      var added = 0;
      await pumpList(
        tester,
        onOpen: (e) => opened.add(e.id),
        onAdd: () => added++,
      );
      await tester.tap(find.byType(TransactionTile).first);
      expect(opened, ['t-010'], reason: 'the newest entry is first');
      await tester.tap(find.text('Add transaction'));
      expect(added, 1);
    });

    testWidgets('states the append-only rule', (tester) async {
      await pumpList(tester);
      expect(find.textContaining('never edited'), findsOneWidget);
    });

    testWidgets('failure shows an error with retry, then recovers', (
      tester,
    ) async {
      await tester.pumpApp(
        const TransactionsScreen(),
        overrides: demoOverrides(
          behavior: const DemoBehavior(
            latency: Duration.zero,
            failNextCalls: 1,
          ),
          extra: [todayProvider.overrideWithValue(fixedToday)],
        ),
        surfaceSize: const Size(400, 6000),
      );
      expect(find.byType(TransactionTile), findsNothing);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.byType(TransactionTile), findsWidgets);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'list meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpList(
                tester,
                mode: mode,
                scale: scale,
                dir: dir,
                onOpen: (_) {},
                onAdd: () {},
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('Transaction detail', () {
    testWidgets('a live entry offers a correction and says it is live', (
      tester,
    ) async {
      await pumpDetail(tester, 't-002');
      expect(find.text('Demo Global Equity Fund (DEMO-GEQ)'), findsOneWidget);
      expect(find.text('No corrections. This entry is live.'), findsOneWidget);
      expect(find.text('Correct this entry'), findsOneWidget);
      expect(find.text('Add corrected entry'), findsNothing);
    });

    testWidgets('a reversed entry links to its reversal and offers a redo', (
      tester,
    ) async {
      final opened = <String>[];
      LedgerEntry? corrected;
      await pumpDetail(
        tester,
        't-005',
        onOpenEntry: opened.add,
        onAddCorrected: (e) => corrected = e,
      );
      expect(
        find.textContaining('Cancelled by a later reversal'),
        findsOneWidget,
      );
      expect(find.text('Correct this entry'), findsNothing);
      await tester.tap(find.text('View the reversal'));
      expect(opened, ['t-006']);
      await tester.tap(find.text('Add corrected entry'));
      expect(corrected?.id, 't-005');
    });

    testWidgets('a reversal links back to the original and is final', (
      tester,
    ) async {
      final opened = <String>[];
      await pumpDetail(tester, 't-006', onOpenEntry: opened.add);
      expect(find.textContaining('cancels an earlier entry'), findsOneWidget);
      expect(find.text('Correct this entry'), findsNothing);
      expect(find.text('Add corrected entry'), findsNothing);
      await tester.tap(find.text('View the original entry'));
      expect(opened, ['t-005']);
      expect(
        find.textContaining('Reversal of Demo Aggregate Bond Fund'),
        findsOneWidget,
      );
    });

    testWidgets('correcting adds a reversal instead of editing', (
      tester,
    ) async {
      await pumpDetail(tester, 't-002');
      await tester.tap(find.text('Correct this entry'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Entries are never edited'), findsWidgets);
      await tester.enterText(find.byType(TextField), 'wrong fund');
      await tester.tap(find.text('Add reversal'));
      await tester.pumpAndSettle();
      expect(
        find.text('Reversal added. The entry is now marked as reversed.'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Cancelled by a later reversal'),
        findsOneWidget,
      );
      expect(find.text('Correct this entry'), findsNothing);
      // The ledger grew by one entry; the original is still there, only linked.
      final all = await containerOf(tester)
          .read(transactionRepositoryProvider)
          .entries('consolidated');
      expect(all, hasLength(17));
      expect(all.where((e) => e.id == 't-002'), hasLength(1));
    });

    testWidgets('cancelling the dialog changes nothing', (tester) async {
      await pumpDetail(tester, 't-002');
      await tester.tap(find.text('Correct this entry'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      final all = await containerOf(tester)
          .read(transactionRepositoryProvider)
          .entries('consolidated');
      expect(all, hasLength(16));
      expect(find.text('No corrections. This entry is live.'), findsOneWidget);
    });

    testWidgets('an unknown entry shows an error, not a blank screen', (
      tester,
    ) async {
      await pumpDetail(tester, 'nope');
      expect(find.text('Try again'), findsOneWidget);
    });

    for (final id in ['t-002', 't-005', 't-006']) {
      for (final mode in [ThemeMode.light, ThemeMode.dark]) {
        for (final scale in [1.0, 2.0]) {
          testWidgets(
            'detail $id meets the accessibility guidelines (${mode.name}, ${scale}x)',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpDetail(
                tester,
                id,
                mode: mode,
                scale: scale,
                onOpenEntry: (_) {},
                onAddCorrected: (_) {},
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('Add transaction', () {
    testWidgets('an empty form lists every missing field in plain words', (
      tester,
    ) async {
      await pumpAdd(tester);
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      expect(find.text('Portfolio is required.'), findsOneWidget);
      expect(find.text('Investment is required.'), findsOneWidget);
      expect(find.text('Trade date is required.'), findsOneWidget);
      expect(find.text('Quantity is required.'), findsOneWidget);
      expect(find.text('Price per unit is required.'), findsOneWidget);
      expect(find.text('Fix 5 fields to continue'), findsOneWidget);
      expect(find.text('Check before saving'), findsNothing);
    });

    testWidgets('number mistakes are explained next to the field', (
      tester,
    ) async {
      await pumpAdd(tester);
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      await tester.enterText(field('Quantity'), '0');
      await tester.pumpAndSettle();
      expect(find.text('Enter a number greater than zero.'), findsOneWidget);
      await tester.enterText(field('Quantity'), '-2');
      await tester.pumpAndSettle();
      expect(find.textContaining('Enter a positive number'), findsOneWidget);
      await tester.enterText(field('Quantity'), '1.123456789');
      await tester.pumpAndSettle();
      expect(find.text('Use at most 8 decimal places.'), findsOneWidget);
      await tester.enterText(field('Price per unit'), '1,5');
      await tester.pumpAndSettle();
      expect(
        find.text('Use digits and a decimal point only, like 1250.50.'),
        findsOneWidget,
      );
      await tester.enterText(field('Quantity'), '5');
      await tester.pumpAndSettle();
      expect(find.textContaining('Use at most 8'), findsNothing);
    });

    testWidgets('letters cannot be typed into a number field', (tester) async {
      await pumpAdd(tester);
      await tester.enterText(field('Quantity'), '1a2b');
      expect(
        tester.widget<TextField>(field('Quantity')).controller!.text,
        '12',
      );
    });

    testWidgets('the form changes with the type', (tester) async {
      await pumpAdd(tester);
      expect(field('Quantity'), findsOneWidget);
      expect(field('Amount'), findsNothing);
      await chooseKind(tester, 'Deposit');
      expect(field('Quantity'), findsNothing);
      expect(field('Amount'), findsOneWidget);
      expect(
        find.widgetWithText(DropdownButtonFormField<String>, 'Investment'),
        findsNothing,
      );
      await chooseKind(tester, 'Dividend');
      expect(field('Amount'), findsOneWidget);
      expect(
        find.widgetWithText(DropdownButtonFormField<String>, 'Investment'),
        findsOneWidget,
      );
    });

    testWidgets('money is limited to the currency decimals', (tester) async {
      await pumpAdd(tester);
      await chooseKind(tester, 'Deposit');
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      await tester.enterText(field('Amount'), '100.123');
      await tester.pumpAndSettle();
      expect(find.text('Use at most 2 decimal places.'), findsOneWidget);
    });

    testWidgets('a full trade: review, save and confirm', (tester) async {
      String? opened;
      var done = 0;
      await pumpAdd(
        tester,
        onOpenEntry: (id) => opened = id,
        onDone: () => done++,
      );
      await chooseFromDropdown(tester, 'Portfolio', 'Growth');
      await chooseFromDropdown(tester, 'Investment', 'Demo Technology ETF');
      await pickToday(tester);
      expect(find.text('Oct 9, 2026'), findsOneWidget);
      await tester.enterText(field('Quantity'), '5');
      await tester.enterText(field('Price per unit'), '190.10');
      await tester.enterText(field('Fee (optional)'), '1.00');
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();

      expect(find.text('Check before saving'), findsOneWidget);
      expect(find.text('Growth'), findsOneWidget);
      expect(find.text('Demo Technology ETF'), findsOneWidget);
      expect(find.text('Oct 9, 2026'), findsOneWidget);
      expect(find.text('5'), findsOneWidget);
      expect(find.text('\$190.10'), findsOneWidget);
      expect(find.textContaining('calculated by the server'), findsOneWidget);
      expect(find.textContaining('DEMO'), findsWidgets);

      await tester.tap(find.text('Save transaction'));
      await tester.pumpAndSettle();
      expect(find.text('Transaction recorded'), findsOneWidget);
      expect(find.textContaining("can't be edited"), findsOneWidget);
      expect(find.byType(TransactionTile), findsOneWidget);

      // It is in the ledger now.
      final growth = await containerOf(tester)
          .read(transactionRepositoryProvider)
          .entries('p-growth');
      expect(growth, hasLength(5));
      expect(growth.last.assetSymbol, 'DEMO-TEC');

      await tester.tap(find.text('View transaction'));
      expect(opened, growth.last.id);
      await tester.tap(find.text('Back to transactions'));
      expect(done, 1);
    });

    testWidgets('Back to edit keeps what was typed', (tester) async {
      await pumpAdd(tester);
      await chooseKind(tester, 'Deposit');
      await chooseFromDropdown(tester, 'Portfolio', 'Retirement');
      await pickToday(tester);
      await tester.enterText(field('Amount'), '250.50');
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      expect(find.text('\$250.50'), findsOneWidget);
      expect(find.textContaining('calculated by the server'), findsNothing);
      await tester.tap(find.text('Back to edit'));
      await tester.pumpAndSettle();
      expect(
        tester.widget<TextField>(field('Amount')).controller!.text,
        '250.50',
      );
    });

    testWidgets('Add another starts an empty form', (tester) async {
      await pumpAdd(tester);
      await chooseKind(tester, 'Deposit');
      await chooseFromDropdown(tester, 'Portfolio', 'Retirement');
      await pickToday(tester);
      await tester.enterText(field('Amount'), '10');
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save transaction'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add another'));
      await tester.pumpAndSettle();
      expect(find.text('Review'), findsOneWidget);
      expect(find.text('Select a date'), findsOneWidget);
      expect(find.text('Portfolio is required.'), findsNothing);
    });

    testWidgets('a failed save keeps the review and offers a retry', (
      tester,
    ) async {
      await pumpAdd(tester);
      await chooseKind(tester, 'Deposit');
      await chooseFromDropdown(tester, 'Portfolio', 'Retirement');
      await pickToday(tester);
      await tester.enterText(field('Amount'), '10');
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      containerOf(tester)
          .read(demoBehaviorProvider.notifier)
          .set(const DemoBehavior(latency: Duration.zero, failNextCalls: 1));
      await tester.tap(find.text('Save transaction'));
      await tester.pumpAndSettle();
      expect(find.textContaining('could not be saved'), findsOneWidget);
      expect(find.text('Check before saving'), findsOneWidget);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.text('Transaction recorded'), findsOneWidget);
    });

    testWidgets('a correction prefills the form from the reversed entry', (
      tester,
    ) async {
      final original = await ProviderContainer(overrides: overrides())
          .read(transactionRepositoryProvider)
          .entry('t-005');
      await pumpAdd(tester, correctionOf: original);
      expect(find.textContaining('corrected version'), findsOneWidget);
      expect(
        tester.widget<TextField>(field('Quantity')).controller!.text,
        '50',
      );
      expect(
        tester.widget<TextField>(field('Price per unit')).controller!.text,
        '98.2',
      );
      expect(find.text('Sep 3, 2026'), findsOneWidget);
      expect(find.text('Retirement'), findsOneWidget);
      expect(find.text('Demo Aggregate Bond Fund'), findsOneWidget);
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      expect(find.text('Check before saving'), findsOneWidget);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'form with errors meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpAdd(tester, mode: mode, scale: scale, dir: dir);
              await tester.tap(find.text('Review'));
              await tester.pumpAndSettle();
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }

    testWidgets('review and confirmation meet the accessibility guidelines', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpAdd(tester, scale: 2.0, onOpenEntry: (_) {}, onDone: () {});
      await chooseKind(tester, 'Deposit');
      await chooseFromDropdown(tester, 'Portfolio', 'Retirement');
      await pickToday(tester);
      await tester.enterText(field('Amount'), '10');
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      await accessibilityChecks(tester);
      await tester.tap(find.text('Save transaction'));
      await tester.pumpAndSettle();
      await accessibilityChecks(tester);
      handle.dispose();
    });
  });

  group('Routes', () {
    testWidgets('list, entry and add are reachable from the portfolio tab', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/portfolio',
        overrides: overrides(),
      );
      await tester.scrollUntilVisible(find.text('Transactions'), 300);
      await tester.ensureVisible(find.text('Transactions'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Transactions'));
      await tester.pumpAndSettle();
      expect(find.byType(TransactionsScreen), findsOneWidget);

      await tester.tap(find.text('Add transaction'));
      await tester.pumpAndSettle();
      expect(find.byType(AddTransactionScreen), findsOneWidget);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.byType(TransactionsScreen), findsOneWidget);

      await tester.tap(find.byType(TransactionTile).first);
      await tester.pumpAndSettle();
      expect(find.byType(TransactionDetailScreen), findsOneWidget);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.byType(TransactionsScreen), findsOneWidget);
    });

    testWidgets('an entry deep link opens it and "add" is not read as an id', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/portfolio/transactions/t-002',
        overrides: overrides(),
      );
      expect(find.byType(TransactionDetailScreen), findsOneWidget);
      expect(find.text('Demo Global Equity Fund (DEMO-GEQ)'), findsOneWidget);
    });

    testWidgets('/portfolio/transactions/add opens the form', (tester) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/portfolio/transactions/add',
        overrides: overrides(),
      );
      expect(find.byType(AddTransactionScreen), findsOneWidget);
      expect(find.byType(TransactionDetailScreen), findsNothing);
    });

    testWidgets('a reversed entry leads to a prefilled corrected entry', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/portfolio/transactions/t-005',
        overrides: overrides(),
      );
      await tester.scrollUntilVisible(find.text('Add corrected entry'), 200);
      await tester.tap(find.text('Add corrected entry'));
      await tester.pumpAndSettle();
      expect(find.byType(AddTransactionScreen), findsOneWidget);
      expect(find.textContaining('corrected version'), findsOneWidget);
    });

    testWidgets('the reversal link navigates between the two entries', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/portfolio/transactions/t-005',
        overrides: overrides(),
      );
      await tester.scrollUntilVisible(find.text('View the reversal'), 200);
      await tester.drag(find.byType(Scrollable).last, const Offset(0, -200));
      await tester.pumpAndSettle();
      await tester.tap(find.text('View the reversal'));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('cancels an earlier entry', skipOffstage: false),
        findsOneWidget,
      );
    });
  });
}

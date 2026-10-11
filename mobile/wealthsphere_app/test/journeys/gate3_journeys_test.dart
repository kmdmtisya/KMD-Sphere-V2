// UX Gate 3 journeys (P07-T09): the user journeys across the Gate 3 screens, run through the real
// router and shell on DEMO data. These run in CI with the widget tests; the device versions are
// in integration_test/app_test.dart.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/design_system/theme/theme.dart';

import '../helpers/demo_overrides.dart';
import '../helpers/pump_router.dart';

Future<void> tapTab(WidgetTester tester, String label) async {
  await tester.tap(
    find.descendant(of: find.byType(NavigationBar), matching: find.text(label)),
  );
  await tester.pumpAndSettle();
}

/// The vertical scrollable of the screen (or sheet) on top. A text field has a horizontal one.
Finder get topScrollable => find
    .byWidgetPredicate(
      (w) => w is Scrollable && w.axisDirection == AxisDirection.down,
    )
    .last;

/// Scrolls the screen on top until [finder] is built and on screen.
Future<void> reveal(WidgetTester tester, Finder finder) async {
  if (finder.evaluate().isEmpty) {
    // It may be above what is built (after coming back to a scrolled list), so start from the top.
    await toTop(tester);
  }
  if (finder.evaluate().isEmpty) {
    await tester.scrollUntilVisible(finder, 300, scrollable: topScrollable);
  }
  await tester.ensureVisible(finder.first);
  await tester.pumpAndSettle();
}

/// Back to the top of the screen on top (a lazy list drops what scrolled far away).
Future<void> toTop(WidgetTester tester) async {
  await tester.drag(topScrollable, const Offset(0, 4000));
  await tester.pumpAndSettle();
}

/// The button called [label] on the card of the idea with [symbol].
Finder buttonOn(String symbol, String label) => find.descendant(
  of: find.ancestor(
    of: find.textContaining(symbol),
    matching: find.byType(OpportunityCard),
  ),
  matching: find.widgetWithText(OutlinedButton, label),
);

/// Lets a snack bar finish, so it does not cover what the next step taps.
Future<void> dismissSnackBar(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 6));
  await tester.pumpAndSettle();
}

Future<void> tap(WidgetTester tester, Finder finder) async {
  await reveal(tester, finder);
  await tester.tap(finder.first);
  await tester.pumpAndSettle();
}

Future<void> back(WidgetTester tester) async {
  await tester.tap(find.byType(BackButton));
  await tester.pumpAndSettle();
}

Finder field(String label) => find.widgetWithText(TextField, label);

Future<void> pickDate(WidgetTester tester) async {
  await tap(tester, find.text('Select a date'));
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  testWidgets(
    'journey 6: holdings, search and filter, an investment, its transactions',
    (tester) async {
      await pumpRouterApp(tester);
      await tapTab(tester, 'Portfolio');
      await tap(tester, find.text('View all holdings'));
      expect(find.textContaining('10 investments'), findsOneWidget);

      await tester.enterText(field('Search investments'), 'bond');
      await tester.pumpAndSettle();
      expect(
        find.text('1 investment, matching bond, sorted by Value, high to low'),
        findsOneWidget,
      );
      await tester.tap(find.byTooltip('Clear search'));
      await tester.pumpAndSettle();

      await tap(tester, find.widgetWithText(ChoiceChip, 'Equities'));
      expect(find.textContaining('in Equities'), findsOneWidget);

      await tap(tester, find.text('DEMO-GEQ'));
      expect(find.text('Demo Global Equity Fund'), findsWidgets);
      expect(
        find.text('Buy'),
        findsNothing,
        reason: 'no trade action on an investment',
      );
      await tap(tester, find.widgetWithText(ChoiceChip, 'Transactions'));
      expect(find.byType(TransactionTile), findsWidgets);

      await tap(tester, find.byType(TransactionTile).first);
      expect(find.text('Transaction'), findsWidgets);
      await back(tester);
      await back(tester);
      expect(
        find.text('Holdings'),
        findsWidgets,
        reason: 'back on the holdings list',
      );
    },
  );

  testWidgets(
    'journey 7: add a transaction, then correct it with a linked reversal',
    (tester) async {
      await pumpRouterApp(tester);
      await tapTab(tester, 'Portfolio');
      await tap(tester, find.text('Transactions'));
      await reveal(tester, find.text('Reversed'));
      expect(
        find.text('Reversed'),
        findsOneWidget,
        reason: 'a corrected entry is marked',
      );

      await tap(tester, find.text('Add transaction'));
      // Invalid first: every problem is in plain words next to its field.
      await tap(tester, find.text('Review'));
      await toTop(tester);
      expect(find.text('Portfolio is required.'), findsOneWidget);
      expect(find.text('Fix 5 fields to continue'), findsOneWidget);

      // Valid now.
      await tap(
        tester,
        find.widgetWithText(DropdownButtonFormField<String>, 'Portfolio'),
      );
      await tester.tap(find.text('Growth').last);
      await tester.pumpAndSettle();
      await tap(
        tester,
        find.widgetWithText(DropdownButtonFormField<String>, 'Investment'),
      );
      await tester.tap(find.text('Demo Technology ETF').last);
      await tester.pumpAndSettle();
      await pickDate(tester);
      await tester.enterText(field('Quantity'), '5');
      await tester.enterText(field('Price per unit'), '190.10');
      await tap(tester, find.text('Review'));
      expect(find.text('Check before saving'), findsOneWidget);
      await tap(tester, find.text('Save transaction'));
      expect(find.text('Transaction recorded'), findsOneWidget);

      // Open it and correct it: a reversal is added, nothing is edited.
      await tap(tester, find.text('View transaction'));
      await tap(tester, find.text('Correct this entry'));
      await tester.tap(find.text('Add reversal'));
      await tester.pumpAndSettle();
      await toTop(tester);
      expect(
        find.text('Reversal added. The entry is now marked as reversed.'),
        findsOneWidget,
      );
      await tap(tester, find.text('Add corrected entry'));
      expect(find.textContaining('corrected version'), findsOneWidget);
      expect(
        tester.widget<TextField>(field('Quantity')).controller!.text,
        '5',
        reason: 'the corrected entry starts from the old values',
      );
    },
  );

  testWidgets('journey 8: goals, add one with validation, view and edit it', (
    tester,
  ) async {
    await pumpRouterApp(tester);
    await tapTab(tester, 'Goals');
    expect(
      find.text('3 of 4 goals on track under your assumptions'),
      findsOneWidget,
    );

    await tap(tester, find.text('Add goal'));
    await tap(tester, find.text('Save goal'));
    await toTop(tester);
    expect(find.text('Enter a name for the goal.'), findsOneWidget);
    expect(find.text('Choose a target date.'), findsOneWidget);

    await tester.enterText(field('Goal name'), 'Car');
    await tester.enterText(field('Target amount'), '20000');
    await pickDate(tester);
    await tester.enterText(field('Contribution'), '300');
    await tester.enterText(field('Base annual return (%)'), '5');
    await tap(tester, find.text('Save goal'));
    // The new goal opens with no invented estimate.
    expect(find.text('Car'), findsWidgets);
    expect(find.textContaining("The demo can't calculate it"), findsOneWidget);

    await dismissSnackBar(tester);
    await tap(tester, find.text('Edit goal'));
    await tester.enterText(field('Contribution'), '450');
    await tap(tester, find.text('Save goal'));
    await dismissSnackBar(tester);
    await reveal(tester, find.text('Your assumptions'));
    expect(find.text('Your assumptions'), findsOneWidget);

    await tap(tester, find.text('Ask AI about this goal'));
    expect(
      find.textContaining('Goal '),
      findsWidgets,
      reason: 'AI opens scoped to the goal',
    );
  });

  testWidgets(
    'journey 9: Portfolio Doctor, then opportunities, compare and simulate',
    (tester) async {
      await pumpRouterApp(tester);
      await tapTab(tester, 'AI Wealth');

      await tester.tap(find.byTooltip('Portfolio Doctor'));
      await tester.pumpAndSettle();
      expect(find.text('Portfolio health'), findsOneWidget);
      await tap(tester, find.widgetWithText(ChoiceChip, 'Currency (1)'));
      await tap(tester, find.textContaining('weakened 10%'));
      expect(find.text('What it would mean'), findsOneWidget);
      await tap(tester, find.text('Close'));
      await back(tester);

      await tester.tap(find.byTooltip('Investment opportunities'));
      await tester.pumpAndSettle();
      expect(find.textContaining('not live market data'), findsOneWidget);
      await tap(tester, find.widgetWithText(FilledButton, 'Research').first);
      expect(find.text('What it is'), findsOneWidget);
      await tap(tester, find.text('Close'));

      await tap(tester, buttonOn('DEMO-GLB', 'Compare'));
      await tap(tester, buttonOn('DEMO-DVI', 'Compare'));
      await tap(tester, find.text('Compare 2 selected'));
      expect(find.text('Compare ideas'), findsOneWidget);
      expect(find.textContaining('not a ranking'), findsOneWidget);
      await back(tester);

      await tap(tester, buttonOn('DEMO-GLB', 'Simulate'));
      expect(
        find.textContaining('Pre-filled from Demo Global Index ETF (DEMO)'),
        findsOneWidget,
      );
      await tap(tester, find.byKey(const ValueKey('calculate')));
      expect(find.text('Wealth forecast'), findsWidgets);
    },
  );

  testWidgets('journey 10: More, net worth, income, settings and theme', (
    tester,
  ) async {
    // The real app (not the router harness), so the theme setting is applied to the screens.
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...demoOverrides(),
          preferencesStoreProvider.overrideWithValue(
            InMemoryPreferencesStore(),
          ),
          initialThemeModeProvider.overrideWithValue(ThemeMode.system),
        ],
        child: const WealthSphereApp(),
      ),
    );
    await tester.pumpAndSettle();
    await tapTab(tester, 'More');
    expect(find.text('Coming soon'), findsWidgets);

    await tap(tester, find.text('Net worth'));
    expect(find.text('\$168,286.35'), findsOneWidget);
    await back(tester);
    await tap(tester, find.text('Income'));
    expect(find.text('\$1,245.30'), findsOneWidget);
    await back(tester);

    await tap(tester, find.text('Settings'));
    Brightness shown() =>
        Theme.of(tester.element(find.byType(Scaffold).last)).brightness;
    expect(shown(), Brightness.light);
    await tap(tester, find.text('Dark'));
    expect(shown(), Brightness.dark);
    await tap(tester, find.text('Light'));
    expect(shown(), Brightness.light);
    await back(tester);
    expect(find.text('Your wealth'), findsOneWidget);
  });
}

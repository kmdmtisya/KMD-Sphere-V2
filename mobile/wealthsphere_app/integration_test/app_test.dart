// Integration journeys for UX Gate 2 (P03-T07, UI plan step 15) and UX Gate 3 (P07-T09).
//
// These run the real app (DEMO data, real asset bundle, real on-device SharedPreferences) on an
// attached device or emulator, not the synchronous test harness used by the widget tests:
//
//   flutter test integration_test/app_test.dart -d <device-id>
//
// Journeys 1 to 5 match the five listed in docs/UI_EXECUTION_PLAN.md step 15. Journeys 6 to 10
// cover the Gate 3 screens; the same flows also run in CI as widget tests
// (test/journeys/gate3_journeys_test.dart).
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wealthsphere_app/app/app.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/design_system/theme/theme.dart';

void ensureBinding() =>
    IntegrationTestWidgetsFlutterBinding.ensureInitialized();

/// Builds the real app exactly as `main()` does, on real on-device SharedPreferences, so a fresh
/// call after one has already run reads back whatever the previous call persisted — the closest
/// thing to an app restart available inside one test process.
Future<void> launchApp(WidgetTester tester) async {
  await initializeDateLabels();
  final store = SharedPreferencesStore(await SharedPreferences.getInstance());
  final themeMode = await readThemeMode(store);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        preferencesStoreProvider.overrideWithValue(store),
        initialThemeModeProvider.overrideWithValue(themeMode),
      ],
      child: const WealthSphereApp(),
    ),
  );
  await tester.pumpAndSettle(const Duration(seconds: 2));
}

/// Scrolls [finder] into view and taps it, waiting for the result to settle.
Future<void> reveal(WidgetTester tester, Finder finder) async {
  if (finder.evaluate().isEmpty) {
    // Not built yet (lazy list): scroll the screen's main scrollable until it is.
    await tester.scrollUntilVisible(
      finder,
      300,
      scrollable: find.byType(Scrollable).first,
    );
  }
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

Future<void> revealAndTap(WidgetTester tester, Finder finder) async {
  await reveal(tester, finder);
  await tester.tap(finder);
  await tester.pumpAndSettle(const Duration(seconds: 1));
}

Future<void> tapTab(WidgetTester tester, String label) async {
  await tester.tap(
    find.descendant(of: find.byType(NavigationBar), matching: find.text(label)),
  );
  await tester.pumpAndSettle(const Duration(seconds: 1));
}

Future<void> waitForText(
  WidgetTester tester,
  String text, {
  int seconds = 5,
}) async {
  for (var i = 0; i < seconds; i++) {
    if (find.text(text).evaluate().isNotEmpty) return;
    await tester.pump(const Duration(seconds: 1));
  }
  await tester.pumpAndSettle();
}

// ------------------------------------------------------------------------- Gate 3 helpers

/// The vertical scrollable of the screen (or sheet) on top. A text field has a horizontal one.
Finder get topScrollable => find
    .byWidgetPredicate(
      (w) => w is Scrollable && w.axisDirection == AxisDirection.down,
    )
    .last;

/// Back to the top of the screen on top (a lazy list drops what scrolled far away).
Future<void> toTop(WidgetTester tester) async {
  await tester.drag(topScrollable, const Offset(0, 4000));
  await tester.pumpAndSettle();
}

/// Scrolls the screen on top until [finder] is built and fully on screen.
Future<void> bring(WidgetTester tester, Finder finder) async {
  if (finder.evaluate().isEmpty) await toTop(tester);
  if (finder.evaluate().isEmpty) {
    await tester.scrollUntilVisible(finder, 300, scrollable: topScrollable);
  }
  await tester.ensureVisible(finder.first);
  await tester.pumpAndSettle();
}

Future<void> press(WidgetTester tester, Finder finder) async {
  await bring(tester, finder);
  await tester.tap(finder.first);
  await tester.pumpAndSettle(const Duration(seconds: 1));
}

Future<void> goBack(WidgetTester tester) async {
  await tester.tap(find.byType(BackButton));
  await tester.pumpAndSettle(const Duration(seconds: 1));
}

Finder textField(String label) => find.widgetWithText(TextField, label);

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

Future<void> pickTodayOrLater(WidgetTester tester) async {
  await press(tester, find.text('Select a date'));
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
}

void main() {
  ensureBinding();

  setUp(() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
  });

  testWidgets('journey 1: launch, visit all five tabs, state preserved', (
    tester,
  ) async {
    await launchApp(tester);
    expect(find.text('Total wealth'), findsOneWidget, reason: 'opens on Home');

    for (final label in ['Portfolio', 'AI Wealth', 'Goals', 'More', 'Home']) {
      await tapTab(tester, label);
      expect(tester.takeException(), isNull, reason: label);
    }
    expect(find.text('Total wealth'), findsOneWidget, reason: 'back on Home');

    // Push a nested screen, leave the tab, come back: the stack is still there.
    await tapTab(tester, 'Portfolio');
    await revealAndTap(tester, find.text('View all holdings'));
    expect(find.text('Holdings'), findsWidgets);

    await tapTab(tester, 'Home');
    await tapTab(tester, 'Portfolio');
    expect(find.text('Holdings'), findsWidgets, reason: 'tab stack preserved');
  });

  testWidgets(
    'journey 2: customise Home, reorder and hide, survives a restart',
    (tester) async {
      await launchApp(tester);
      await tester.tap(find.byTooltip('Customise'));
      await tester.pumpAndSettle();
      expect(find.text('Customise home'), findsOneWidget);

      await tester.tap(find.byIcon(Icons.arrow_downward_rounded).first);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Switch).last); // hide Goals
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Done'));
      await tester.pumpAndSettle();
      expect(find.text('Home deposit'), findsNothing, reason: 'goals hidden');

      // "Restart": a fresh widget tree reading the same on-device storage.
      await tester.pumpWidget(const SizedBox());
      await launchApp(tester);
      expect(
        find.text('Home deposit'),
        findsNothing,
        reason: 'hidden section stays hidden after restart',
      );
    },
  );

  testWidgets(
    'journey 3: switch portfolio, change period, view holdings, back',
    (tester) async {
      await launchApp(tester);
      await tapTab(tester, 'Portfolio');
      expect(find.text('All portfolios (consolidated)'), findsOneWidget);

      await tester.tap(find.text('All portfolios (consolidated)'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Growth'));
      await tester.pumpAndSettle();
      expect(find.text('Growth'), findsWidgets);
      expect(find.text(r'$31,940.15'), findsWidgets);

      await tester.tap(find.text('6M'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await revealAndTap(tester, find.text('View all holdings'));
      expect(find.text('Holdings'), findsWidgets);

      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.text('Growth'), findsWidgets, reason: 'back on Portfolio');
    },
  );

  testWidgets(
    'journey 4: calculator validation, forecast, scenario, real values, ask AI',
    (tester) async {
      await launchApp(tester);
      await tapTab(tester, 'More');
      await tester.tap(find.text('Compounding calculator'));
      await tester.pumpAndSettle();

      // Invalid first: clear the required years field and try to submit.
      await tester.enterText(find.byKey(const ValueKey('field-years')), '');
      await tester.pump();
      await revealAndTap(tester, find.byKey(const ValueKey('calculate')));
      expect(find.text('Enter a value.'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('calculate')),
        findsOneWidget,
        reason: 'invalid input keeps the user on the calculator',
      );

      // Now valid: restore a value and submit.
      await tester.enterText(find.byKey(const ValueKey('field-years')), '20');
      await tester.pump();
      await revealAndTap(tester, find.byKey(const ValueKey('calculate')));
      expect(
        find.text('Scenarios'),
        findsOneWidget,
        reason: 'on the Forecast screen',
      );

      await tester.tap(find.byKey(const ValueKey('scenario-growth')));
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);

      await tester.tap(find.text("Today's money"));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await revealAndTap(tester, find.text('Ask AI about this forecast'));
      expect(find.text('Context: This forecast'), findsOneWidget);
    },
  );

  testWidgets(
    'journey 5: AI suggested question streams an answer, retry on failure',
    (tester) async {
      await launchApp(tester);
      await tapTab(tester, 'AI Wealth');
      expect(
        find.text('Demo responses, not connected to your data.'),
        findsOneWidget,
      );

      await tester.tap(find.text('How is my portfolio performing?'));
      await waitForText(tester, 'AI interpretation', seconds: 10);
      expect(find.text('Observed data'), findsOneWidget);
      expect(find.text('Calculated'), findsOneWidget);
      expect(find.text('Assumptions'), findsOneWidget);
      expect(find.text('AI interpretation'), findsOneWidget);

      await tester.enterText(
        find.byType(TextField),
        'Show me a failing request (demo)',
      );
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await waitForText(
        tester,
        'The assistant could not complete this request. Please try again.',
      );
      await reveal(tester, find.text('Try again'));
      expect(find.text('Try again'), findsOneWidget);

      await tester.tap(find.text('Try again'));
      await waitForText(
        tester,
        'The assistant could not complete this request. Please try again.',
      );
      expect(
        find.text(
          'The assistant could not complete this request. Please try again.',
        ),
        findsOneWidget,
        reason: 'the failure script fails the same way on retry (by design)',
      );
    },
  );

  testWidgets(
    'journey 6: holdings, search and filter, an investment, its transactions',
    (tester) async {
      await launchApp(tester);
      await tapTab(tester, 'Portfolio');
      await revealAndTap(tester, find.text('View all holdings'));
      expect(find.textContaining('10 investments'), findsOneWidget);

      await tester.enterText(textField('Search investments'), 'bond');
      await tester.pumpAndSettle();
      expect(find.textContaining('1 investment'), findsOneWidget);
      await tester.tap(find.byTooltip('Clear search'));
      await tester.pumpAndSettle();

      await press(tester, find.widgetWithText(ChoiceChip, 'Equities'));
      expect(find.textContaining('in Equities'), findsOneWidget);

      await press(tester, find.text('DEMO-GEQ'));
      expect(find.text('Demo Global Equity Fund'), findsWidgets);
      expect(find.text('Buy'), findsNothing, reason: 'no trade action');
      await press(tester, find.widgetWithText(ChoiceChip, 'Transactions'));
      expect(find.byType(TransactionTile), findsWidgets);

      await press(tester, find.byType(TransactionTile).first);
      await goBack(tester);
      expect(find.text('Demo Global Equity Fund'), findsWidgets);
      await goBack(tester);
      expect(find.text('Holdings'), findsWidgets);
    },
  );

  testWidgets(
    'journey 7: add a transaction, then correct it with a linked reversal',
    (tester) async {
      await launchApp(tester);
      await tapTab(tester, 'Portfolio');
      await press(tester, find.text('Transactions'));
      await bring(tester, find.text('Reversed'));
      expect(find.text('Reversed'), findsOneWidget);

      await press(tester, find.text('Add transaction'));
      await press(tester, find.text('Review'));
      await toTop(tester);
      expect(find.text('Portfolio is required.'), findsOneWidget);

      await press(
        tester,
        find.widgetWithText(DropdownButtonFormField<String>, 'Portfolio'),
      );
      await tester.tap(find.text('Growth').last);
      await tester.pumpAndSettle();
      await press(
        tester,
        find.widgetWithText(DropdownButtonFormField<String>, 'Investment'),
      );
      await tester.tap(find.text('Demo Technology ETF').last);
      await tester.pumpAndSettle();
      await pickTodayOrLater(tester);
      await tester.enterText(textField('Quantity'), '5');
      await tester.enterText(textField('Price per unit'), '190.10');
      await press(tester, find.text('Review'));
      expect(find.text('Check before saving'), findsOneWidget);
      await press(tester, find.text('Save transaction'));
      expect(find.text('Transaction recorded'), findsOneWidget);

      await press(tester, find.text('View transaction'));
      await press(tester, find.text('Correct this entry'));
      await tester.tap(find.text('Add reversal'));
      await tester.pumpAndSettle();
      await toTop(tester);
      expect(
        find.text('Reversal added. The entry is now marked as reversed.'),
        findsOneWidget,
      );
      await press(tester, find.text('Add corrected entry'));
      expect(find.textContaining('corrected version'), findsOneWidget);
    },
  );

  testWidgets('journey 8: goals, add one with validation, view and edit it', (
    tester,
  ) async {
    await launchApp(tester);
    await tapTab(tester, 'Goals');
    expect(
      find.text('3 of 4 goals on track under your assumptions'),
      findsOneWidget,
    );

    await press(tester, find.text('Add goal'));
    await press(tester, find.text('Save goal'));
    await toTop(tester);
    expect(find.text('Enter a name for the goal.'), findsOneWidget);

    await tester.enterText(textField('Goal name'), 'Car');
    await tester.enterText(textField('Target amount'), '20000');
    await pickTodayOrLater(tester);
    await tester.enterText(textField('Contribution'), '300');
    await tester.enterText(textField('Base annual return (%)'), '5');
    await press(tester, find.text('Save goal'));
    expect(find.textContaining("The demo can't calculate it"), findsOneWidget);

    await dismissSnackBar(tester);
    await press(tester, find.text('Edit goal'));
    await tester.enterText(textField('Contribution'), '450');
    await press(tester, find.text('Save goal'));
    await dismissSnackBar(tester);
    await bring(tester, find.text('Your assumptions'));
    expect(find.text('Your assumptions'), findsOneWidget);
  });

  testWidgets(
    'journey 9: Portfolio Doctor, then opportunities, compare and simulate',
    (tester) async {
      await launchApp(tester);
      await tapTab(tester, 'AI Wealth');

      await tester.tap(find.byTooltip('Portfolio Doctor'));
      await tester.pumpAndSettle(const Duration(seconds: 1));
      expect(find.text('Portfolio health'), findsOneWidget);
      await press(tester, find.widgetWithText(ChoiceChip, 'Currency (1)'));
      await press(tester, find.textContaining('weakened 10%'));
      expect(find.text('What it would mean'), findsOneWidget);
      await press(tester, find.text('Close'));
      await goBack(tester);

      await tester.tap(find.byTooltip('Investment opportunities'));
      await tester.pumpAndSettle(const Duration(seconds: 1));
      expect(find.textContaining('not live market data'), findsOneWidget);
      await press(tester, find.widgetWithText(FilledButton, 'Research').first);
      expect(find.text('What it is'), findsOneWidget);
      await press(tester, find.text('Close'));

      await press(tester, buttonOn('DEMO-GLB', 'Compare'));
      await press(tester, buttonOn('DEMO-DVI', 'Compare'));
      await press(tester, find.text('Compare 2 selected'));
      expect(find.text('Compare ideas'), findsOneWidget);
      await goBack(tester);

      await press(tester, buttonOn('DEMO-GLB', 'Simulate'));
      expect(
        find.textContaining('Pre-filled from Demo Global Index ETF (DEMO)'),
        findsOneWidget,
      );
      await press(tester, find.byKey(const ValueKey('calculate')));
      expect(find.text('Wealth forecast'), findsWidgets);
    },
  );

  testWidgets('journey 10: More, net worth, income, settings and theme', (
    tester,
  ) async {
    await launchApp(tester);
    await tapTab(tester, 'More');
    expect(find.text('Coming soon'), findsWidgets);

    await press(tester, find.text('Net worth'));
    expect(find.text(r'$168,286.35'), findsOneWidget);
    await goBack(tester);
    await press(tester, find.text('Income'));
    expect(find.text(r'$1,245.30'), findsOneWidget);
    await goBack(tester);

    await press(tester, find.text('Settings'));
    Brightness shown() =>
        Theme.of(tester.element(find.byType(Scaffold).last)).brightness;
    // The device may be in dark mode, so choose both explicitly.
    await press(tester, find.text('Light'));
    expect(shown(), Brightness.light);
    await press(tester, find.text('Dark'));
    expect(shown(), Brightness.dark);
    await press(tester, find.text('System'));
    await goBack(tester);
    // Back on More (scrolled to where Settings is).
    expect(find.text('Settings'), findsOneWidget);
  });
}

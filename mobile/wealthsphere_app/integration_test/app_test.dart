// Integration journeys for UX Gate 2 (P03-T07, UI plan step 15).
//
// These run the real app (DEMO data, real asset bundle, real on-device SharedPreferences) on an
// attached device or emulator, not the synchronous test harness used by the widget tests:
//
//   flutter test integration_test/app_test.dart -d <device-id>
//
// Each journey matches one of the five listed in docs/UI_EXECUTION_PLAN.md step 15.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wealthsphere_app/app/app.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
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
}

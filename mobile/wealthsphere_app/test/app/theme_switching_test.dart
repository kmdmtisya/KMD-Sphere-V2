import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/shared/design_system/theme/theme.dart';
import 'package:wealthsphere_app/shared/design_system/tokens/tokens.dart';

import '../helpers/demo_overrides.dart';

Widget appWith(
  PreferencesStore store, {
  ThemeMode initial = ThemeMode.system,
}) => ProviderScope(
  overrides: [
    ...demoOverrides(),
    preferencesStoreProvider.overrideWithValue(store),
    initialThemeModeProvider.overrideWithValue(initial),
  ],
  child: const WealthSphereApp(),
);

Brightness shownBrightness(WidgetTester tester) =>
    Theme.of(tester.element(find.byType(Scaffold).first)).brightness;

/// The theme switch lives on the More tab (temporary Settings placeholder).
Future<void> openMore(WidgetTester tester) async {
  await tester.tap(find.text('More'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'light, dark and system themes switch at runtime and drive the real colours',
    (tester) async {
      final store = InMemoryPreferencesStore();
      await tester.pumpWidget(appWith(store));
      await tester.pumpAndSettle();
      await openMore(tester);

      // The test platform is light, so "system" shows the light theme.
      expect(shownBrightness(tester), Brightness.light);
      final scaffold = tester.widget<Scaffold>(find.byType(Scaffold).first);
      expect(
        Theme.of(tester.element(find.byType(Scaffold).first))
            .scaffoldBackgroundColor,
        WealthColors.light.scaffold,
      );
      expect(scaffold, isNotNull);

      await tester.tap(find.text('Dark'));
      await tester.pumpAndSettle();
      expect(shownBrightness(tester), Brightness.dark);
      expect(
        Theme.of(tester.element(find.byType(Scaffold).first))
            .scaffoldBackgroundColor,
        WealthColors.dark.scaffold,
      );
      expect(store.values[themeModePreferenceKey], 'dark');

      await tester.tap(find.text('Light'));
      await tester.pumpAndSettle();
      expect(shownBrightness(tester), Brightness.light);
      expect(store.values[themeModePreferenceKey], 'light');

      await tester.tap(find.text('System'));
      await tester.pumpAndSettle();
      expect(store.values[themeModePreferenceKey], 'system');
    },
  );

  testWidgets('"system" follows the device brightness', (tester) async {
    tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    addTearDown(tester.platformDispatcher.clearAllTestValues);
    await tester.pumpWidget(appWith(InMemoryPreferencesStore()));
    await tester.pumpAndSettle();
    expect(shownBrightness(tester), Brightness.dark);
  });

  testWidgets(
    'the saved choice is applied on the very first frame after a restart',
    (tester) async {
      final store = InMemoryPreferencesStore({themeModePreferenceKey: 'dark'});
      final restored = await readThemeMode(store);
      await tester.pumpWidget(appWith(store, initial: restored));
      // No settling: the first frame already uses the stored mode (no light flash).
      expect(shownBrightness(tester), Brightness.dark);
    },
  );

  testWidgets(
    'the selected mode is marked with a check mark and exposed as selected to screen readers',
    (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(appWith(InMemoryPreferencesStore()));
      await tester.pumpAndSettle();
      await openMore(tester);

      expect(find.byIcon(Icons.check), findsOneWidget);
      expect(
        tester.getSemantics(find.bySemanticsLabel('System')),
        isSemantics(label: 'System', hasSelectedState: true, isSelected: true),
      );
      expect(
        tester.getSemantics(find.bySemanticsLabel('Dark')),
        isSemantics(label: 'Dark', hasSelectedState: true, isSelected: false),
      );
      handle.dispose();
    },
  );

  testWidgets(
    'the placeholder screen fits a small phone at 2.0x text without overflow',
    (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
        tester.platformDispatcher.clearAllTestValues();
      });
      await tester.pumpWidget(appWith(InMemoryPreferencesStore()));
      await tester.pumpAndSettle();
      await openMore(tester);
      expect(tester.takeException(), isNull);
      expect(find.text('Dark'), findsOneWidget);
    },
  );
}

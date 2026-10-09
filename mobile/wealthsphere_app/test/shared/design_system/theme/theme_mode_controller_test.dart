import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/shared/design_system/theme/theme.dart';

class _ThrowingStore implements PreferencesStore {
  @override
  Future<String?> getString(String key) async =>
      throw StateError('read failed');

  @override
  Future<void> setString(String key, String value) async =>
      throw StateError('write failed');

  @override
  Future<void> remove(String key) async => throw StateError('remove failed');
}

ProviderContainer containerFor(PreferencesStore store, {ThemeMode? initial}) {
  final container = ProviderContainer(
    overrides: [
      preferencesStoreProvider.overrideWithValue(store),
      if (initial != null) initialThemeModeProvider.overrideWithValue(initial),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

void main() {
  group('storage mapping', () {
    test('round-trips every mode', () {
      for (final mode in ThemeMode.values) {
        expect(themeModeFromStorage(themeModeToStorage(mode)), mode);
      }
    });

    test('unknown, empty or corrupt values mean "follow the system"', () {
      for (final bad in [null, '', 'purple', 'DARK', ' dark', 'null', '1']) {
        expect(themeModeFromStorage(bad), ThemeMode.system, reason: '$bad');
      }
    });
  });

  group('readThemeMode', () {
    test('empty store -> system', () async {
      expect(await readThemeMode(InMemoryPreferencesStore()), ThemeMode.system);
    });

    test('reads the saved value', () async {
      final store = InMemoryPreferencesStore({themeModePreferenceKey: 'dark'});
      expect(await readThemeMode(store), ThemeMode.dark);
    });

    test('a failing store is not fatal', () async {
      expect(await readThemeMode(_ThrowingStore()), ThemeMode.system);
    });
  });

  group('ThemeModeController', () {
    test('starts from the initial mode (system by default)', () {
      expect(
        containerFor(InMemoryPreferencesStore()).read(themeModeProvider),
        ThemeMode.system,
      );
      final dark = containerFor(
        InMemoryPreferencesStore(),
        initial: ThemeMode.dark,
      );
      expect(dark.read(themeModeProvider), ThemeMode.dark);
    });

    test('setMode changes the state immediately and persists it', () async {
      final store = InMemoryPreferencesStore();
      final container = containerFor(store);
      final states = <ThemeMode>[];
      container.listen(themeModeProvider, (_, next) => states.add(next));

      await container.read(themeModeProvider.notifier).setMode(ThemeMode.dark);
      expect(container.read(themeModeProvider), ThemeMode.dark);
      expect(store.values[themeModePreferenceKey], 'dark');

      await container.read(themeModeProvider.notifier).setMode(ThemeMode.light);
      expect(store.values[themeModePreferenceKey], 'light');
      await container
          .read(themeModeProvider.notifier)
          .setMode(ThemeMode.system);
      expect(store.values[themeModePreferenceKey], 'system');
      expect(states, [ThemeMode.dark, ThemeMode.light, ThemeMode.system]);
    });

    test('the choice survives an app restart', () async {
      final store = InMemoryPreferencesStore();
      await containerFor(store)
          .read(themeModeProvider.notifier)
          .setMode(ThemeMode.dark);

      // "Restart": a brand-new container that starts from what main() reads from storage.
      final restored = await readThemeMode(store);
      final second = containerFor(store, initial: restored);
      expect(second.read(themeModeProvider), ThemeMode.dark);
    });

    test('a storage failure never blocks the change', () async {
      final container = containerFor(_ThrowingStore());
      await container.read(themeModeProvider.notifier).setMode(ThemeMode.light);
      expect(container.read(themeModeProvider), ThemeMode.light);
    });

    test('selecting the current mode again is harmless', () async {
      final store = InMemoryPreferencesStore();
      final container = containerFor(store, initial: ThemeMode.dark);
      await container.read(themeModeProvider.notifier).setMode(ThemeMode.dark);
      expect(container.read(themeModeProvider), ThemeMode.dark);
      expect(store.values[themeModePreferenceKey], 'dark');
    });
  });

  group('SharedPreferencesStore', () {
    test('stores, reads and removes strings', () async {
      SharedPreferences.setMockInitialValues({});
      final store = SharedPreferencesStore(
        await SharedPreferences.getInstance(),
      );
      expect(await store.getString('k'), isNull);
      await store.setString('k', 'v');
      expect(await store.getString('k'), 'v');
      await store.setString('k', 'w');
      expect(await store.getString('k'), 'w');
      await store.remove('k');
      expect(await store.getString('k'), isNull);
    });

    test('works end-to-end with the theme controller', () async {
      SharedPreferences.setMockInitialValues({});
      final store = SharedPreferencesStore(
        await SharedPreferences.getInstance(),
      );
      await containerFor(store)
          .read(themeModeProvider.notifier)
          .setMode(ThemeMode.dark);
      expect(await readThemeMode(store), ThemeMode.dark);
    });
  });
}

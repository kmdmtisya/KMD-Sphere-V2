import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/preferences/preferences_store.dart';

const String themeModePreferenceKey = 'ui.theme_mode';

String themeModeToStorage(ThemeMode mode) => switch (mode) {
  ThemeMode.system => 'system',
  ThemeMode.light => 'light',
  ThemeMode.dark => 'dark',
};

/// Parses a stored value. Anything unknown (corrupt, from a future version) means "follow the
/// system", never a crash.
ThemeMode themeModeFromStorage(String? value) => switch (value) {
  'light' => ThemeMode.light,
  'dark' => ThemeMode.dark,
  _ => ThemeMode.system,
};

/// Reads the saved theme mode. Called once in `main()` so the first frame already uses it.
Future<ThemeMode> readThemeMode(PreferencesStore store) async {
  try {
    return themeModeFromStorage(await store.getString(themeModePreferenceKey));
  } on Object {
    return ThemeMode.system;
  }
}

/// The theme mode known at start-up (see [readThemeMode]). Overridden in `main()`.
final initialThemeModeProvider = Provider<ThemeMode>((ref) => ThemeMode.system);

/// Current theme mode: system, light or dark. Changes apply immediately and are persisted on a
/// best-effort basis (a storage failure never prevents the change).
class ThemeModeController extends Notifier<ThemeMode> {
  @override
  ThemeMode build() => ref.watch(initialThemeModeProvider);

  Future<void> setMode(ThemeMode mode) async {
    state = mode;
    try {
      await ref
          .read(preferencesStoreProvider)
          .setString(themeModePreferenceKey, themeModeToStorage(mode));
    } on Object {
      // Preference persistence is a convenience; the in-memory state is already updated.
    }
  }
}

final themeModeProvider = NotifierProvider<ThemeModeController, ThemeMode>(
  ThemeModeController.new,
);

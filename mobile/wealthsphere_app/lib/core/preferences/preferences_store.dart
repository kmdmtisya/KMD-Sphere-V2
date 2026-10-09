import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Small key-value store for **UI preferences only** (theme mode, dashboard layout, ...).
///
/// Never put credentials, tokens or financial data here: tokens belong in secure storage and
/// financial data comes from the backend. The interface exists so the real storage can be
/// replaced by an in-memory one in tests and demo mode.
abstract interface class PreferencesStore {
  Future<String?> getString(String key);
  Future<void> setString(String key, String value);
  Future<void> remove(String key);
}

/// [PreferencesStore] backed by `shared_preferences`.
class SharedPreferencesStore implements PreferencesStore {
  const SharedPreferencesStore(this._prefs);

  final SharedPreferences _prefs;

  @override
  Future<String?> getString(String key) async => _prefs.getString(key);

  @override
  Future<void> setString(String key, String value) async {
    await _prefs.setString(key, value);
  }

  @override
  Future<void> remove(String key) async {
    await _prefs.remove(key);
  }
}

/// Volatile store for tests and previews.
class InMemoryPreferencesStore implements PreferencesStore {
  InMemoryPreferencesStore([Map<String, String>? initial])
    : values = {...?initial};

  final Map<String, String> values;

  @override
  Future<String?> getString(String key) async => values[key];

  @override
  Future<void> setString(String key, String value) async => values[key] = value;

  @override
  Future<void> remove(String key) async => values.remove(key);
}

/// The active store. `main()` overrides it with [SharedPreferencesStore]; the default is
/// in-memory so widgets and tests that do not care about persistence just work.
final preferencesStoreProvider = Provider<PreferencesStore>(
  (ref) => InMemoryPreferencesStore(),
);

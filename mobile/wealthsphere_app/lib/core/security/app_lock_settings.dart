import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../preferences/preferences_store.dart';

/// How long the app may stay in the background before it locks.
enum LockTimeout {
  immediately(Duration.zero),
  oneMinute(Duration(minutes: 1)),
  fiveMinutes(Duration(minutes: 5));

  const LockTimeout(this.duration);

  final Duration duration;
}

/// The app-lock preference. A preference, not a secret: it lives in [PreferencesStore].
@immutable
class AppLockSettings {
  const AppLockSettings({
    this.enabled = true,
    this.timeout = LockTimeout.immediately,
  });

  /// On by default: WealthSphere shows financial data.
  final bool enabled;
  final LockTimeout timeout;

  /// Locks after this long without any touch while the app is open.
  static const idleTimeout = Duration(minutes: 5);

  AppLockSettings copyWith({bool? enabled, LockTimeout? timeout}) =>
      AppLockSettings(
        enabled: enabled ?? this.enabled,
        timeout: timeout ?? this.timeout,
      );

  String toStorage() =>
      jsonEncode({'enabled': enabled, 'timeout': timeout.name});

  /// Unknown or damaged values fall back to the safe default (locking on).
  static AppLockSettings fromStorage(String? raw) {
    if (raw == null) return const AppLockSettings();
    try {
      final json = jsonDecode(raw) as Map<String, Object?>;
      return AppLockSettings(
        enabled: json['enabled'] != false,
        timeout: LockTimeout.values.firstWhere(
          (t) => t.name == json['timeout'],
          orElse: () => LockTimeout.immediately,
        ),
      );
    } on Object {
      return const AppLockSettings();
    }
  }

  @override
  bool operator ==(Object other) =>
      other is AppLockSettings &&
      other.enabled == enabled &&
      other.timeout == timeout;

  @override
  int get hashCode => Object.hash(enabled, timeout);
}

const appLockPreferenceKey = 'ws.appLock.v1';

Future<AppLockSettings> readAppLockSettings(PreferencesStore store) async {
  try {
    return AppLockSettings.fromStorage(
      await store.getString(appLockPreferenceKey),
    );
  } on Object {
    return const AppLockSettings();
  }
}

/// The settings known at start-up. Overridden in `main()`.
final initialAppLockSettingsProvider = Provider<AppLockSettings>(
  (ref) => const AppLockSettings(),
);

class AppLockSettingsController extends Notifier<AppLockSettings> {
  @override
  AppLockSettings build() => ref.watch(initialAppLockSettingsProvider);

  Future<void> set(AppLockSettings settings) async {
    state = settings;
    try {
      await ref
          .read(preferencesStoreProvider)
          .setString(appLockPreferenceKey, settings.toStorage());
    } on Object {
      // Persistence is best effort; the in-memory setting applies now.
    }
  }
}

final appLockSettingsProvider =
    NotifierProvider<AppLockSettingsController, AppLockSettings>(
      AppLockSettingsController.new,
    );

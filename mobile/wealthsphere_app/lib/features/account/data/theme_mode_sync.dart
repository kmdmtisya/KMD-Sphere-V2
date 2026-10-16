import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/auth/auth_controller.dart';
import '../../../core/data/demo_support.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/design_system/theme/theme.dart';

/// Where the appearance choice is kept besides the device: the account's `theme_mode` in
/// `/me/preferences` (DEC-40, P14-T18), so Light, Dark or System follows the user between the
/// phone and the web portal.
abstract interface class ThemeModeSync {
  /// The account's choice, or null when it has none (or the account cannot be reached).
  Future<ThemeMode?> load();

  /// Saves the choice to the account. A failure is swallowed: the device keeps its copy and the
  /// next change sends it again.
  Future<void> save(ThemeMode mode);
}

/// Demo data and tests: nothing leaves the device.
class NoThemeModeSync implements ThemeModeSync {
  const NoThemeModeSync();

  @override
  Future<ThemeMode?> load() async => null;

  @override
  Future<void> save(ThemeMode mode) async {}
}

class AccountThemeModeSync extends LiveRepository implements ThemeModeSync {
  const AccountThemeModeSync(super.dio);

  @override
  Future<ThemeMode?> load() async {
    try {
      final stored = await getObject(
        '/api/v1/me',
        (r) => r.object('preferences').stringOrNull('theme_mode'),
      );
      return stored == null ? null : themeModeFromStorage(stored);
    } on ApiException {
      return null; // offline or signed out: keep the device's choice
    }
  }

  @override
  Future<void> save(ThemeMode mode) async {
    try {
      await sendEmpty(
        'PATCH',
        '/api/v1/me/preferences',
        body: {'theme_mode': themeModeToStorage(mode)},
      );
    } on ApiException {
      // Kept on the device; sent with the next change.
    }
  }
}

final themeModeSyncProvider = Provider<ThemeModeSync>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return const NoThemeModeSync();
    case DataSourceMode.live:
      return AccountThemeModeSync(ref.watch(apiClientProvider));
  }
});

/// Keeps the appearance in step with the account. After sign-in the account's choice wins; when
/// the account has none, the device's choice is sent up. Later changes on the device are saved to
/// the account. Watched once by the app.
final themeModeSyncWiringProvider = Provider<void>((ref) {
  var applyingRemote = false;

  Future<void> pull() async {
    try {
      final sync = ref.read(themeModeSyncProvider);
      final remote = await sync.load();
      final local = ref.read(themeModeProvider);
      if (remote == null) {
        await sync.save(local);
      } else if (remote != local) {
        applyingRemote = true;
        await ref.read(themeModeProvider.notifier).setMode(remote);
      }
    } on Object {
      // The appearance is a convenience; never let syncing it disturb the app.
    } finally {
      applyingRemote = false;
    }
  }

  ref.listen<AuthState>(authControllerProvider, (previous, next) {
    if (next is SignedIn && previous is! SignedIn) unawaited(pull());
  }, fireImmediately: true);

  ref.listen<ThemeMode>(themeModeProvider, (previous, next) {
    if (previous == null || previous == next || applyingRemote) return;
    if (ref.read(authControllerProvider) is! SignedIn) return;
    // A failing save is the account's problem, never the app's: the device copy stays.
    unawaited(
      ref.read(themeModeSyncProvider).save(next).catchError((Object _) {}),
    );
  });
});

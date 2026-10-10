import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'app_lock_settings.dart';
import 'device_authenticator.dart';

@immutable
sealed class AppLockState {
  const AppLockState();
}

class Unlocked extends AppLockState {
  const Unlocked();
}

class Locked extends AppLockState {
  const Locked({this.lastOutcome});

  /// Why the last unlock attempt did not succeed (null before any attempt).
  final UnlockOutcome? lastOutcome;

  @override
  bool operator ==(Object other) =>
      other is Locked && other.lastOutcome == lastOutcome;

  @override
  int get hashCode => lastOutcome.hashCode;
}

class Unlocking extends AppLockState {
  const Unlocking();
}

/// Locks a signed-in session behind biometrics or the device credential.
///
/// The lock applies only while signed in and enabled. It engages when a stored session is
/// restored at start-up, when the app returns after at least the configured background timeout,
/// and after [AppLockSettings.idleTimeout] without interaction. Only a successful device
/// authentication unlocks; every other outcome leaves the app locked, and the way out is to sign
/// out (and sign in again with the identity provider).
class AppLockController extends Notifier<AppLockState> {
  DateTime? _backgroundedAt;
  DateTime Function() clock = DateTime.now;

  bool get _protects =>
      ref.read(authControllerProvider) is SignedIn &&
      ref.read(appLockSettingsProvider).enabled;

  @override
  AppLockState build() {
    ref.listen(authControllerProvider, (previous, next) {
      if (next is! SignedIn) {
        _backgroundedAt = null;
        state = const Unlocked(); // nothing to protect
      } else if (previous is AuthRestoring &&
          ref.read(appLockSettingsProvider).enabled) {
        state = const Locked(); // a stored session was restored at start-up
      }
    });
    ref.listen(appLockSettingsProvider, (_, settings) {
      if (!settings.enabled) state = const Unlocked();
    });
    final auth = ref.read(authControllerProvider);
    return auth is SignedIn && ref.read(appLockSettingsProvider).enabled
        ? const Locked()
        : const Unlocked();
  }

  bool get isLocked => state is! Unlocked;

  void onBackgrounded() {
    if (state is Unlocked && _protects) _backgroundedAt = clock();
  }

  void onResumed() {
    final since = _backgroundedAt;
    _backgroundedAt = null;
    if (since == null || state is! Unlocked || !_protects) return;
    final timeout = ref.read(appLockSettingsProvider).timeout.duration;
    final away = clock().difference(since);
    // A clock that moved backwards cannot prove the absence was short: lock.
    if (away.isNegative || away >= timeout) state = const Locked();
  }

  void onIdle() {
    if (state is Unlocked && _protects) state = const Locked();
  }

  /// Asks the device to verify the user. Unlocks only on success.
  Future<void> unlock(String reason) async {
    if (state is! Locked) return;
    state = const Unlocking();
    final outcome = await ref
        .read(deviceAuthenticatorProvider)
        .authenticate(reason);
    if (!ref.mounted || state is! Unlocking) return;
    state = outcome == UnlockOutcome.success
        ? const Unlocked()
        : Locked(lastOutcome: outcome);
  }
}

final appLockControllerProvider =
    NotifierProvider<AppLockController, AppLockState>(AppLockController.new);

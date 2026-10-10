import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';

/// The result of asking the user to prove it is them (biometrics or the device PIN/passcode).
enum UnlockOutcome {
  success,

  /// Not recognised (or an unexpected device error). The app stays locked; try again.
  failed,

  /// The user (or the system) dismissed the prompt. The app stays locked.
  cancelled,

  /// Too many attempts: the device refuses for a while.
  lockedOut,

  /// No biometrics or device credential is set up, so the app cannot be unlocked locally.
  unavailable,
}

/// Local user verification. Faked in tests.
abstract interface class DeviceAuthenticator {
  /// Whether the device can verify the user (biometrics or a device credential is set up).
  Future<bool> isAvailable();

  Future<UnlockOutcome> authenticate(String reason);
}

/// [DeviceAuthenticator] backed by `local_auth`: biometrics with the device PIN, pattern or
/// passcode as the platform fallback. The fallback is the device's own credential, so a failed
/// biometric never unlocks the app by itself.
class LocalAuthDeviceAuthenticator implements DeviceAuthenticator {
  LocalAuthDeviceAuthenticator([LocalAuthentication? auth])
    : _auth = auth ?? LocalAuthentication();

  final LocalAuthentication _auth;

  @override
  Future<bool> isAvailable() async {
    try {
      return await _auth.isDeviceSupported();
    } on Object {
      return false;
    }
  }

  @override
  Future<UnlockOutcome> authenticate(String reason) async {
    try {
      final ok = await _auth.authenticate(
        localizedReason: reason,
        persistAcrossBackgrounding: true,
      );
      return ok ? UnlockOutcome.success : UnlockOutcome.failed;
    } on LocalAuthException catch (e) {
      return outcomeFor(e.code);
    } on PlatformException {
      return UnlockOutcome.failed;
    }
  }

  static UnlockOutcome outcomeFor(LocalAuthExceptionCode code) =>
      switch (code) {
        LocalAuthExceptionCode.userCanceled ||
        LocalAuthExceptionCode.systemCanceled ||
        LocalAuthExceptionCode.timeout ||
        LocalAuthExceptionCode.userRequestedFallback ||
        LocalAuthExceptionCode.authInProgress ||
        LocalAuthExceptionCode.uiUnavailable => UnlockOutcome.cancelled,
        LocalAuthExceptionCode.temporaryLockout ||
        LocalAuthExceptionCode.biometricLockout => UnlockOutcome.lockedOut,
        LocalAuthExceptionCode.noCredentialsSet ||
        LocalAuthExceptionCode.noBiometricsEnrolled ||
        LocalAuthExceptionCode.noBiometricHardware => UnlockOutcome.unavailable,
        LocalAuthExceptionCode.biometricHardwareTemporarilyUnavailable ||
        LocalAuthExceptionCode.deviceError ||
        LocalAuthExceptionCode.unknownError => UnlockOutcome.failed,
      };
}

final deviceAuthenticatorProvider = Provider<DeviceAuthenticator>(
  (ref) => LocalAuthDeviceAuthenticator(),
);

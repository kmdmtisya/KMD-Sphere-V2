import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/config/app_config.dart';
import '../../../core/preferences/preferences_store.dart';

// ------------------------------------------------------------------ onboarding (UI preference)

const onboardingCompleteKey = 'ws.onboarding.v1';

Future<bool> readOnboardingComplete(PreferencesStore store) async {
  try {
    return await store.getString(onboardingCompleteKey) == 'done';
  } on Object {
    return false;
  }
}

/// Whether the introduction was already seen, known at start-up. `main()` overrides it from
/// storage; the default (true) lets tests and previews start on Home.
final initialOnboardingCompleteProvider = Provider<bool>((ref) => true);

Future<void> markOnboardingComplete(PreferencesStore store) async {
  try {
    await store.setString(onboardingCompleteKey, 'done');
  } on Object {
    // Best effort: at worst the introduction shows again.
  }
}

// ------------------------------------------------- one-time biometric offer (UI preference)

const biometricOfferedKey = 'ws.biometricOffer.v1';

Future<bool> biometricOfferShown(PreferencesStore store) async {
  try {
    return await store.getString(biometricOfferedKey) == 'shown';
  } on Object {
    return true; // unsure: do not nag
  }
}

Future<void> markBiometricOfferShown(PreferencesStore store) async {
  try {
    await store.setString(biometricOfferedKey, 'shown');
  } on Object {
    // Best effort.
  }
}

// ------------------------------------------------------------------------- password reset

/// Opens the identity provider's "forgot password" page. The URL is built from configuration
/// only (never from user input or a server response).
abstract interface class PasswordResetLauncher {
  Future<bool> open();
}

class UrlPasswordResetLauncher implements PasswordResetLauncher {
  const UrlPasswordResetLauncher(this._config);

  final AppConfig _config;

  Uri get resetUri => resetPasswordUri(_config);

  @override
  Future<bool> open() async {
    try {
      return await launchUrl(resetUri, mode: LaunchMode.inAppBrowserView);
    } on Object {
      return false;
    }
  }
}

Uri resetPasswordUri(AppConfig config) {
  final issuer = Uri.parse(config.oidcIssuer.replaceAll(RegExp(r'/+$'), ''));
  return issuer.replace(
    path: '${issuer.path}/login-actions/reset-credentials',
    queryParameters: {'client_id': config.clientId},
  );
}

final passwordResetLauncherProvider = Provider<PasswordResetLauncher>(
  (ref) => UrlPasswordResetLauncher(ref.watch(appConfigProvider)),
);

// ---------------------------------------------------------------------- email (login hint)

const maxEmailLength = 320;
final RegExp _email = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$');

enum EmailProblem { invalid, tooLong }

/// Validates the optional email used to pre-fill the sign-in page. Empty is fine.
EmailProblem? validateLoginHint(String raw) {
  final value = raw.trim();
  if (value.isEmpty) return null;
  if (value.length > maxEmailLength) return EmailProblem.tooLong;
  return _email.hasMatch(value) ? null : EmailProblem.invalid;
}

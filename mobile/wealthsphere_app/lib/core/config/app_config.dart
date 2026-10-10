import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Where the app finds the API and the identity provider.
///
/// Values come from `--dart-define` at build time; the defaults target the local development
/// stack. On an Android emulator or a USB device, forward the ports first so `127.0.0.1` is the
/// host machine and token issuers match the backend's configuration:
/// `adb reverse tcp:8000 tcp:8000 && adb reverse tcp:8081 tcp:8081` (docs/dev-setup.md).
@immutable
class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    required this.oidcIssuer,
    this.clientId = 'wealthsphere-mobile',
    this.redirectUri = 'com.kmdmtisya.wealthsphere:/oauth2redirect',
    this.scopes = const ['openid', 'profile', 'email'],
  });

  /// Reads `WS_API_BASE_URL` and `WS_OIDC_ISSUER`. Release builds must use https.
  factory AppConfig.fromEnvironment() {
    const config = AppConfig(
      apiBaseUrl: String.fromEnvironment(
        'WS_API_BASE_URL',
        defaultValue: 'http://127.0.0.1:8000',
      ),
      oidcIssuer: String.fromEnvironment(
        'WS_OIDC_ISSUER',
        defaultValue: 'http://127.0.0.1:8081/realms/wealthsphere',
      ),
    );
    config.assertSecureFor(debug: kDebugMode);
    return config;
  }

  final String apiBaseUrl;

  /// Must equal the `iss` claim of the tokens the backend accepts.
  final String oidcIssuer;
  final String clientId;
  final String redirectUri;

  /// No `offline_access`: long-lived offline tokens are not issued to the app.
  final List<String> scopes;

  String get authorizationEndpoint => '$_oidc/auth';
  String get tokenEndpoint => '$_oidc/token';
  String get endSessionEndpoint => '$_oidc/logout';
  String get _oidc =>
      '${oidcIssuer.replaceAll(RegExp(r'/+$'), '')}/protocol/openid-connect';

  /// Plain HTTP is accepted only for loopback development hosts in debug builds.
  bool get allowsInsecureConnections =>
      _isLocalHttp(apiBaseUrl) || _isLocalHttp(oidcIssuer);

  void assertSecureFor({required bool debug}) {
    for (final url in [apiBaseUrl, oidcIssuer]) {
      final uri = Uri.parse(url);
      if (uri.scheme == 'https') continue;
      if (debug && _isLocalHttp(url)) continue;
      throw StateError(
        'Insecure endpoint not allowed in this build: ${uri.scheme}://${uri.host}',
      );
    }
  }

  static bool _isLocalHttp(String url) {
    final uri = Uri.parse(url);
    return uri.scheme == 'http' &&
        const {'127.0.0.1', 'localhost', '10.0.2.2'}.contains(uri.host);
  }
}

final appConfigProvider = Provider<AppConfig>(
  (ref) => AppConfig.fromEnvironment(),
);

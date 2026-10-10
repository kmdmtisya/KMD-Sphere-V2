import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:flutter_appauth/flutter_appauth.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/app_config.dart';
import 'token_set.dart';

/// Why an authentication step failed. Deliberately coarse: users see a plain message and nothing
/// about tokens or server internals.
enum AuthFailure {
  /// The user closed the sign-in page.
  cancelled,

  /// The identity provider could not be reached (offline, timeout, 5xx). Transient.
  network,

  /// The identity provider refused the grant (expired or revoked session, reused refresh token).
  rejected,

  /// There is no session to use.
  signedOut,

  /// Anything else (misconfiguration, malformed response).
  unexpected,
}

/// What the hosted identity pages should show.
enum SignInIntent {
  /// The sign-in page (with links to registration and password reset).
  signIn,

  /// The registration page (`prompt=create`).
  register,

  /// Set up TOTP two-step verification (Keycloak application-initiated action).
  configureMfa,
}

class AuthException implements Exception {
  const AuthException(this.failure);

  final AuthFailure failure;

  @override
  String toString() => 'AuthException(${failure.name})';
}

/// The identity-provider operations the app needs. Faked in tests.
abstract interface class OidcClient {
  /// Authorization Code + PKCE in the system browser; returns the new session's tokens.
  /// [loginHint] pre-fills the email on the identity provider's page; the password is only ever
  /// typed there, never in the app.
  Future<TokenSet> signIn({
    String? loginHint,
    SignInIntent intent = SignInIntent.signIn,
  });

  /// Exchanges the refresh token. Keycloak rotates it: the result carries a new one and the old
  /// one stops working.
  Future<TokenSet> refresh(TokenSet current);

  /// Ends the session at the identity provider (best effort; local sign-out never waits on it).
  Future<void> endSession(TokenSet tokens);
}

/// [OidcClient] for the WealthSphere Keycloak realm.
///
/// The browser step uses AppAuth (PKCE S256 is built in; ASWebAuthenticationSession on iOS,
/// Custom Tabs on Android). Refresh and logout are plain form posts, so their failures map
/// exactly onto [AuthFailure].
class KeycloakOidcClient implements OidcClient {
  KeycloakOidcClient({
    required this._config,
    FlutterAppAuth? appAuth,
    Dio? http,
    DateTime Function()? clock,
  }) : _appAuth = appAuth ?? const FlutterAppAuth(),
       _http =
           http ??
           Dio(
             BaseOptions(
               connectTimeout: const Duration(seconds: 10),
               receiveTimeout: const Duration(seconds: 15),
             ),
           ),
       _clock = clock ?? DateTime.now;

  final AppConfig _config;
  final FlutterAppAuth _appAuth;
  final Dio _http;
  final DateTime Function() _clock;

  @override
  Future<TokenSet> signIn({
    String? loginHint,
    SignInIntent intent = SignInIntent.signIn,
  }) async {
    try {
      final response = await _appAuth.authorizeAndExchangeCode(
        AuthorizationTokenRequest(
          _config.clientId,
          _config.redirectUri,
          loginHint: loginHint,
          promptValues: intent == SignInIntent.register
              ? const ['create']
              : null,
          additionalParameters: intent == SignInIntent.configureMfa
              ? const {'kc_action': 'CONFIGURE_TOTP'}
              : null,
          serviceConfiguration: AuthorizationServiceConfiguration(
            authorizationEndpoint: _config.authorizationEndpoint,
            tokenEndpoint: _config.tokenEndpoint,
            endSessionEndpoint: _config.endSessionEndpoint,
          ),
          scopes: _config.scopes,
          allowInsecureConnections: _config.allowsInsecureConnections,
          // No shared browser cookies: each sign-in is explicit, and signing out really ends it.
          externalUserAgent:
              ExternalUserAgent.ephemeralAsWebAuthenticationSession,
        ),
      );
      final access = response.accessToken;
      final refresh = response.refreshToken;
      final expiry = response.accessTokenExpirationDateTime;
      if (access == null || refresh == null || expiry == null) {
        throw const AuthException(AuthFailure.unexpected);
      }
      return TokenSet(
        accessToken: access,
        refreshToken: refresh,
        accessTokenExpiresAt: expiry.toUtc(),
        idToken: response.idToken,
      );
    } on FlutterAppAuthUserCancelledException {
      throw const AuthException(AuthFailure.cancelled);
    } on FlutterAppAuthPlatformException catch (e) {
      final error = e.platformErrorDetails.error;
      throw AuthException(
        error == FlutterAppAuthOAuthError.invalidGrant
            ? AuthFailure.rejected
            : (error == null ? AuthFailure.network : AuthFailure.unexpected),
      );
    } on PlatformException {
      throw const AuthException(AuthFailure.unexpected);
    }
  }

  @override
  Future<TokenSet> refresh(TokenSet current) async {
    final Response<Object?> response;
    try {
      response = await _http.post<Object?>(
        _config.tokenEndpoint,
        data: {
          'grant_type': 'refresh_token',
          'client_id': _config.clientId,
          'refresh_token': current.refreshToken,
        },
        options: Options(
          contentType: Headers.formUrlEncodedContentType,
          validateStatus: (_) => true,
        ),
      );
    } on DioException {
      throw const AuthException(AuthFailure.network);
    }
    final status = response.statusCode ?? 0;
    final body = response.data;
    if (status == 200 && body is Map<String, Object?>) {
      try {
        return TokenSet.fromTokenResponse(
          body,
          now: _clock(),
          previousRefreshToken: current.refreshToken,
        );
      } on FormatException {
        throw const AuthException(AuthFailure.unexpected);
      }
    }
    if (status == 400 || status == 401) {
      throw const AuthException(AuthFailure.rejected);
    }
    if (status >= 500 || status == 429) {
      throw const AuthException(AuthFailure.network);
    }
    throw const AuthException(AuthFailure.unexpected);
  }

  @override
  Future<void> endSession(TokenSet tokens) async {
    try {
      await _http.post<Object?>(
        _config.endSessionEndpoint,
        data: {
          'client_id': _config.clientId,
          'refresh_token': tokens.refreshToken,
        },
        options: Options(
          contentType: Headers.formUrlEncodedContentType,
          validateStatus: (_) => true,
        ),
      );
    } on DioException {
      // Offline: the tokens are already gone from the device; the server session times out.
    }
  }
}

final oidcClientProvider = Provider<OidcClient>(
  (ref) => KeycloakOidcClient(config: ref.watch(appConfigProvider)),
);

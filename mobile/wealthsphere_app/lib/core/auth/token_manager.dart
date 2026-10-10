import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'oidc_client.dart';
import 'token_set.dart';
import 'token_store.dart';

/// Why a session ended without the user signing out.
enum SessionEnd {
  /// The identity provider refused the refresh token (session expired or revoked).
  refreshRejected,

  /// The API refused a freshly refreshed token (for example, a disabled account).
  rejectedByApi,
}

/// Owns the session's tokens: restores them from secure storage, hands out a valid access token
/// (refreshing shortly before expiry, one refresh at a time), and clears them on sign-out or
/// when the session can no longer be refreshed.
class TokenManager {
  TokenManager({
    required this._store,
    required this._client,
    DateTime Function()? clock,
    this.refreshMargin = const Duration(seconds: 30),
  }) : _clock = clock ?? DateTime.now;

  final TokenStore _store;
  final OidcClient _client;
  final DateTime Function() _clock;

  /// Refresh this long before the access token expires, so it never expires in flight.
  final Duration refreshMargin;

  /// Called when the session ends without the user asking (see [SessionEnd]).
  void Function(SessionEnd reason)? onSessionEnded;

  TokenSet? _tokens;
  Future<void>? _loading;
  Future<TokenSet?>? _refreshing;

  /// Loads the stored session once. Safe to call repeatedly.
  Future<bool> restore() async {
    await (_loading ??= _store.read().then((t) => _tokens = t));
    return _tokens != null;
  }

  bool get isSignedIn => _tokens != null;

  /// Display-only claims of the current access token (unverified).
  Map<String, Object?> get claims => _tokens?.displayClaims ?? const {};

  Future<void> signIn() async {
    await restore();
    final tokens = await _client.signIn();
    await _store.write(tokens);
    _tokens = tokens;
  }

  /// Forgets the session on this device first, then ends it at the identity provider.
  Future<void> signOut() async {
    await restore();
    final tokens = _tokens;
    _tokens = null;
    await _store.clear();
    if (tokens != null) {
      unawaited(_client.endSession(tokens).catchError((Object _) {}));
    }
  }

  /// A usable access token, or null when signed out.
  ///
  /// Pass the token the API just rejected as [rejected] to force a refresh; if another request
  /// already refreshed it, the newer token is returned without refreshing again.
  /// Throws [AuthException] with [AuthFailure.network] when a needed refresh cannot reach the
  /// identity provider (the session is kept for later).
  Future<String?> validAccessToken({String? rejected}) async {
    await restore();
    final tokens = _tokens;
    if (tokens == null) return null;
    final mustRefresh = rejected != null
        ? tokens.accessToken == rejected
        : tokens.expiresWithin(refreshMargin, _clock());
    if (!mustRefresh) return tokens.accessToken;
    return (await _refreshOnce(tokens))?.accessToken;
  }

  /// Ends the session because the API refused even a fresh token.
  Future<void> endRejectedSession() async {
    if (_tokens == null) return;
    await signOut();
    onSessionEnded?.call(SessionEnd.rejectedByApi);
  }

  Future<TokenSet?> _refreshOnce(TokenSet tokens) {
    return _refreshing ??= _refresh(tokens)
        .whenComplete(() => _refreshing = null);
  }

  Future<TokenSet?> _refresh(TokenSet tokens) async {
    try {
      final fresh = await _client.refresh(tokens);
      // Signed out (or in again) while refreshing: keep what is current now.
      if (!identical(_tokens, tokens)) return _tokens;
      _tokens = fresh;
      // The old refresh token is dead now (rotation): persist the new one.
      await _store.write(fresh);
      return fresh;
    } on AuthException catch (e) {
      if (e.failure != AuthFailure.rejected) rethrow;
      if (identical(_tokens, tokens)) {
        _tokens = null;
        await _store.clear();
        onSessionEnded?.call(SessionEnd.refreshRejected);
      }
      return null;
    }
  }
}

final tokenManagerProvider = Provider<TokenManager>(
  (ref) => TokenManager(
    store: ref.watch(tokenStoreProvider),
    client: ref.watch(oidcClientProvider),
  ),
);

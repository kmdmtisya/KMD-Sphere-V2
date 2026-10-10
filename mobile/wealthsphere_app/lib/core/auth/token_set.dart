import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../data/json_reader.dart';

/// The tokens of one signed-in session. Held in memory and in secure storage only.
///
/// [toString] never prints a token, so a stray log line or error message cannot leak one.
@immutable
class TokenSet {
  const TokenSet({
    required this.accessToken,
    required this.refreshToken,
    required this.accessTokenExpiresAt,
    this.idToken,
  });

  /// A token endpoint response (`expires_in` is relative to [now]). When a refresh response omits
  /// the refresh token, [previousRefreshToken] is kept.
  factory TokenSet.fromTokenResponse(
    Map<String, Object?> json, {
    required DateTime now,
    String? previousRefreshToken,
  }) {
    final r = JsonReader(json);
    final refresh = r.stringOrNull('refresh_token') ?? previousRefreshToken;
    if (refresh == null) {
      throw const FormatException('token response without a refresh token');
    }
    return TokenSet(
      accessToken: r.string('access_token'),
      refreshToken: refresh,
      accessTokenExpiresAt: now.toUtc().add(
        Duration(seconds: r.integer('expires_in')),
      ),
      idToken: r.stringOrNull('id_token'),
    );
  }

  factory TokenSet.fromJson(Map<String, Object?> json) {
    final r = JsonReader(json);
    return TokenSet(
      accessToken: r.string('access_token'),
      refreshToken: r.string('refresh_token'),
      accessTokenExpiresAt: r.timestamp('access_token_expires_at'),
      idToken: r.stringOrNull('id_token'),
    );
  }

  final String accessToken;
  final String refreshToken;
  final DateTime accessTokenExpiresAt;
  final String? idToken;

  /// Whether the access token expires within [margin] of [now] (or already has).
  bool expiresWithin(Duration margin, DateTime now) =>
      !now.toUtc().add(margin).isBefore(accessTokenExpiresAt);

  Map<String, Object?> toJson() => {
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'access_token_expires_at': accessTokenExpiresAt.toUtc().toIso8601String(),
    if (idToken != null) 'id_token': idToken,
  };

  /// Unverified claims of the access token, for display only (the backend verifies tokens).
  Map<String, Object?> get displayClaims {
    try {
      final payload = accessToken.split('.')[1];
      final decoded = utf8.decode(
        base64Url.decode(base64Url.normalize(payload)),
      );
      final claims = jsonDecode(decoded);
      return claims is Map<String, Object?> ? claims : const {};
    } on Object {
      return const {};
    }
  }

  @override
  String toString() =>
      'TokenSet(expires: ${accessTokenExpiresAt.toIso8601String()}, '
      'tokens: [REDACTED])';
}

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_set.dart';

/// An unsigned JWT-shaped token with these claims (the app never verifies tokens; the API does).
String fakeJwt(Map<String, Object?> claims) {
  String part(Object json) =>
      base64Url.encode(utf8.encode(jsonEncode(json))).replaceAll('=', '');
  return '${part({'alg': 'none'})}.${part(claims)}.sig';
}

final epoch = DateTime.utc(2026, 10, 10, 12);

TokenSet tokens(
  String name, {
  DateTime? expiresAt,
  String? email = 'alice@example.test',
}) => TokenSet(
  accessToken: fakeJwt({'sub': name, 'email': email, 'jti': 'access-$name'}),
  refreshToken: 'refresh-$name',
  accessTokenExpiresAt: expiresAt ?? epoch.add(const Duration(minutes: 5)),
  idToken: 'id-$name',
);

/// Scriptable [OidcClient]: queue results (a [TokenSet] or an [AuthException]) per operation.
class FakeOidcClient implements OidcClient {
  final List<Object> signInResults = [];
  final List<Object> refreshResults = [];
  final List<TokenSet> refreshedFrom = [];
  final List<TokenSet> endedSessions = [];
  int signInCalls = 0;

  /// Completes refreshes only when the test says so (to test concurrency).
  Completer<void>? refreshGate;
  bool failEndSession = false;

  @override
  Future<TokenSet> signIn() async {
    signInCalls++;
    return _next(signInResults);
  }

  @override
  Future<TokenSet> refresh(TokenSet current) async {
    refreshedFrom.add(current);
    await refreshGate?.future;
    return _next(refreshResults);
  }

  @override
  Future<void> endSession(TokenSet tokens) async {
    endedSessions.add(tokens);
    if (failEndSession) throw const AuthException(AuthFailure.network);
  }

  static TokenSet _next(List<Object> queue) {
    if (queue.isEmpty) throw StateError('no scripted result');
    final result = queue.removeAt(0);
    if (result is AuthException) throw result;
    return result as TokenSet;
  }
}

/// A recorded request.
class SentRequest {
  SentRequest(this.options, this.body);

  final RequestOptions options;
  final String body;

  String? header(String name) {
    for (final entry in options.headers.entries) {
      if (entry.key.toLowerCase() == name.toLowerCase()) {
        return entry.value?.toString();
      }
    }
    return null;
  }
}

typedef FakeReply = ({int status, Object? json, Map<String, String> headers});

FakeReply reply(
  int status, [
  Object? json,
  Map<String, String> headers = const {},
]) => (status: status, json: json, headers: headers);

/// [HttpClientAdapter] that records requests and answers from a script (or throws a
/// connection error when the script holds a [DioExceptionType]).
class FakeAdapter implements HttpClientAdapter {
  FakeAdapter([List<Object>? replies]) : replies = replies ?? [];

  final List<Object> replies;
  final List<SentRequest> sent = [];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final bytes = <int>[];
    if (requestStream != null) {
      await for (final chunk in requestStream) {
        bytes.addAll(chunk);
      }
    }
    sent.add(SentRequest(options, utf8.decode(bytes)));
    if (replies.isEmpty) {
      throw StateError('no scripted reply for ${options.path}');
    }
    final next = replies.removeAt(0);
    if (next is DioExceptionType) {
      throw DioException(requestOptions: options, type: next);
    }
    final r = next as FakeReply;
    final isProblem = r.status >= 400;
    return ResponseBody.fromString(
      r.json == null ? '' : jsonEncode(r.json),
      r.status,
      headers: {
        Headers.contentTypeHeader: [
          isProblem ? 'application/problem+json' : Headers.jsonContentType,
        ],
        for (final h in r.headers.entries) h.key: [h.value],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

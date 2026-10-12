import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

/// One request the fake API received.
class ApiCall {
  ApiCall(this.method, this.path, this.query, this.headers, this.body);

  final String method;
  final String path;
  final Map<String, String> query;
  final Map<String, dynamic> headers;

  /// The decoded JSON body, or null.
  final Object? body;

  String? header(String name) {
    for (final e in headers.entries) {
      if (e.key.toLowerCase() == name.toLowerCase()) return e.value?.toString();
    }
    return null;
  }

  @override
  String toString() => '$method $path';
}

/// What a route answers: a status and a JSON body. Throw a [DioExceptionType] to simulate a
/// dropped connection.
typedef FakeHandler = Object Function(ApiCall call);

/// A routed stand-in for the WealthSphere API, for live-repository and widget tests. Routes are
/// `'GET /api/v1/portfolios'`; the last path segment may be matched with a handler that reads
/// [ApiCall.path]. Unrouted requests answer 404 like the real API.
class FakeApi implements HttpClientAdapter {
  FakeApi([Map<String, FakeHandler>? routes]) : routes = routes ?? {};

  final Map<String, FakeHandler> routes;
  final List<ApiCall> calls = [];

  /// A [Dio] that talks to this fake.
  Dio dio() =>
      Dio(BaseOptions(baseUrl: 'http://api.test'))..httpClientAdapter = this;

  void on(String route, Object Function(ApiCall call) handler) =>
      routes[route] = handler;

  /// Answers [route] with [body] (status 200).
  void json(String route, Object? body, {int status = 200}) =>
      routes[route] = (_) => (status, body);

  List<ApiCall> callsTo(String method, String path) => [
    for (final c in calls)
      if (c.method == method && c.path == path) c,
  ];

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
    final text = utf8.decode(bytes);
    final call = ApiCall(
      options.method.toUpperCase(),
      options.uri.path,
      options.uri.queryParameters,
      options.headers,
      text.isEmpty ? null : jsonDecode(text),
    );
    calls.add(call);
    final handler = routes['${call.method} ${call.path}'];
    final Object answer = handler == null
        ? (404, {'title': 'Not found', 'status': 404})
        : handler(call);
    if (answer is DioExceptionType) {
      throw DioException(requestOptions: options, type: answer);
    }
    final (status, body) = answer as (int, Object?);
    return ResponseBody.fromString(
      body == null ? '' : jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [
          status >= 400 ? 'application/problem+json' : Headers.jsonContentType,
        ],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Map<String, String> usd(String amount) => {'amount': amount, 'currency': 'USD'};

import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/oidc_client.dart';
import '../auth/token_manager.dart';
import '../config/app_config.dart';

/// Request option: `extra: {ApiOptions.public: true}` sends no access token.
abstract final class ApiOptions {
  static const public = 'ws.public';
  static const _retried = 'ws.retried';
}

/// The Dio client for the WealthSphere API.
///
/// - Adds `Authorization: Bearer` from [TokenManager], refreshing shortly before expiry.
/// - On a 401, refreshes once and retries once; if the API refuses the fresh token too, the
///   session is ended.
/// - Sends an `X-Correlation-ID` with every request.
/// - Has no logging interceptor: requests carry tokens and responses carry financial data.
Dio buildApiClient({
  required AppConfig config,
  required TokenManager tokens,
  HttpClientAdapter? adapter,
}) {
  final dio = Dio(
    BaseOptions(
      baseUrl: config.apiBaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 20),
      sendTimeout: const Duration(seconds: 20),
      responseType: ResponseType.json,
      headers: {'Accept': 'application/json, application/problem+json'},
    ),
  );
  if (adapter != null) dio.httpClientAdapter = adapter;
  dio.interceptors.addAll([
    CorrelationIdInterceptor(),
    AuthInterceptor(tokens, dio),
  ]);
  return dio;
}

class CorrelationIdInterceptor extends Interceptor {
  CorrelationIdInterceptor([Random? random])
    : _random = random ?? Random.secure();

  final Random _random;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers.putIfAbsent('X-Correlation-ID', _newId);
    handler.next(options);
  }

  String _newId() => List.generate(
    16,
    (_) => _random.nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
}

class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._tokens, this._dio);

  final TokenManager _tokens;
  final Dio _dio;

  static const _header = 'Authorization';

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (options.extra[ApiOptions.public] == true) {
      handler.next(options);
      return;
    }
    try {
      final token = await _tokens.validAccessToken();
      if (token == null) {
        handler.reject(_authError(options, AuthFailure.signedOut));
        return;
      }
      options.headers[_header] = 'Bearer $token';
      handler.next(options);
    } on AuthException catch (e) {
      handler.reject(_authError(options, e.failure));
    }
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    final sent = options.headers[_header];
    if (err.response?.statusCode != 401 ||
        options.extra[ApiOptions.public] == true ||
        sent is! String) {
      handler.next(err);
      return;
    }
    if (options.extra[ApiOptions._retried] == true) {
      // A freshly refreshed token was refused too: this session cannot use the API.
      await _tokens.endRejectedSession();
      handler.next(err);
      return;
    }
    final String? token;
    try {
      token = await _tokens.validAccessToken(
        rejected: sent.substring('Bearer '.length),
      );
    } on AuthException catch (e) {
      handler.next(_authError(options, e.failure));
      return;
    }
    if (token == null) {
      handler.next(err); // the refresh was refused and the session has ended
      return;
    }
    final retry = options.copyWith(
      headers: {...options.headers, _header: 'Bearer $token'},
      extra: {...options.extra, ApiOptions._retried: true},
    );
    try {
      handler.resolve(await _dio.fetch<Object?>(retry));
    } on DioException catch (e) {
      handler.next(e);
    }
  }

  static DioException _authError(RequestOptions options, AuthFailure failure) =>
      DioException(
        requestOptions: options,
        error: AuthException(failure),
        type: failure == AuthFailure.network
            ? DioExceptionType.connectionError
            : DioExceptionType.unknown,
      );
}

final apiClientProvider = Provider<Dio>(
  (ref) => buildApiClient(
    config: ref.watch(appConfigProvider),
    tokens: ref.watch(tokenManagerProvider),
  ),
);

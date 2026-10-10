import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../auth/oidc_client.dart';

/// What went wrong with an API call, in terms the UI can act on.
enum ApiErrorKind {
  /// No connection, DNS failure or timeout.
  network,

  /// Not signed in, or the session ended.
  unauthenticated,
  forbidden,
  notFound,
  validation,

  /// 429: wait [ApiException.retryAfter] before trying again.
  rateLimited,
  server,
  unexpected,
}

/// An API failure built from an RFC 7807 problem+json response (or a transport error).
///
/// Holds no request or response bodies beyond the problem fields, and never a token.
@immutable
class ApiException implements Exception {
  const ApiException(
    this.kind, {
    this.status,
    this.title,
    this.detail,
    this.correlationId,
    this.retryAfter,
    this.fieldErrors = const [],
  });

  factory ApiException.fromDio(DioException e) {
    final error = e.error;
    if (error is AuthException) {
      return ApiException(
        error.failure == AuthFailure.network
            ? ApiErrorKind.network
            : ApiErrorKind.unauthenticated,
      );
    }
    final response = e.response;
    if (response == null) {
      return const ApiException(ApiErrorKind.network);
    }
    final status = response.statusCode ?? 0;
    final body = response.data;
    final problem = body is Map ? body : const <Object?, Object?>{};
    String? text(String key) =>
        problem[key] is String ? problem[key]! as String : null;
    final errors = problem['errors'];
    return ApiException(
      _kindFor(status),
      status: status,
      title: text('title'),
      detail: text('detail'),
      correlationId:
          text('correlation_id') ?? response.headers.value('x-correlation-id'),
      retryAfter: _retryAfter(response.headers.value('retry-after')),
      fieldErrors: [
        if (errors is List)
          for (final item in errors)
            if (item is Map &&
                item['field'] is String &&
                item['message'] is String)
              (
                field: item['field']! as String,
                message: item['message']! as String,
              ),
      ],
    );
  }

  final ApiErrorKind kind;
  final int? status;
  final String? title;
  final String? detail;

  /// Quote this to support: it links the failure to the server logs.
  final String? correlationId;
  final Duration? retryAfter;
  final List<({String field, String message})> fieldErrors;

  static ApiErrorKind _kindFor(int status) => switch (status) {
    401 => ApiErrorKind.unauthenticated,
    403 => ApiErrorKind.forbidden,
    404 => ApiErrorKind.notFound,
    413 || 422 => ApiErrorKind.validation,
    429 => ApiErrorKind.rateLimited,
    >= 500 => ApiErrorKind.server,
    _ => ApiErrorKind.unexpected,
  };

  static Duration? _retryAfter(String? header) {
    final seconds = int.tryParse(header ?? '');
    return seconds == null || seconds < 0 ? null : Duration(seconds: seconds);
  }

  @override
  String toString() =>
      'ApiException(${kind.name}, status: $status, correlation: $correlationId)';
}

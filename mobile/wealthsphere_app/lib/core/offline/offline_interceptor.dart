import 'package:dio/dio.dart';

import '../auth/oidc_client.dart';
import '../network/api_client.dart';
import 'snapshot_cache.dart';

/// Keeps the last good answer to every API GET and serves it when the device is offline
/// (ADR-0015).
///
/// - A successful GET is saved (encrypted, per user) and reports the device online.
/// - A GET that fails because the device cannot reach the server (no connection, a timeout, or a
///   token refresh that could not reach the identity provider) is answered from the saved copy
///   when there is one, and reports the device offline with the copy's age.
/// - Every other failure (401, 403, 404, 422, 429, 5xx) passes through unchanged: saved data never
///   hides an error the user should see. Writes are never cached or replayed.
class OfflineInterceptor extends Interceptor {
  OfflineInterceptor(
    this._cache, {
    required this.onOnline,
    required this.onOffline,
    DateTime Function()? clock,
  }) : _now = clock ?? DateTime.now;

  final SnapshotCache _cache;

  /// A request reached the server.
  final void Function() onOnline;

  /// A request could not reach the server; [savedAt] is the age of the copy shown, if any.
  final void Function(DateTime? savedAt) onOffline;
  final DateTime Function() _now;

  /// Set on a response served from the saved copy: when it was saved.
  static const savedAtKey = 'ws.offline.saved_at';

  static String requestKey(RequestOptions o) {
    final query = o.uri.queryParameters.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));
    return 'GET ${o.uri.path}?${[for (final e in query) '${e.key}=${e.value}'].join('&')}';
  }

  static bool _cacheable(RequestOptions o) =>
      o.method.toUpperCase() == 'GET' && o.extra[ApiOptions.public] != true;

  static bool isOffline(DioException e) {
    final cause = e.error;
    if (cause is AuthException && cause.failure == AuthFailure.network) {
      return true;
    }
    return switch (e.type) {
      DioExceptionType.connectionError ||
      DioExceptionType.connectionTimeout ||
      DioExceptionType.sendTimeout ||
      DioExceptionType.receiveTimeout => true,
      _ => false,
    };
  }

  @override
  Future<void> onResponse(
    Response<dynamic> response,
    ResponseInterceptorHandler handler,
  ) async {
    onOnline();
    final options = response.requestOptions;
    final status = response.statusCode ?? 0;
    final body = response.data;
    if (_cacheable(options) &&
        status >= 200 &&
        status < 300 &&
        (body is Map || body is List)) {
      try {
        await _cache.write(requestKey(options), body, _now());
      } on Object {
        // Saving is best effort; the answer itself is fine.
      }
    }
    handler.next(response);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (!isOffline(err)) {
      // The server answered, with an error: it is reachable.
      if (err.response != null) onOnline();
      handler.next(err);
      return;
    }
    final options = err.requestOptions;
    Snapshot? saved;
    if (_cacheable(options)) {
      try {
        saved = await _cache.read(requestKey(options));
      } on Object {
        saved = null;
      }
    }
    onOffline(saved?.savedAt);
    if (saved == null) {
      handler.next(err);
      return;
    }
    handler.resolve(
      Response<dynamic>(
        requestOptions: options..extra[savedAtKey] = saved.savedAt,
        data: saved.body,
        statusCode: 200,
      ),
    );
  }
}

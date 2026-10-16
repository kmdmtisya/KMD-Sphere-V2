import 'package:dio/dio.dart';

import '../data/json_reader.dart';
import 'api_exception.dart';

/// Base class of the repositories that read the WealthSphere API.
///
/// It turns transport and HTTP failures into [ApiException] and shape problems into
/// [ApiErrorKind.invalidResponse], so every live repository fails the way the UI already handles
/// (`loadFailureOf`, `LoadErrorView`). It never logs bodies or tokens.
///
/// Repositories return what the server says. Financial figures are not recalculated here
/// (CLAUDE.md: the backend is authoritative); parse them with [JsonReader] only.
abstract class LiveRepository {
  const LiveRepository(this.dio);

  final Dio dio;

  /// GET an object and parse it.
  Future<T> getObject<T>(
    String path,
    T Function(JsonReader json) parse, {
    Map<String, Object?>? query,
  }) => _run(
    () => dio.get<Object?>(path, queryParameters: query),
    (body) => parse(JsonReader(body)),
  );

  /// GET an object and parse it together with the response's `ETag`, the version of the record the
  /// caller saw. Send it back as `If-Match` on the update so a change made elsewhere is refused (409)
  /// instead of being overwritten.
  Future<T> getObjectWithEtag<T>(
    String path,
    T Function(JsonReader json, String? etag) parse,
  ) async {
    final Response<Object?> response;
    try {
      response = await dio.get<Object?>(path);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
    try {
      return parse(JsonReader(response.data), response.headers.value('etag'));
    } on FormatException catch (e) {
      throw ApiException(
        ApiErrorKind.invalidResponse,
        status: response.statusCode,
        detail: e.message,
        correlationId: response.headers.value('x-correlation-id'),
      );
    }
  }

  /// GET a JSON array and parse each element.
  Future<List<T>> getList<T>(
    String path,
    T Function(JsonReader json) parse, {
    Map<String, Object?>? query,
  }) => _run(() => dio.get<Object?>(path, queryParameters: query), (body) {
    if (body is! List) {
      throw const FormatException(r'$ must be a list');
    }
    return [
      for (var i = 0; i < body.length; i++)
        parse(JsonReader(body[i], '\$[$i]')),
    ];
  });

  /// Send a request with a JSON body (POST, PATCH or PUT) and parse the answer.
  /// [idempotencyKey] is sent as `Idempotency-Key` so a retried write cannot post twice. [ifMatch] is
  /// the version being changed (an `ETag` read earlier): the server refuses the update if it moved on.
  Future<T> send<T>(
    String method,
    String path,
    T Function(JsonReader json) parse, {
    Object? body,
    String? idempotencyKey,
    String? ifMatch,
  }) => _run(
    () => dio.request<Object?>(
      path,
      data: body,
      options: Options(
        method: method,
        headers: {'Idempotency-Key': ?idempotencyKey, 'If-Match': ?ifMatch},
      ),
    ),
    (data) => parse(JsonReader(data)),
  );

  /// Send a request whose success has no body (204).
  Future<void> sendEmpty(String method, String path, {Object? body}) async {
    try {
      await dio.request<Object?>(
        path,
        data: body,
        options: Options(method: method),
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<T> _run<T>(
    Future<Response<Object?>> Function() call,
    T Function(Object? body) parse,
  ) async {
    final Response<Object?> response;
    try {
      response = await call();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
    try {
      return parse(response.data);
    } on FormatException catch (e) {
      // The message names the field path, never a value.
      throw ApiException(
        ApiErrorKind.invalidResponse,
        status: response.statusCode,
        detail: e.message,
        correlationId: response.headers.value('x-correlation-id'),
      );
    }
  }
}

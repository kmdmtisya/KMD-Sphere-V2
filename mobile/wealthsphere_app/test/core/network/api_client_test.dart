@Tags(['security'])
library;

import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_manager.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';
import 'package:wealthsphere_app/core/network/api_client.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';

import '../../helpers/auth_fakes.dart';

const config = AppConfig(
  apiBaseUrl: 'http://127.0.0.1:8000',
  oidcIssuer: 'http://127.0.0.1:8081/realms/wealthsphere',
);

void main() {
  late FakeAdapter api;
  late FakeOidcClient oidc;
  late InMemoryTokenStore store;
  late TokenManager manager;
  late List<SessionEnd> ended;
  late Dio dio;

  setUp(() {
    api = FakeAdapter();
    oidc = FakeOidcClient();
    store = InMemoryTokenStore(tokens('a'));
    ended = [];
    manager = TokenManager(store: store, client: oidc, clock: () => epoch)
      ..onSessionEnded = ended.add;
    dio = buildApiClient(config: config, tokens: manager, adapter: api);
  });

  Future<ApiException> failure(Future<Object?> call) async {
    try {
      await call;
    } on DioException catch (e) {
      return ApiException.fromDio(e);
    }
    fail('expected the call to fail');
  }

  test(
    'sends the access token and a correlation id to the API base URL',
    () async {
      api.replies.add(reply(200, {'ok': true}));
      await dio.get<Object?>('/api/v1/me');
      final sent = api.sent.single;
      expect(sent.options.uri.toString(), 'http://127.0.0.1:8000/api/v1/me');
      expect(sent.header('authorization'), 'Bearer ${tokens('a').accessToken}');
      expect(
        sent.header('x-correlation-id'),
        matches(RegExp(r'^[0-9a-f]{32}$')),
      );
    },
  );

  test('each request gets its own correlation id', () async {
    api.replies.addAll([reply(200, {}), reply(200, {})]);
    await dio.get<Object?>('/a');
    await dio.get<Object?>('/b');
    expect(
      api.sent[0].header('x-correlation-id'),
      isNot(api.sent[1].header('x-correlation-id')),
    );
  });

  test('public requests carry no token', () async {
    api.replies.add(reply(200, {}));
    await dio.get<Object?>(
      '/health/live',
      options: Options(extra: {ApiOptions.public: true}),
    );
    expect(api.sent.single.header('authorization'), isNull);
  });

  test('an expired access token is refreshed before the request', () async {
    store.tokens = tokens('a', expiresAt: epoch);
    oidc.refreshResults.add(tokens('b'));
    api.replies.add(reply(200, {}));
    await dio.get<Object?>('/api/v1/me');
    expect(
      api.sent.single.header('authorization'),
      'Bearer ${tokens('b').accessToken}',
    );
    expect(store.tokens!.refreshToken, 'refresh-b');
  });

  test('a 401 refreshes once and retries once, transparently', () async {
    oidc.refreshResults.add(tokens('b'));
    api.replies.addAll([
      reply(401, {'type': 'x/unauthenticated'}),
      reply(200, {'id': '1'}),
    ]);
    final response = await dio.get<Object?>('/api/v1/me');
    expect(response.data, {'id': '1'});
    expect(api.sent, hasLength(2));
    expect(
      api.sent[1].header('authorization'),
      'Bearer ${tokens('b').accessToken}',
    );
    expect(oidc.refreshedFrom, hasLength(1));
    expect(ended, isEmpty);
  });

  test(
    'if the API refuses the refreshed token too, the session ends',
    () async {
      oidc.refreshResults.add(tokens('b'));
      api.replies.addAll([reply(401), reply(401)]);
      final error = await failure(dio.get<Object?>('/api/v1/me'));
      expect(error.kind, ApiErrorKind.unauthenticated);
      expect(api.sent, hasLength(2)); // no retry loop
      expect(store.tokens, isNull);
      expect(ended, [SessionEnd.rejectedByApi]);
    },
  );

  test('if the refresh is refused, the session ends and the call fails as unauthenticated', () async {
    oidc.refreshResults.add(const AuthException(AuthFailure.rejected));
    api.replies.add(reply(401));
    final error = await failure(dio.get<Object?>('/api/v1/me'));
    expect(error.kind, ApiErrorKind.unauthenticated);
    expect(store.tokens, isNull);
    expect(ended, [SessionEnd.refreshRejected]);
  });

  test('signed out: the request never leaves the device', () async {
    store.tokens = null;
    final error = await failure(dio.get<Object?>('/api/v1/me'));
    expect(error.kind, ApiErrorKind.unauthenticated);
    expect(api.sent, isEmpty);
  });

  test(
    'offline during refresh: a network error, and the session is kept',
    () async {
      store.tokens = tokens('a', expiresAt: epoch);
      oidc.refreshResults.add(const AuthException(AuthFailure.network));
      final error = await failure(dio.get<Object?>('/api/v1/me'));
      expect(error.kind, ApiErrorKind.network);
      expect(api.sent, isEmpty);
      expect(store.tokens, isNotNull);
    },
  );

  test('other errors are not retried', () async {
    api.replies.add(reply(500, {'title': 'Internal Server Error'}));
    final error = await failure(dio.get<Object?>('/api/v1/me'));
    expect(error.kind, ApiErrorKind.server);
    expect(api.sent, hasLength(1));
    expect(oidc.refreshedFrom, isEmpty);
  });

  test('problem+json, Retry-After and field errors are surfaced', () async {
    api.replies.addAll([
      reply(
        429,
        {
          'type': 'https://wealthsphere.app/problems/rate-limited',
          'title': 'Too Many Requests',
          'status': 429,
          'correlation_id': 'abc123',
        },
        {'retry-after': '17'},
      ),
      reply(422, {
        'title': 'Validation failed',
        'errors': [
          {'field': 'risk_tolerance', 'message': 'Input should be ...'},
        ],
      }),
    ]);
    final limited = await failure(dio.get<Object?>('/api/v1/me'));
    expect(limited.kind, ApiErrorKind.rateLimited);
    expect(limited.retryAfter, const Duration(seconds: 17));
    expect(limited.correlationId, 'abc123');
    final invalid = await failure(
      dio.post<Object?>('/api/v1/risk-profiles', data: {}),
    );
    expect(invalid.kind, ApiErrorKind.validation);
    expect(invalid.fieldErrors.single.field, 'risk_tolerance');
  });

  test('transport failures are network errors', () async {
    api.replies.add(DioExceptionType.connectionTimeout);
    expect((await failure(dio.get<Object?>('/x'))).kind, ApiErrorKind.network);
  });

  test('tokens never reach logs, errors or printed output', () async {
    final printed = <String>[];
    final previous = debugPrint;
    debugPrint = (message, {wrapWidth}) => printed.add(message ?? '');
    addTearDown(() => debugPrint = previous);
    oidc.refreshResults.add(tokens('b'));
    api.replies.addAll([reply(401), reply(401)]);
    final errors = <String>[];
    await runZoned(
      () async {
        try {
          await dio.get<Object?>('/api/v1/me');
        } on DioException catch (e) {
          errors
            ..add(e.toString())
            ..add(ApiException.fromDio(e).toString());
        }
      },
      zoneSpecification: ZoneSpecification(
        print: (_, _, _, line) => printed.add(line),
      ),
    );
    final everything = [...printed, ...errors].join('\n');
    for (final secret in [
      tokens('a').accessToken,
      tokens('a').refreshToken,
      tokens('b').accessToken,
      tokens('b').refreshToken,
    ]) {
      expect(everything, isNot(contains(secret)));
    }
    expect(dio.interceptors.whereType<LogInterceptor>(), isEmpty);
  });
}

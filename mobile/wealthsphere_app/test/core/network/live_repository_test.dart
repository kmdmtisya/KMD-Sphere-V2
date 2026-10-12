import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/token_manager.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/data/json_reader.dart';
import 'package:wealthsphere_app/core/network/api_client.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';
import 'package:wealthsphere_app/core/network/live_repository.dart';
import 'package:wealthsphere_app/core/network/load_failure.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';

import '../../helpers/auth_fakes.dart';
import '../../helpers/pump_app.dart';

const config = AppConfig(
  apiBaseUrl: 'http://127.0.0.1:8000',
  oidcIssuer: 'http://127.0.0.1:8081/realms/wealthsphere',
);

class _Repo extends LiveRepository {
  const _Repo(super.dio);
}

typedef _Named = ({String id, String name});

_Named _named(JsonReader r) => (id: r.string('id'), name: r.string('name'));

void main() {
  late FakeAdapter api;
  late _Repo repo;

  setUp(() {
    api = FakeAdapter();
    final manager = TokenManager(
      store: InMemoryTokenStore(tokens('a')),
      client: FakeOidcClient(),
      clock: () => epoch,
    );
    repo = _Repo(buildApiClient(config: config, tokens: manager, adapter: api));
  });

  Future<ApiException> failure(Future<Object?> call) async {
    try {
      await call;
    } on ApiException catch (e) {
      return e;
    }
    fail('expected an ApiException');
  }

  group('reading', () {
    test('parses an object through the strict reader', () async {
      api.replies.add(reply(200, {'id': 'p1', 'name': 'Main'}));
      final item = await repo.getObject('/api/v1/portfolios/p1', _named);
      expect(item, (id: 'p1', name: 'Main'));
      expect(api.sent.single.options.method, 'GET');
    });

    test('sends query parameters', () async {
      api.replies.add(reply(200, <Object?>[]));
      await repo.getList('/api/v1/goals', _named, query: {'limit': 5});
      expect(api.sent.single.options.uri.query, 'limit=5');
    });

    test('parses a list and reports the path of a bad element', () async {
      api.replies.add(
        reply(200, [
          {'id': 'a', 'name': 'A'},
          {'id': 'b'},
        ]),
      );
      final error = await failure(repo.getList('/api/v1/goals', _named));
      expect(error.kind, ApiErrorKind.invalidResponse);
      expect(error.detail, contains(r'$[1]'));
      expect(error.detail, contains('name'));
    });

    test('an object where a list is expected is an invalid response', () async {
      api.replies.add(reply(200, {'id': 'a'}));
      final error = await failure(repo.getList('/api/v1/goals', _named));
      expect(error.kind, ApiErrorKind.invalidResponse);
    });

    test('a malformed body never puts its values in the error', () async {
      api.replies.add(reply(200, {'id': 'secret-value', 'name': 42}));
      final error = await failure(repo.getObject('/x', _named));
      expect(error.kind, ApiErrorKind.invalidResponse);
      expect('$error ${error.detail}', isNot(contains('secret-value')));
    });
  });

  group('writing', () {
    test('sends the body and the idempotency key', () async {
      api.replies.add(reply(201, {'id': 't1', 'name': 'Deposit'}));
      await repo.send(
        'POST',
        '/api/v1/portfolios/p1/transactions',
        _named,
        body: {'transaction_type': 'DEPOSIT'},
        idempotencyKey: 'key-1',
      );
      final sent = api.sent.single;
      expect(sent.options.method, 'POST');
      expect(sent.header('idempotency-key'), 'key-1');
      expect(sent.body, contains('DEPOSIT'));
    });

    test('no key header when none is given', () async {
      api.replies.add(reply(200, {'id': 'a', 'name': 'A'}));
      await repo.send('PATCH', '/x', _named, body: {});
      expect(api.sent.single.header('idempotency-key'), isNull);
    });

    test('an empty success is fine', () async {
      api.replies.add(reply(204));
      await repo.sendEmpty('DELETE', '/api/v1/goals/g1');
      expect(api.sent.single.options.method, 'DELETE');
    });
  });

  group('errors map to the failure the UI handles', () {
    final cases = <String, (Object, ApiErrorKind, LoadFailure)>{
      '403': (reply(403), ApiErrorKind.forbidden, LoadFailure.forbidden),
      '404': (reply(404), ApiErrorKind.notFound, LoadFailure.notFound),
      '422': (reply(422), ApiErrorKind.validation, LoadFailure.unknown),
      '429': (
        reply(429, null, {'retry-after': '7'}),
        ApiErrorKind.rateLimited,
        LoadFailure.busy,
      ),
      '500': (reply(500), ApiErrorKind.server, LoadFailure.busy),
      'timeout': (
        DioExceptionType.receiveTimeout,
        ApiErrorKind.network,
        LoadFailure.offline,
      ),
      'no connection': (
        DioExceptionType.connectionError,
        ApiErrorKind.network,
        LoadFailure.offline,
      ),
    };

    cases.forEach((name, expected) {
      test(name, () async {
        final (scripted, kind, load) = expected;
        api.replies.add(scripted);
        final error = await failure(repo.getObject('/x', _named));
        expect(error.kind, kind);
        expect(loadFailureOf(error), load);
      });
    });

    test('rate limiting carries the wait', () async {
      api.replies.add(reply(429, null, {'retry-after': '7'}));
      final error = await failure(repo.getObject('/x', _named));
      expect(error.retryAfter, const Duration(seconds: 7));
    });

    test('problem details keep the support reference', () async {
      api.replies.add(
        reply(500, {'title': 'Boom', 'correlation_id': 'abc123'}),
      );
      final error = await failure(repo.getObject('/x', _named));
      expect(supportReferenceOf(error), 'abc123');
    });

    test('other errors are unknown and retryable', () {
      expect(loadFailureOf(StateError('x')), LoadFailure.unknown);
      expect(LoadFailure.unknown.retryable, isTrue);
      expect(LoadFailure.signedOut.retryable, isFalse);
      expect(LoadFailure.forbidden.retryable, isFalse);
      expect(LoadFailure.offline.retryable, isTrue);
    });
  });

  group('LoadErrorView', () {
    Future<void> show(WidgetTester tester, Object error) => tester.pumpApp(
      Scaffold(
        body: LoadErrorView(error: error, onRetry: () {}),
      ),
    );

    testWidgets('offline says so and offers Retry', (tester) async {
      await show(tester, const ApiException(ApiErrorKind.network));
      expect(find.text("You're offline"), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
    });

    testWidgets('a ended session offers no Retry', (tester) async {
      await show(tester, const ApiException(ApiErrorKind.unauthenticated));
      expect(find.text('Your session has ended'), findsOneWidget);
      expect(find.text('Try again'), findsNothing);
    });

    testWidgets('shows the support reference, not the exception', (
      tester,
    ) async {
      await show(
        tester,
        const ApiException(
          ApiErrorKind.server,
          detail: 'stack trace here',
          correlationId: 'abc123',
        ),
      );
      expect(find.textContaining('Reference: abc123'), findsOneWidget);
      expect(find.textContaining('stack trace'), findsNothing);
    });

    testWidgets('a non-API error is the generic state', (tester) async {
      await show(tester, const DataLoadException('Demo failure injected'));
      expect(find.text('Something went wrong'), findsOneWidget);
      expect(find.textContaining('Demo failure'), findsNothing);
    });

    testWidgets('AsyncValueView uses it for a failed first load', (
      tester,
    ) async {
      await tester.pumpApp(
        Scaffold(
          body: AsyncValueView<int>(
            value: const AsyncError<int>(
              ApiException(ApiErrorKind.network),
              StackTrace.empty,
            ),
            data: (_) => const Text('data'),
            onRetry: () {},
          ),
        ),
      );
      expect(find.text("You're offline"), findsOneWidget);
    });
  });

  group('data-source mode', () {
    ProviderContainer container(String source) => ProviderContainer(
      overrides: [
        appConfigProvider.overrideWithValue(
          AppConfig(
            apiBaseUrl: config.apiBaseUrl,
            oidcIssuer: config.oidcIssuer,
            dataSource: source,
          ),
        ),
      ],
    );

    test('starts from WS_DATA_SOURCE', () {
      expect(
        container('live').read(dataSourceModeProvider),
        DataSourceMode.live,
      );
      expect(
        container('demo').read(dataSourceModeProvider),
        DataSourceMode.demo,
      );
    });

    test('an unknown value is refused', () {
      expect(
        () => container('staging').read(dataSourceModeProvider),
        throwsA(anything),
      );
    });

    test('the default is demo', () {
      expect(
        const AppConfig(apiBaseUrl: 'x', oidcIssuer: 'y').dataSource,
        'demo',
      );
    });

    test('an unwired live repository fails loudly', () {
      final c = container('live');
      addTearDown(c.dispose);
      expect(
        () => liveNotWired('PortfolioRepository'),
        throwsA(isA<UnsupportedError>()),
      );
      c.read(dataSourceModeProvider.notifier).set(DataSourceMode.demo);
      expect(c.read(dataSourceModeProvider), DataSourceMode.demo);
    });
  });
}

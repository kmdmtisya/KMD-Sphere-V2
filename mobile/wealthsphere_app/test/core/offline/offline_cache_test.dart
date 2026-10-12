@Tags(['security'])
library;

import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/auth_controller.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_manager.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';
import 'package:wealthsphere_app/core/connectivity/connectivity.dart';
import 'package:wealthsphere_app/core/network/api_client.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';
import 'package:wealthsphere_app/core/offline/connectivity_banner.dart';
import 'package:wealthsphere_app/core/offline/offline_interceptor.dart';
import 'package:wealthsphere_app/core/offline/snapshot_cache.dart';

import '../../helpers/auth_fakes.dart';
import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';

const config = AppConfig(
  apiBaseUrl: 'http://127.0.0.1:8000',
  oidcIssuer: 'http://127.0.0.1:8081/realms/wealthsphere',
);

void main() {
  group('EncryptedSnapshotCache', () {
    late Directory root;
    late InMemoryCacheKeyStore keys;
    String? user;

    EncryptedSnapshotCache cache() => EncryptedSnapshotCache(
      root: () async => root,
      keys: keys,
      user: () => user,
    );

    setUp(() {
      root = Directory.systemTemp.createTempSync('ws_cache_test');
      keys = InMemoryCacheKeyStore();
      user = 'alice-subject';
    });
    tearDown(() => root.deleteSync(recursive: true));

    List<File> files() => [
      for (final f in root.listSync(recursive: true))
        if (f is File) f,
    ];

    test('round-trips the body and the time it was saved', () async {
      final saved = DateTime.utc(2026, 10, 12, 9);
      await cache().write('GET /api/v1/net-worth?', {
        'net_worth': '12000.00',
      }, saved);
      final back = await cache().read('GET /api/v1/net-worth?');
      expect(back!.body, {'net_worth': '12000.00'});
      expect(back.savedAt, saved);
    });

    test('nothing readable is on disk: no amounts, ids or paths', () async {
      await cache().write('GET /api/v1/portfolios/p-secret-id/summary?', {
        'total_value': {'amount': '987654.32', 'currency': 'USD'},
      }, DateTime.utc(2026));
      final file = files().single;
      final bytes = file.readAsBytesSync();
      final asText = latin1.decode(bytes);
      expect(asText, isNot(contains('987654.32')));
      expect(asText, isNot(contains('total_value')));
      expect(file.path, isNot(contains('p-secret-id')));
      expect(file.path, isNot(contains('alice')));
    });

    test('one user cannot read another user\'s saved data', () async {
      await cache().write('GET /x?', {'v': 1}, DateTime.utc(2026));
      user = 'bob-subject';
      expect(await cache().read('GET /x?'), isNull);
    });

    test('no signed-in user: nothing is saved or read', () async {
      user = null;
      await cache().write('GET /x?', {'v': 1}, DateTime.utc(2026));
      expect(files(), isEmpty);
      expect(await cache().read('GET /x?'), isNull);
    });

    test('wipe removes every file and the key', () async {
      await cache().write('GET /x?', {'v': 1}, DateTime.utc(2026));
      expect(keys.key, isNotNull);
      await cache().wipe();
      expect(files(), isEmpty);
      expect(keys.key, isNull);
      expect(await cache().read('GET /x?'), isNull);
    });

    test('a different key cannot decrypt old files', () async {
      await cache().write('GET /x?', {'v': 1}, DateTime.utc(2026));
      keys.key = List<int>.filled(32, 7);
      expect(await cache().read('GET /x?'), isNull);
    });
  });

  group('OfflineInterceptor', () {
    late FakeAdapter api;
    late MemorySnapshotCache cache;
    late Dio dio;
    late List<String> events;
    late TokenManager manager;

    setUp(() {
      api = FakeAdapter();
      cache = MemorySnapshotCache();
      events = [];
      manager = TokenManager(
        store: InMemoryTokenStore(tokens('a')),
        client: FakeOidcClient(),
        clock: () => epoch,
      );
      dio = buildApiClient(
        config: config,
        tokens: manager,
        adapter: api,
        after: [
          OfflineInterceptor(
            cache,
            onOnline: () => events.add('online'),
            onOffline: (at) => events.add('offline ${at?.toIso8601String()}'),
            clock: () => DateTime.utc(2026, 10, 12, 8),
          ),
        ],
      );
    });

    test('a good GET is saved; offline, the saved copy is served', () async {
      api.replies.addAll([
        reply(200, {'net_worth': '1.00'}),
        DioExceptionType.connectionError,
      ]);
      await dio.get<Object?>('/api/v1/net-worth');
      final offline = await dio.get<Object?>('/api/v1/net-worth');
      expect(offline.data, {'net_worth': '1.00'});
      expect(
        offline.requestOptions.extra[OfflineInterceptor.savedAtKey],
        DateTime.utc(2026, 10, 12, 8),
      );
      expect(events, ['online', 'offline 2026-10-12T08:00:00.000Z']);
    });

    test('a timeout with nothing saved is still an offline error', () async {
      api.replies.add(DioExceptionType.receiveTimeout);
      try {
        await dio.get<Object?>('/api/v1/goals');
        fail('expected an error');
      } on DioException catch (e) {
        expect(ApiException.fromDio(e).kind, ApiErrorKind.network);
      }
      expect(events, ['offline null']);
    });

    for (final status in [401, 403, 404, 500]) {
      test(
        'an HTTP $status is shown as itself, never hidden by saved data',
        () async {
          api.replies.addAll([
            reply(200, {'v': 1}),
            reply(status),
            if (status == 401) reply(status),
          ]);
          await dio.get<Object?>('/api/v1/goals');
          await expectLater(
            dio.get<Object?>('/api/v1/goals'),
            throwsA(isA<DioException>()),
          );
        },
      );
    }

    test('writes are never saved or replayed', () async {
      api.replies.addAll([
        reply(201, {'id': 't1'}),
        DioExceptionType.connectionError,
      ]);
      await dio.post<Object?>('/api/v1/goals', data: {});
      expect(cache.entries, isEmpty);
      await expectLater(
        dio.post<Object?>('/api/v1/goals', data: {}),
        throwsA(isA<DioException>()),
      );
    });

    test('query parameters are part of what is saved', () async {
      api.replies.addAll([
        reply(200, {'p': 'monthly'}),
        DioExceptionType.connectionError,
      ]);
      await dio.get<Object?>('/r', queryParameters: {'frequency': 'monthly'});
      await expectLater(
        dio.get<Object?>('/r', queryParameters: {'frequency': 'daily'}),
        throwsA(isA<DioException>()),
        reason: 'a different request has no saved copy',
      );
    });

    test(
      'a token refresh that cannot reach sign-in is treated as offline',
      () async {
        // An expired access token with no reachable identity provider.
        final expired = TokenManager(
          store: InMemoryTokenStore(tokens('a', expiresAt: epoch)),
          client: FakeOidcClient()
            ..refreshResults.add(const AuthException(AuthFailure.network)),
          clock: () => epoch.add(const Duration(hours: 1)),
        );
        final offline = buildApiClient(
          config: config,
          tokens: expired,
          adapter: api,
          after: [
            OfflineInterceptor(
              cache
                ..entries['GET /api/v1/goals?'] = Snapshot(const [
                  <String, Object?>{},
                ], DateTime.utc(2026)),
              onOnline: () => events.add('online'),
              onOffline: (_) => events.add('offline'),
            ),
          ],
        );
        final r = await offline.get<Object?>('/api/v1/goals');
        expect(r.data, const [<String, Object?>{}]);
        expect(events, ['offline']);
      },
    );
  });

  group('connectivity state', () {
    test('reconnecting clears the saved age and reloads live data', () {
      final c = ProviderContainer();
      addTearDown(c.dispose);
      final online = c.read(onlineProvider.notifier);
      online.unreachable(DateTime.utc(2026, 10, 12, 7));
      online.unreachable(DateTime.utc(2026, 10, 12, 9));
      expect(c.read(onlineProvider), isFalse);
      expect(
        c.read(savedDataAsOfProvider),
        DateTime.utc(2026, 10, 12, 7),
        reason: 'the oldest',
      );
      final before = c.read(dataEpochProvider);
      online.reachedServer();
      expect(c.read(onlineProvider), isTrue);
      expect(c.read(savedDataAsOfProvider), isNull);
      expect(c.read(dataEpochProvider), before + 1);
      online.reachedServer();
      expect(
        c.read(dataEpochProvider),
        before + 1,
        reason: 'only on the way back',
      );
    });
  });

  group('sign-out', () {
    test(
      'wipes saved data and reloads so nothing carries to the next user',
      () async {
        final cache = MemorySnapshotCache()
          ..entries['GET /api/v1/net-worth?'] = Snapshot(
            const {},
            DateTime.utc(2026),
          );
        final c = ProviderContainer(
          overrides: [
            snapshotCacheProvider.overrideWithValue(cache),
            tokenStoreProvider.overrideWithValue(
              InMemoryTokenStore(tokens('a')),
            ),
            oidcClientProvider.overrideWithValue(FakeOidcClient()),
          ],
        );
        addTearDown(c.dispose);
        c.read(authControllerProvider);
        await Future<void>.delayed(Duration.zero);
        final before = c.read(dataEpochProvider);
        await c.read(authControllerProvider.notifier).signOut();
        expect(cache.entries, isEmpty);
        expect(cache.wipes, 1);
        expect(c.read(dataEpochProvider), greaterThan(before));
      },
    );
  });

  group('ConnectivityBanner', () {
    testWidgets('silent while online and in DEMO mode', (tester) async {
      await tester.pumpApp(const Scaffold(body: ConnectivityBanner()));
      expect(find.byType(Text), findsNothing);
    });

    testWidgets('offline in live mode: says so, with the saved data age', (
      tester,
    ) async {
      await tester.pumpApp(
        Consumer(
          builder: (context, ref, _) => Scaffold(
            body: Column(
              children: [
                ConnectivityBanner(now: DateTime.utc(2026, 10, 12, 12)),
                TextButton(
                  onPressed: () => ref
                      .read(onlineProvider.notifier)
                      .unreachable(DateTime.utc(2026, 10, 12, 10)),
                  child: const Text('drop'),
                ),
              ],
            ),
          ),
        ),
        overrides: demoOverrides(extra: [liveModeOverride()]),
      );
      await tester.tap(find.text('drop'));
      await tester.pump();
      expect(
        find.textContaining("You're offline. Showing saved data"),
        findsOneWidget,
      );
      expect(find.textContaining('2 hours ago'), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
    });
  });
}

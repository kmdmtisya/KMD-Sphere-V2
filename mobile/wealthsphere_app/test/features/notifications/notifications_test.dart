import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/auth/auth_controller.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/offline/snapshot_cache.dart';
import 'package:wealthsphere_app/features/alerts/data/alerts_repository.dart';
import 'package:wealthsphere_app/features/alerts/domain/alert_models.dart';
import 'package:wealthsphere_app/features/alerts/presentation/alert_preferences_card.dart';
import 'package:wealthsphere_app/features/investments/data/investment_repository.dart';
import 'package:wealthsphere_app/features/investments/domain/investment_models.dart';
import 'package:wealthsphere_app/features/notifications/deep_link_host.dart';
import 'package:wealthsphere_app/features/notifications/notification_service.dart';
import 'package:wealthsphere_app/shared/design_system/components/period_selector.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/auth_fakes.dart';
import '../../helpers/demo_overrides.dart';
import '../../helpers/fake_api.dart';
import '../../helpers/pump_app.dart';

class _Token implements PushTokenSource {
  @override
  Future<({String platform, String token})?> token() async =>
      (platform: 'android', token: 'token-1234567890');
}

class _Devices implements DeviceRepository {
  final List<String> registered = [];
  final List<String> removed = [];

  @override
  Future<String> register({
    required String platform,
    required String token,
  }) async {
    registered.add(token);
    return 'dev-1';
  }

  @override
  Future<void> remove(String deviceId) async => removed.add(deviceId);
}

void main() {
  group('NotificationRoute', () {
    test('accepts only in-app routes from the list', () {
      expect(
        NotificationRoute.fromPayload({'route': '/more/alerts'})!.path,
        AppRoutes.alerts,
      );
      expect(
        NotificationRoute.fromPayload({'route': '/goals?x=1'})!.path,
        AppRoutes.goals,
      );
    });

    for (final bad in [
      null,
      42,
      '',
      'https://evil.example/more/alerts',
      '//evil.example/more/alerts',
      'wealthsphere://more/alerts',
      '/more/settings',
      '/unknown',
      'more/alerts',
    ]) {
      test('ignores $bad', () {
        expect(NotificationRoute.fromPayload({'route': bad}), isNull);
      });
    }

    test('a payload without a route is ignored', () {
      expect(
        NotificationRoute.fromPayload({'type': 'alert_triggered'}),
        isNull,
      );
    });
  });

  group('deep link opens after authentication', () {
    late FakeOidcClient oidc;
    late ProviderContainer container;

    ProviderContainer make() => ProviderContainer(
      overrides: [
        snapshotCacheProvider.overrideWithValue(MemorySnapshotCache()),
        tokenStoreProvider.overrideWithValue(InMemoryTokenStore()),
        oidcClientProvider.overrideWithValue(oidc),
      ],
    );

    setUp(() {
      oidc = FakeOidcClient();
      container = make();
      addTearDown(container.dispose);
    });

    test('a link waits while signed out', () async {
      await Future<void>.delayed(Duration.zero);
      container.read(authControllerProvider);
      await Future<void>.delayed(Duration.zero);
      container.read(pendingDeepLinkProvider.notifier).received({
        'route': '/more/alerts',
      });
      expect(container.read(pendingDeepLinkProvider), isNotNull);
      expect(container.read(deepLinkToOpenProvider), isNull);
    });

    test('once signed in, the link is ready to open', () async {
      oidc.signInResults.add(tokens('a'));
      container.read(authControllerProvider);
      await Future<void>.delayed(Duration.zero);
      container.read(pendingDeepLinkProvider.notifier).received({
        'route': '/more/alerts',
      });
      await container.read(authControllerProvider.notifier).signIn();
      expect(container.read(deepLinkToOpenProvider)!.path, AppRoutes.alerts);
    });

    test('signing out drops a waiting link', () async {
      oidc.signInResults.add(tokens('a'));
      container
        ..read(notificationWiringProvider)
        ..read(authControllerProvider);
      await Future<void>.delayed(Duration.zero);
      await container.read(authControllerProvider.notifier).signIn();
      container.read(pendingDeepLinkProvider.notifier).received({
        'route': '/goals',
      });
      await container.read(authControllerProvider.notifier).signOut();
      expect(container.read(pendingDeepLinkProvider), isNull);
    });
  });

  testWidgets('the host sends the user to the screen and forgets the link', (
    tester,
  ) async {
    final oidc = FakeOidcClient()..signInResults.add(tokens('a'));
    final router = GoRouter(
      routes: [
        GoRoute(path: '/', builder: (_, _) => const Text('start')),
        GoRoute(
          path: AppRoutes.alerts,
          builder: (_, _) => const Text('alerts'),
        ),
      ],
    );
    addTearDown(router.dispose);
    late ProviderContainer container;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          snapshotCacheProvider.overrideWithValue(MemorySnapshotCache()),
          tokenStoreProvider.overrideWithValue(InMemoryTokenStore()),
          oidcClientProvider.overrideWithValue(oidc),
        ],
        child: Builder(
          builder: (context) {
            container = ProviderScope.containerOf(context);
            return MaterialApp.router(
              routerConfig: router,
              builder: (context, child) =>
                  DeepLinkHost(router: router, child: child!),
            );
          },
        ),
      ),
    );
    await tester.pump();
    container.read(pendingDeepLinkProvider.notifier).received({
      'route': '/more/alerts',
    });
    await tester.pump();
    expect(find.text('start'), findsOneWidget, reason: 'signed out: it waits');
    await container.read(authControllerProvider.notifier).signIn();
    await tester.pumpAndSettle();
    expect(find.text('alerts'), findsOneWidget);
    expect(container.read(pendingDeepLinkProvider), isNull);
  });

  group('device registration', () {
    test('registers at sign-in and removes at sign-out', () async {
      final devices = _Devices();
      final oidc = FakeOidcClient()..signInResults.add(tokens('a'));
      final c = ProviderContainer(
        overrides: [
          snapshotCacheProvider.overrideWithValue(MemorySnapshotCache()),
          tokenStoreProvider.overrideWithValue(InMemoryTokenStore()),
          oidcClientProvider.overrideWithValue(oidc),
          pushTokenSourceProvider.overrideWithValue(_Token()),
          deviceRepositoryProvider.overrideWithValue(devices),
        ],
      );
      addTearDown(c.dispose);
      c
        ..read(notificationWiringProvider)
        ..read(authControllerProvider);
      await Future<void>.delayed(Duration.zero);
      await c.read(authControllerProvider.notifier).signIn();
      await Future<void>.delayed(Duration.zero);
      expect(devices.registered, ['token-1234567890']);
      await c.read(authControllerProvider.notifier).signOut();
      await Future<void>.delayed(Duration.zero);
      expect(devices.removed, ['dev-1']);
    });

    test('no push token means nothing is registered, and no error', () async {
      final devices = _Devices();
      final oidc = FakeOidcClient()..signInResults.add(tokens('a'));
      final c = ProviderContainer(
        overrides: [
          snapshotCacheProvider.overrideWithValue(MemorySnapshotCache()),
          tokenStoreProvider.overrideWithValue(InMemoryTokenStore()),
          oidcClientProvider.overrideWithValue(oidc),
          deviceRepositoryProvider.overrideWithValue(devices),
        ],
      );
      addTearDown(c.dispose);
      c
        ..read(notificationWiringProvider)
        ..read(authControllerProvider);
      await Future<void>.delayed(Duration.zero);
      await c.read(authControllerProvider.notifier).signIn();
      await Future<void>.delayed(Duration.zero);
      expect(devices.registered, isEmpty);
    });

    test('the live repository posts the platform and token', () async {
      final api = FakeApi()
        ..json('POST /api/v1/devices', {'id': 'd9'}, status: 201)
        ..json('DELETE /api/v1/devices/d9', null, status: 204);
      final repo = LiveDeviceRepository(api.dio());
      final id = await repo.register(platform: 'ios', token: 'abc-123-token');
      await repo.remove(id);
      expect(api.calls.first.body, {
        'platform': 'ios',
        'token': 'abc-123-token',
      });
      expect(api.callsTo('DELETE', '/api/v1/devices/d9'), hasLength(1));
    });
  });

  group('alert preferences', () {
    test('live repository reads and writes the three switches', () async {
      final api = FakeApi()
        ..json('GET /api/v1/alert-preferences', {
          'alerts_enabled': true,
          'price_alerts_enabled': false,
          'allocation_alerts_enabled': true,
        })
        ..json('PUT /api/v1/alert-preferences', {
          'alerts_enabled': false,
          'price_alerts_enabled': false,
          'allocation_alerts_enabled': true,
        });
      final repo = LiveAlertRepository(api.dio());
      final p = await repo.preferences();
      expect(p.priceAlertsEnabled, isFalse);
      final saved = await repo.savePreferences(
        p.copyWith(alertsEnabled: false),
      );
      expect(saved.alertsEnabled, isFalse);
      expect(api.callsTo('PUT', '/api/v1/alert-preferences').single.body, {
        'alerts_enabled': false,
        'price_alerts_enabled': false,
        'allocation_alerts_enabled': true,
      });
    });

    testWidgets('switches save, and the master switch disables the others', (
      tester,
    ) async {
      final repo = DemoAlertRepository(_NoInvestments(), () async {});
      await tester.pumpApp(
        const Scaffold(body: AlertPreferencesCard()),
        overrides: demoOverrides(
          extra: [alertRepositoryProvider.overrideWithValue(repo)],
        ),
      );
      expect(find.text('Price alerts'), findsOneWidget);
      await tester.tap(find.text('Price alerts'));
      await tester.pumpAndSettle();
      expect((await repo.preferences()).priceAlertsEnabled, isFalse);
      await tester.tap(find.text('Alerts'));
      await tester.pumpAndSettle();
      expect((await repo.preferences()).alertsEnabled, isFalse);
      final tile = tester.widget<SwitchListTile>(
        find.widgetWithText(SwitchListTile, 'Allocation alerts'),
      );
      expect(tile.onChanged, isNull);
      expect(const AlertPreferences(), const AlertPreferences());
    });
  });
}

class _NoInvestments implements InvestmentRepository {
  @override
  Future<InvestmentDetail> detail(String key) => throw UnimplementedError();

  @override
  Future<PerformanceSeries> priceHistory(String key, ChartPeriod period) =>
      throw UnimplementedError();
}

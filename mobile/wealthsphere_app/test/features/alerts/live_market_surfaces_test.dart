import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/network/asset_catalog.dart';
import 'package:wealthsphere_app/features/alerts/data/alerts_repository.dart';
import 'package:wealthsphere_app/features/alerts/domain/alert_models.dart';
import 'package:wealthsphere_app/features/alerts/presentation/watchlist_alerts_screen.dart';
import 'package:wealthsphere_app/features/investments/data/investment_repository.dart';
import 'package:wealthsphere_app/features/investments/data/live_investment_repository.dart';
import 'package:wealthsphere_app/features/investments/presentation/investment_detail_screen.dart';
import 'package:wealthsphere_app/shared/design_system/components/period_selector.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/money.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/fake_api.dart';
import '../../helpers/pump_app.dart';

final now = DateTime.utc(2026, 10, 12, 12);

Map<String, Object?> assetJson(String id, {String? symbol = 'ACM'}) => {
  'id': id,
  'symbol': symbol,
  'name': 'Acme Corp',
  'asset_class': 'stock',
  'asset_class_name': 'Stocks',
  'currency': 'USD',
};

Map<String, Object?> pricesJson({bool stale = false, bool none = false}) => {
  'asset_id': 'a1',
  'currency': 'USD',
  'latest': none
      ? null
      : {
          'price': '123.456789',
          'currency': 'USD',
          'as_of': '2026-10-12T10:00:00Z',
          'provider': 'twelvedata',
          'stale': stale,
        },
  'points': none
      ? <Object?>[]
      : [
          {'on': '2026-10-08', 'close': '120.5', 'provider': 'twelvedata'},
          {'on': '2026-10-09', 'close': '121.25', 'provider': 'twelvedata'},
        ],
  'data_type': 'delayed',
};

FakeApi backend({bool stale = false, bool noPrice = false}) => FakeApi()
  ..json('GET /api/v1/assets/a1', assetJson('a1'))
  ..json(
    'GET /api/v1/assets/a1/prices',
    pricesJson(stale: stale, none: noPrice),
  )
  ..json('GET /api/v1/watchlist', <Object?>[])
  ..json('GET /api/v1/alerts', <Object?>[])
  ..json('GET /api/v1/alerts/events', {'items': <Object?>[]});

List<Override> live(FakeApi api) {
  final dio = api.dio();
  return demoOverrides(
    extra: [
      liveModeOverride(),
      investmentRepositoryProvider.overrideWithValue(
        LiveInvestmentRepository(
          dio,
          AssetCatalog(dio),
          () async => const <PortfolioRef>[],
          clock: () => now,
        ),
      ),
      watchlistRepositoryProvider.overrideWithValue(
        LiveWatchlistRepository(dio),
      ),
      alertRepositoryProvider.overrideWithValue(LiveAlertRepository(dio)),
    ],
  );
}

void main() {
  group('investment prices', () {
    test(
      'the latest stored price, unrounded, with provider and time',
      () async {
        final api = backend();
        final dio = api.dio();
        final repo = LiveInvestmentRepository(
          dio,
          AssetCatalog(dio),
          () async => const <PortfolioRef>[],
          clock: () => now,
        );
        final d = await repo.detail('a1');
        expect(d.price!.amount, Decimal.parse('123.456789'));
        expect(d.priceSource!.provider, 'twelvedata');
        expect(d.priceSource!.asOf, DateTime.utc(2026, 10, 12, 10));
        expect(d.priceStale, isFalse);
        expect(d.changePercent, isNull, reason: 'no daily change is invented');
      },
    );

    test(
      'history is the stored closes for the period, nothing filled in',
      () async {
        final api = backend();
        final dio = api.dio();
        final repo = LiveInvestmentRepository(
          dio,
          AssetCatalog(dio),
          () async => const <PortfolioRef>[],
          clock: () => now,
        );
        final s = await repo.priceHistory('a1', ChartPeriod.month);
        expect(
          [for (final p in s.points) p.value],
          [Decimal.parse('120.5'), Decimal.parse('121.25')],
        );
        expect(
          api.callsTo('GET', '/api/v1/assets/a1/prices').single.query['start'],
          '2026-09-12',
        );
      },
    );
  });

  group('watchlist and alerts repositories', () {
    test(
      'watch items carry the unrounded stored price and its freshness',
      () async {
        final api = FakeApi()
          ..json('GET /api/v1/watchlist', [
            {
              'asset': {
                'id': 'a1',
                'symbol': 'BTC',
                'name': 'Bitcoin',
                'asset_class': 'cryptocurrency',
                'currency': 'USD',
              },
              'added_at': '2026-10-01T00:00:00Z',
              'latest_price': {
                'price': '0.000123',
                'currency': 'USD',
                'as_of': '2026-10-12T09:00:00Z',
                'provider': 'coingecko',
                'stale': true,
              },
            },
            {
              'asset': {
                'id': 'a2',
                'symbol': null,
                'name': 'Flat',
                'asset_class': 'real_estate',
                'currency': 'USD',
              },
              'added_at': '2026-10-01T00:00:00Z',
              'latest_price': null,
            },
          ]);
        final items = await LiveWatchlistRepository(api.dio()).items();
        expect(items.first.price!.amount, Decimal.parse('0.000123'));
        expect(items.first.stale, isTrue);
        expect(items.last.price, isNull);
      },
    );

    test('add and remove call the watchlist routes', () async {
      final api = FakeApi()
        ..json('POST /api/v1/watchlist', {
          'asset': <String, Object?>{},
        }, status: 201)
        ..json('DELETE /api/v1/watchlist/a1', null, status: 204);
      final repo = LiveWatchlistRepository(api.dio());
      await repo.add('a1');
      await repo.remove('a1');
      expect(api.callsTo('POST', '/api/v1/watchlist').single.body, {
        'asset_id': 'a1',
      });
      expect(api.callsTo('DELETE', '/api/v1/watchlist/a1'), hasLength(1));
    });

    test('a price alert is sent in the asset currency', () async {
      final api = FakeApi()
        ..json('POST /api/v1/alerts', {
          'id': 'al1',
          'alert_type': 'price_below',
          'status': 'active',
          'asset': {'id': 'a1', 'symbol': 'ACM', 'name': 'Acme Corp'},
          'threshold_price': usd('100.00'),
          'created_at': '2026-10-12T10:00:00Z',
        }, status: 201);
      final alert = await LiveAlertRepository(api.dio()).createPriceAlert(
        assetKey: 'a1',
        type: AlertType.priceBelow,
        threshold: Money(Decimal.parse('100'), 'USD'),
      );
      expect(api.calls.single.body, {
        'alert_type': 'price_below',
        'asset_id': 'a1',
        'threshold_price': {'amount': '100', 'currency': 'USD'},
      });
      expect(alert.status, AlertStatus.active);
    });

    test('pausing, re-arming and reading fired alerts', () async {
      final api = FakeApi()
        ..on('PATCH /api/v1/alerts/al1', (c) {
          final status = (c.body! as Map<String, Object?>)['status'];
          return (
            200,
            {
              'id': 'al1',
              'alert_type': 'price_above',
              'status': status,
              'created_at': '2026-10-12T10:00:00Z',
            },
          );
        })
        ..json('GET /api/v1/alerts/events', {
          'items': [
            {
              'id': 'e1',
              'alert_id': 'al1',
              'alert_type': 'price_above',
              'observed_value': '130.5',
              'observed_as_of': '2026-10-12T09:00:00Z',
              'triggered_at': '2026-10-12T09:05:00Z',
              'seen_at': null,
            },
          ],
        })
        ..json('POST /api/v1/alerts/events/e1/seen', {'id': 'e1'});
      final repo = LiveAlertRepository(api.dio());
      expect(
        (await repo.setActive('al1', active: false)).status,
        AlertStatus.paused,
      );
      expect(
        (await repo.setActive('al1', active: true)).status,
        AlertStatus.active,
      );
      final events = await repo.events(unseenOnly: true);
      expect(events.single.observedValue, Decimal.parse('130.5'));
      expect(api.callsTo('GET', '/api/v1/alerts/events').single.query, {
        'unseen': 'true',
      });
      await repo.markSeen('e1');
      expect(
        api.callsTo('POST', '/api/v1/alerts/events/e1/seen'),
        hasLength(1),
      );
    });
  });

  group('screens', () {
    testWidgets('a stale price is labelled on the investment page', (
      tester,
    ) async {
      await tester.pumpApp(
        const InvestmentDetailScreen(symbol: 'a1'),
        overrides: live(backend(stale: true)),
        surfaceSize: const Size(400, 2000),
      );
      expect(
        find.text(r'$123.4568'),
        findsNothing,
        reason: 'not reformatted into a guess',
      );
      expect(find.text('Price out of date'), findsOneWidget);
      expect(find.text('Delayed market price'), findsOneWidget);
    });

    testWidgets('no stored price: says so, no number', (tester) async {
      await tester.pumpApp(
        const InvestmentDetailScreen(symbol: 'a1'),
        overrides: live(backend(noPrice: true)),
        surfaceSize: const Size(400, 2000),
      );
      expect(find.text('No market price yet'), findsOneWidget);
    });

    testWidgets('setting a price alert from the investment page', (
      tester,
    ) async {
      final api = backend()
        ..json('POST /api/v1/alerts', {
          'id': 'al1',
          'alert_type': 'price_above',
          'status': 'active',
          'created_at': '2026-10-12T10:00:00Z',
        }, status: 201);
      await tester.pumpApp(
        const InvestmentDetailScreen(symbol: 'a1'),
        overrides: live(api),
        surfaceSize: const Size(400, 2000),
      );
      await tester.tap(find.byTooltip('Set a price alert'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '0');
      await tester.tap(find.text('Set alert'));
      await tester.pumpAndSettle();
      expect(find.text('Enter a price above zero.'), findsOneWidget);
      await tester.enterText(find.byType(TextField), '150.25');
      await tester.tap(find.text('Set alert'));
      await tester.pumpAndSettle();
      final body =
          api.callsTo('POST', '/api/v1/alerts').single.body!
              as Map<String, Object?>;
      expect(body['threshold_price'], {'amount': '150.25', 'currency': 'USD'});
      expect(find.textContaining('Alert set'), findsOneWidget);
    });

    testWidgets('watchlist and alerts screen shows freshness and conditions', (
      tester,
    ) async {
      final api = FakeApi()
        ..json('GET /api/v1/watchlist', [
          {
            'asset': {
              'id': 'a1',
              'symbol': 'ACM',
              'name': 'Acme Corp',
              'asset_class': 'stock',
              'currency': 'USD',
            },
            'added_at': '2026-10-01T00:00:00Z',
            'latest_price': {
              'price': '123.45',
              'currency': 'USD',
              'as_of': '2026-10-01T09:00:00Z',
              'provider': 'twelvedata',
              'stale': true,
            },
          },
          {
            'asset': {
              'id': 'a2',
              'symbol': null,
              'name': 'My flat',
              'asset_class': 'real_estate',
              'currency': 'USD',
            },
            'added_at': '2026-10-01T00:00:00Z',
            'latest_price': null,
          },
        ])
        ..json('GET /api/v1/alerts', [
          {
            'id': 'al1',
            'alert_type': 'price_above',
            'status': 'triggered',
            'asset': {'id': 'a1', 'symbol': 'ACM', 'name': 'Acme Corp'},
            'threshold_price': usd('120.00'),
            'created_at': '2026-10-01T10:00:00Z',
            'triggered_at': '2026-10-02T10:00:00Z',
          },
        ])
        ..json('GET /api/v1/alerts/events', {'items': <Object?>[]});
      final opened = <String>[];
      await tester.pumpApp(
        WatchlistAlertsScreen(onOpenInvestment: opened.add),
        overrides: live(api),
        surfaceSize: const Size(400, 2000),
      );
      expect(find.text(r'$123.45'), findsOneWidget);
      expect(find.text('Price out of date'), findsOneWidget);
      expect(find.text('No market price yet'), findsOneWidget);
      expect(find.text(r'When the price rises above $120.00'), findsOneWidget);
      expect(find.text('Triggered'), findsOneWidget);
      expect(find.text('Re-arm'), findsOneWidget);
      expect(find.text('DEMO'), findsNothing);
      await tester.tap(find.text('ACM').first);
      expect(opened, ['a1']);
    });
  });
}

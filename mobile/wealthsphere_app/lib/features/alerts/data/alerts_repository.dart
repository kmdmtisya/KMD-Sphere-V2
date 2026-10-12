import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../investments/data/investment_repository.dart';
import '../domain/alert_models.dart';

/// The investments the user follows. Read-only market data: nothing here places an order.
abstract interface class WatchlistRepository {
  Future<List<WatchItem>> items();
  Future<void> add(String assetKey);
  Future<void> remove(String assetKey);
}

/// Alerts the user set and the alerts that fired. Delivery to the device is P09-T08.
abstract interface class AlertRepository {
  Future<List<PriceAlert>> alerts();
  Future<PriceAlert> createPriceAlert({
    required String assetKey,
    required AlertType type,
    required Money threshold,
  });
  Future<PriceAlert> setActive(String id, {required bool active});
  Future<void> delete(String id);
  Future<List<AlertEvent>> events({bool unseenOnly = false});
  Future<void> markSeen(String eventId);
}

// --------------------------------------------------------------------------------- DEMO

/// In memory for the session, priced from the DEMO investment fixtures.
class DemoWatchlistRepository implements WatchlistRepository {
  DemoWatchlistRepository(this._investments, this._gate);

  final InvestmentRepository _investments;
  final Future<void> Function() _gate;
  final List<String> _keys = [];

  @override
  Future<List<WatchItem>> items() async {
    await _gate();
    return [
      for (final key in _keys)
        await _investments
            .detail(key)
            .then(
              (d) => WatchItem(
                assetKey: key,
                symbol: d.symbol,
                name: d.name,
                price: d.price,
                priceAsOf: d.priceSource?.asOf,
                provider: d.priceSource?.provider,
              ),
            ),
    ];
  }

  @override
  Future<void> add(String assetKey) async {
    await _gate();
    if (!_keys.contains(assetKey)) _keys.add(assetKey);
  }

  @override
  Future<void> remove(String assetKey) async {
    await _gate();
    _keys.remove(assetKey);
  }
}

/// In memory for the session. The demo never evaluates alerts (that is the server's job), so no
/// event ever fires here.
class DemoAlertRepository implements AlertRepository {
  DemoAlertRepository(this._investments, this._gate);

  final InvestmentRepository _investments;
  final Future<void> Function() _gate;
  final List<PriceAlert> _alerts = [];
  int _counter = 0;

  @override
  Future<List<PriceAlert>> alerts() async {
    await _gate();
    return List.unmodifiable(_alerts);
  }

  @override
  Future<PriceAlert> createPriceAlert({
    required String assetKey,
    required AlertType type,
    required Money threshold,
  }) async {
    await _gate();
    final d = await _investments.detail(assetKey);
    _counter++;
    final alert = PriceAlert(
      id: 'demo-alert-$_counter',
      type: type,
      status: AlertStatus.active,
      createdAt: DateTime.now().toUtc(),
      assetKey: assetKey,
      assetName: d.name,
      assetSymbol: d.symbol,
      thresholdPrice: threshold,
    );
    _alerts.add(alert);
    return alert;
  }

  @override
  Future<PriceAlert> setActive(String id, {required bool active}) async {
    await _gate();
    final i = _alerts.indexWhere((a) => a.id == id);
    if (i < 0) throw DataLoadException.unknown('alert', id);
    final a = _alerts[i];
    return _alerts[i] = PriceAlert(
      id: a.id,
      type: a.type,
      status: active ? AlertStatus.active : AlertStatus.paused,
      createdAt: a.createdAt,
      assetKey: a.assetKey,
      assetName: a.assetName,
      assetSymbol: a.assetSymbol,
      thresholdPrice: a.thresholdPrice,
    );
  }

  @override
  Future<void> delete(String id) async {
    await _gate();
    _alerts.removeWhere((a) => a.id == id);
  }

  @override
  Future<List<AlertEvent>> events({bool unseenOnly = false}) async {
    await _gate();
    return const [];
  }

  @override
  Future<void> markSeen(String eventId) async => _gate();
}

// --------------------------------------------------------------------------------- live

PriceAlert _alert(JsonReader r) {
  final hasAsset = r.has('asset');
  final asset = hasAsset ? r.object('asset') : null;
  return PriceAlert(
    id: r.string('id'),
    type: AlertType.parse(r.string('alert_type')),
    status: AlertStatus.parse(r.string('status')),
    createdAt: r.timestamp('created_at'),
    assetKey: asset?.string('id'),
    assetName: asset?.string('name'),
    assetSymbol: asset?.stringOrNull('symbol'),
    thresholdPrice: r.has('threshold_price')
        ? r.money('threshold_price')
        : null,
    assetClass: r.stringOrNull('asset_class'),
    thresholdPercent: r.has('threshold_percent')
        ? r.decimal('threshold_percent')
        : null,
    triggeredAt: r.has('triggered_at') ? r.timestamp('triggered_at') : null,
    note: r.stringOrNull('note'),
  );
}

AlertEvent _event(JsonReader r) => AlertEvent(
  id: r.string('id'),
  alertId: r.string('alert_id'),
  type: AlertType.parse(r.string('alert_type')),
  observedValue: r.decimal('observed_value'),
  observedAsOf: r.timestamp('observed_as_of'),
  triggeredAt: r.timestamp('triggered_at'),
  seenAt: r.has('seen_at') ? r.timestamp('seen_at') : null,
);

class LiveWatchlistRepository extends LiveRepository
    implements WatchlistRepository {
  const LiveWatchlistRepository(super.dio);

  @override
  Future<List<WatchItem>> items() => getList('/api/v1/watchlist', (r) {
    final asset = r.object('asset');
    final price = r.has('latest_price') ? r.object('latest_price') : null;
    return WatchItem(
      assetKey: asset.string('id'),
      symbol: asset.stringOrNull('symbol'),
      name: asset.string('name'),
      price: price == null
          ? null
          : Money(price.decimal('price'), price.string('currency')),
      priceAsOf: price?.timestamp('as_of'),
      provider: price?.string('provider'),
      stale: price != null && price.boolean('stale'),
    );
  });

  @override
  Future<void> add(String assetKey) =>
      send('POST', '/api/v1/watchlist', (r) => r, body: {'asset_id': assetKey});

  @override
  Future<void> remove(String assetKey) =>
      sendEmpty('DELETE', '/api/v1/watchlist/$assetKey');
}

class LiveAlertRepository extends LiveRepository implements AlertRepository {
  const LiveAlertRepository(super.dio);

  @override
  Future<List<PriceAlert>> alerts() => getList('/api/v1/alerts', _alert);

  @override
  Future<PriceAlert> createPriceAlert({
    required String assetKey,
    required AlertType type,
    required Money threshold,
  }) => send(
    'POST',
    '/api/v1/alerts',
    _alert,
    body: {
      'alert_type': type.apiName,
      'asset_id': assetKey,
      'threshold_price': threshold.toJson(),
    },
  );

  @override
  Future<PriceAlert> setActive(String id, {required bool active}) => send(
    'PATCH',
    '/api/v1/alerts/$id',
    _alert,
    body: {'status': active ? 'active' : 'paused'},
  );

  @override
  Future<void> delete(String id) => sendEmpty('DELETE', '/api/v1/alerts/$id');

  @override
  Future<List<AlertEvent>> events({bool unseenOnly = false}) => getObject(
    '/api/v1/alerts/events',
    (r) => r.list('items', _event),
    query: {if (unseenOnly) 'unseen': true},
  );

  @override
  Future<void> markSeen(String eventId) =>
      send('POST', '/api/v1/alerts/events/$eventId/seen', (r) => r);
}

final watchlistRepositoryProvider = Provider<WatchlistRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoWatchlistRepository(
        ref.watch(investmentRepositoryProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
    case DataSourceMode.live:
      return LiveWatchlistRepository(ref.watch(apiClientProvider));
  }
});

final alertRepositoryProvider = Provider<AlertRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoAlertRepository(
        ref.watch(investmentRepositoryProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
    case DataSourceMode.live:
      return LiveAlertRepository(ref.watch(apiClientProvider));
  }
});

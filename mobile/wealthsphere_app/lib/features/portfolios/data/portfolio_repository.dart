import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../../../shared/design_system/components/period_selector.dart';
import '../../../shared/domain/wealth_models.dart';

/// Portfolio data. A `portfolioId` of [PortfolioRef.consolidatedId] means all portfolios combined.
abstract interface class PortfolioRepository {
  Future<List<PortfolioRef>> portfolios();
  Future<PortfolioSummary> summary(String portfolioId);
  Future<PerformanceSeries> performance(String portfolioId, ChartPeriod period);
  Future<List<AllocationShare>> allocation(String portfolioId);
  Future<PerformanceMetrics> metrics(String portfolioId);
  Future<List<HoldingSummary>> holdings(String portfolioId);
}

/// Reads the portfolio fixtures in `assets/demo`.
class DemoPortfolioRepository implements PortfolioRepository {
  DemoPortfolioRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;

  Future<JsonReader> _doc(String file) async {
    await _gate();
    return JsonReader(await _assets.load(file));
  }

  T _byId<T>(Map<String, T> items, String id, String what) {
    final item = items[id];
    if (item == null) throw DataLoadException('Unknown $what "$id"');
    return item;
  }

  @override
  Future<List<PortfolioRef>> portfolios() async =>
      (await _doc('portfolios.json')).list('portfolios', PortfolioRef.fromJson);

  @override
  Future<PortfolioSummary> summary(String portfolioId) async {
    final all = (await _doc('portfolios.json'))
        .mapOf('summaries', PortfolioSummary.fromJson);
    return _byId(all, portfolioId, 'portfolio');
  }

  @override
  Future<PerformanceSeries> performance(
    String portfolioId,
    ChartPeriod period,
  ) async {
    final doc = await _doc('performance.json');
    final byPortfolio = doc.mapOf('performance', (r) => r);
    final periods = _byId(byPortfolio, portfolioId, 'portfolio');
    final points = periods.list(period.name, (p) {
      return PerformancePoint(p.date('date'), p.decimal('value'));
    });
    return PerformanceSeries(
      period: period,
      currencyCode: doc.string('currency'),
      points: points,
      asOf: doc.timestamp('as_of'),
    );
  }

  @override
  Future<List<AllocationShare>> allocation(String portfolioId) async {
    final all = (await _doc('allocation.json')).mapOf('allocation', (r) => r);
    final reader = _byId(all, portfolioId, 'portfolio');
    // The value is a JSON list at the top level of each entry; read it through a wrapper object.
    return reader.list('items', AllocationShare.fromJson);
  }

  @override
  Future<PerformanceMetrics> metrics(String portfolioId) async {
    final doc = await _doc('metrics.json');
    final all = doc.mapOf('metrics', (r) => r);
    return PerformanceMetrics.fromJson(
      _byId(all, portfolioId, 'portfolio'),
      doc.timestamp('as_of'),
    );
  }

  @override
  Future<List<HoldingSummary>> holdings(String portfolioId) async {
    final all = (await _doc('holdings.json')).mapOf('holdings', (r) => r);
    return _byId(
      all,
      portfolioId,
      'portfolio',
    ).list('items', HoldingSummary.fromJson);
  }
}

final portfolioRepositoryProvider = Provider<PortfolioRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoPortfolioRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
  }
});

import 'package:decimal/decimal.dart';

import '../../../core/data/json_reader.dart';
import '../../../core/network/asset_class_names.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/design_system/components/period_selector.dart';
import '../../../shared/domain/wealth_models.dart';
import 'portfolio_repository.dart';

/// Reads portfolios, summaries, performance, allocation and holdings from the API.
///
/// Every figure is the server's: nothing is added, converted or derived here. Where the API has
/// no answer the field is null (or the list empty) and the screen says so. All portfolios
/// combined (`consolidated`) has a server summary only: no profit and loss, series, allocation
/// or metrics exist for it yet, so those come back empty rather than being added up in the app.
class LivePortfolioRepository extends LiveRepository
    implements PortfolioRepository {
  LivePortfolioRepository(
    super.dio,
    this._classes, {
    DateTime Function()? clock,
    this.consolidatedName = 'All portfolios',
  }) : _now = clock ?? DateTime.now;

  final AssetClassNames _classes;
  final DateTime Function() _now;

  /// The name shown for the combined view.
  final String consolidatedName;

  static bool _isAll(String id) => id == PortfolioRef.consolidatedId;

  @override
  Future<List<PortfolioRef>> portfolios() =>
      getList('/api/v1/portfolios', PortfolioRef.fromJson);

  @override
  Future<PortfolioSummary> summary(String portfolioId) async {
    if (_isAll(portfolioId)) {
      final s = await getObject(
        '/api/v1/portfolios/consolidated/summary',
        (r) => r,
      );
      return _summary(portfolioId, consolidatedName, s, null);
    }
    final results = await Future.wait([
      getObject('/api/v1/portfolios/$portfolioId/summary', (r) => r),
      getObject('/api/v1/portfolios/$portfolioId/performance', (r) => r),
      getObject('/api/v1/portfolios/$portfolioId', (r) => r.string('name')),
    ]);
    return _summary(
      portfolioId,
      results[2] as String,
      results[0] as JsonReader,
      results[1] as JsonReader,
    );
  }

  PortfolioSummary _summary(
    String id,
    String name,
    JsonReader s,
    JsonReader? performance,
  ) {
    final freshness = s.object('freshness');
    return PortfolioSummary(
      portfolioId: id,
      name: name,
      baseCurrency: s.string('currency'),
      value: s.money('total_value'),
      invested: s.money('net_contributions'),
      profitLoss: performance != null && performance.has('profit_loss')
          ? performance.money('profit_loss')
          : null,
      returnPercent: performance != null && performance.has('return_percent')
          ? performance.decimal('return_percent')
          : null,
      asOf: freshness.timestamp('data_as_of'),
      complete: freshness.boolean('complete'),
      unpricedAssetCount: s.list('unpriced_assets', (r) => r).length,
      stalePriceCount: freshness.list('stale_prices', (r) => r).length,
    );
  }

  @override
  Future<PerformanceSeries> performance(
    String portfolioId,
    ChartPeriod period,
  ) async {
    if (_isAll(portfolioId)) {
      return PerformanceSeries(
        period: period,
        currencyCode: '',
        points: const [],
        asOf: _now(),
      );
    }
    final today = _now();
    final (frequency, start) = _window(period, today);
    return getObject(
      '/api/v1/portfolios/$portfolioId/risk',
      (r) => PerformanceSeries(
        period: period,
        currencyCode: r.string('currency'),
        // Points whose value could not be completed are left out, not filled in.
        points: [
          for (final p in r.list('points', (p) => p))
            if (p.boolean('complete'))
              PerformancePoint(p.date('on'), p.money('value').amount),
        ],
        asOf: r.timestamp('as_of'),
      ),
      query: {
        'frequency': frequency,
        'start': ?(start == null ? null : _day(start)),
      },
    );
  }

  /// Spacing and first day of the series for a chart period.
  (String frequency, DateTime? start) _window(
    ChartPeriod period,
    DateTime now,
  ) {
    DateTime back(int days) => now.subtract(Duration(days: days));
    return switch (period) {
      ChartPeriod.week => ('daily', back(7)),
      ChartPeriod.month => ('daily', back(30)),
      ChartPeriod.threeMonths => ('weekly', back(91)),
      ChartPeriod.sixMonths => ('weekly', back(182)),
      ChartPeriod.yearToDate => ('weekly', DateTime(now.year)),
      ChartPeriod.year => ('weekly', back(365)),
      ChartPeriod.all => ('monthly', null),
    };
  }

  static String _day(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  @override
  Future<List<AllocationShare>> allocation(String portfolioId) async {
    if (_isAll(portfolioId)) return const [];
    final names = await _classes.names();
    return getObject('/api/v1/portfolios/$portfolioId/allocation', (r) {
      return [
        for (final slice in r.object('asset_class').list('slices', (s) => s))
          // A slice with no weight (a zero total) has nothing to draw.
          if (slice.has('weight_percent'))
            AllocationShare(
              label: slice.has('key')
                  ? (names[slice.string('key')] ?? slice.string('key'))
                  : 'Unclassified',
              value: slice.money('value'),
              weightPercent: slice.decimal('weight_percent'),
            ),
      ];
    });
  }

  @override
  Future<PerformanceMetrics> metrics(String portfolioId) async {
    if (_isAll(portfolioId)) {
      return PerformanceMetrics(
        totalReturnPercent: null,
        cagrPercent: null,
        dividendYieldPercent: null,
        volatilityPercent: null,
        asOf: _now(),
      );
    }
    final base = '/api/v1/portfolios/$portfolioId';
    final results = await Future.wait([
      getObject('$base/performance', (r) => r),
      getObject('$base/risk', (r) => r),
      getObject('$base/income', (r) => r),
    ]);
    final performance = results[0];
    final risk = results[1];
    final income = results[2];
    Decimal? optional(JsonReader r, String key) =>
        r.has(key) ? r.decimal(key) : null;
    return PerformanceMetrics(
      totalReturnPercent: optional(performance, 'return_percent'),
      cagrPercent: optional(risk, 'time_weighted_annualized_percent'),
      dividendYieldPercent: optional(income, 'portfolio_yield_percent'),
      volatilityPercent: optional(risk, 'volatility_percent'),
      asOf: performance.timestamp('as_of'),
    );
  }

  @override
  Future<List<HoldingSummary>> holdings(String portfolioId) async {
    final ids = _isAll(portfolioId)
        ? [for (final p in await portfolios()) p.id]
        : [portfolioId];
    final names = await _classes.names();
    final lists = await Future.wait([
      for (final id in ids)
        getList('/api/v1/portfolios/$id/holdings', (h) => _holding(h, names)),
    ]);
    return [for (final l in lists) ...l];
  }

  HoldingSummary _holding(JsonReader h, Map<String, String> names) {
    final asset = h.object('asset');
    final classCode = asset.string('asset_class');
    return HoldingSummary(
      symbol: asset.stringOrNull('symbol'),
      name: asset.string('name'),
      assetClass: names[classCode] ?? classCode,
      value: h.has('value') ? h.money('value') : null,
      nativeValue: h.has('native_value') ? h.money('native_value') : null,
      changePercent: null,
      asOf: h.has('value_as_of') ? h.timestamp('value_as_of') : null,
      assetId: asset.string('id'),
      valueSource: h.stringOrNull('value_source'),
      valueStale: h.has('value_stale') && h.boolean('value_stale'),
    );
  }
}

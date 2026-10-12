import '../../../core/network/asset_catalog.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/design_system/components/evidence_source_chip.dart';
import '../../../shared/design_system/components/period_selector.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../../shared/domain/wealth_models.dart';
import '../domain/investment_models.dart';
import 'investment_repository.dart';

/// One investment from the API, opened by asset id. It shows the asset and the user's position
/// in each portfolio that holds it, as the server reports them.
///
/// The price and its history are the stored, delayed market prices (`/assets/{id}/prices`), with
/// their provider, time and freshness. What the API does not supply stays empty rather than
/// being filled in: fundamentals, research, per-asset income, the daily change, and the
/// unrealised gain or loss of a position. Nothing is derived in the app (for example value minus
/// cost).
class LiveInvestmentRepository extends LiveRepository
    implements InvestmentRepository {
  LiveInvestmentRepository(
    super.dio,
    this._assets,
    this._portfolios, {
    DateTime Function()? clock,
  }) : _now = clock ?? DateTime.now;

  final AssetCatalog _assets;

  /// The user's portfolios (to find every position in the asset).
  final Future<List<PortfolioRef>> Function() _portfolios;
  final DateTime Function() _now;

  @override
  Future<InvestmentDetail> detail(String assetId) async {
    final results = await Future.wait([
      _assets.asset(assetId),
      _positions(assetId),
      _prices(assetId, null),
    ]);
    final asset = results[0] as AssetInfo;
    final positions = results[1] as List<PositionInfo>;
    final latest = (results[2] as _Prices).latest;
    return InvestmentDetail(
      symbol: asset.symbol,
      name: asset.name,
      assetClass: asset.assetClassName,
      currency: asset.currency,
      price: latest?.price,
      changePercent: null,
      priceSource: latest == null
          ? null
          : EvidenceSource(
              label: priceSourceLabel,
              provider: latest.provider,
              asOf: latest.asOf,
            ),
      priceStale: latest?.stale ?? false,
      fundamentals: null,
      income: null,
      positions: positions,
      research: const [],
    );
  }

  Future<List<PositionInfo>> _positions(String assetId) async {
    final portfolios = await _portfolios();
    final perPortfolio = await Future.wait([
      for (final p in portfolios)
        getList('/api/v1/portfolios/${p.id}/holdings', (h) => h).then(
          (rows) => [
            for (final h in rows)
              if (h.object('asset').string('id') == assetId)
                PositionInfo(
                  quantity: h.decimal('quantity'),
                  averageCost: h.has('average_cost')
                      ? h.money('average_cost')
                      : null,
                  costBasis: h.money('cost_basis'),
                  value: h.has('value') ? h.money('value') : null,
                  nativeValue: h.has('native_value')
                      ? h.money('native_value')
                      : null,
                  unrealisedPl: null,
                  unrealisedPlPercent: null,
                  asOf: h.has('value_as_of')
                      ? h.timestamp('value_as_of')
                      : null,
                  portfolioName: portfolios.length > 1 ? p.name : null,
                ),
          ],
        ),
    ]);
    return [for (final list in perPortfolio) ...list];
  }

  /// Daily closes the server has stored for the period. Days without a stored close are missing
  /// from the chart, never filled in.
  @override
  Future<PerformanceSeries> priceHistory(
    String assetId,
    ChartPeriod period,
  ) async {
    final now = _now();
    final prices = await _prices(assetId, _start(period, now));
    return PerformanceSeries(
      period: period,
      currencyCode: prices.currency,
      points: prices.points,
      asOf: prices.latest?.asOf ?? now,
    );
  }

  static DateTime? _start(ChartPeriod period, DateTime now) {
    DateTime back(int days) => now.subtract(Duration(days: days));
    return switch (period) {
      ChartPeriod.week => back(7),
      ChartPeriod.month => back(30),
      ChartPeriod.threeMonths => back(91),
      ChartPeriod.sixMonths => back(182),
      ChartPeriod.yearToDate => DateTime(now.year),
      ChartPeriod.year => back(365),
      ChartPeriod.all => DateTime(1970),
    };
  }

  Future<_Prices> _prices(String assetId, DateTime? start) =>
      getObject('/api/v1/assets/$assetId/prices', (r) {
        final currency = r.string('currency');
        final latest = r.has('latest') ? r.object('latest') : null;
        return _Prices(
          currency: currency,
          latest: latest == null
              ? null
              : (
                  price: Money(
                    latest.decimal('price'),
                    latest.string('currency'),
                  ),
                  provider: latest.string('provider'),
                  asOf: latest.timestamp('as_of'),
                  stale: latest.boolean('stale'),
                ),
          points: r.list(
            'points',
            (p) => PerformancePoint(p.date('on'), p.decimal('close')),
          ),
        );
      }, query: {'start': ?(start == null ? null : _day(start))});

  static String _day(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}

/// The label of a stored market price shown with its provider (not live or executable).
const String priceSourceLabel = 'Delayed market price';

class _Prices {
  const _Prices({
    required this.currency,
    required this.latest,
    required this.points,
  });

  final String currency;
  final ({Money price, String provider, DateTime asOf, bool stale})? latest;
  final List<PerformancePoint> points;
}

import '../../../core/network/asset_catalog.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/design_system/components/period_selector.dart';
import '../../../shared/domain/wealth_models.dart';
import '../domain/investment_models.dart';
import 'investment_repository.dart';

/// One investment from the API, opened by asset id. It shows the asset and the user's position
/// in each portfolio that holds it, as the server reports them.
///
/// What the API does not supply stays empty rather than being filled in: a market price and its
/// history (P09-T07), fundamentals, research and per-asset income, and the unrealised gain or
/// loss of a position. Nothing is derived in the app (for example value minus cost).
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
    ]);
    final asset = results[0] as AssetInfo;
    final positions = results[1] as List<PositionInfo>;
    return InvestmentDetail(
      symbol: asset.symbol,
      name: asset.name,
      assetClass: asset.assetClassName,
      currency: asset.currency,
      price: null,
      changePercent: null,
      priceSource: null,
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

  /// Price history arrives with the market-data screens (P09-T07); until then the chart is
  /// empty, never drawn from invented points.
  @override
  Future<PerformanceSeries> priceHistory(
    String assetId,
    ChartPeriod period,
  ) async {
    final asset = await _assets.asset(assetId);
    return PerformanceSeries(
      period: period,
      currencyCode: asset.currency,
      points: const [],
      asOf: _now(),
    );
  }
}

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../../../shared/design_system/components/period_selector.dart';
import '../../../shared/domain/wealth_models.dart';
import '../domain/investment_models.dart';

/// Read-only data about one investment (an asset). There is no call that places an order: this
/// app does not execute trades.
abstract interface class InvestmentRepository {
  Future<InvestmentDetail> detail(String symbol);
  Future<PerformanceSeries> priceHistory(String symbol, ChartPeriod period);
}

/// Reads `assets/demo/investments.json`.
class DemoInvestmentRepository implements InvestmentRepository {
  DemoInvestmentRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;

  Future<(JsonReader, JsonReader)> _entry(String symbol) async {
    await _gate();
    final doc = JsonReader(await _assets.load('investments.json'));
    final all = doc.mapOf('investments', (r) => r);
    final entry = all[symbol];
    if (entry == null) throw DataLoadException('Unknown investment "$symbol"');
    return (doc, entry);
  }

  @override
  Future<InvestmentDetail> detail(String symbol) async {
    final (_, entry) = await _entry(symbol);
    return InvestmentDetail.fromJson(entry);
  }

  @override
  Future<PerformanceSeries> priceHistory(
    String symbol,
    ChartPeriod period,
  ) async {
    final (_, entry) = await _entry(symbol);
    final price = entry.object('price');
    final points = entry
        .object('performance')
        .list(
          period.name,
          (p) => PerformancePoint(p.date('date'), p.decimal('value')),
        );
    return PerformanceSeries(
      period: period,
      currencyCode: price.money('value').currencyCode,
      points: points,
      asOf: price.timestamp('as_of'),
    );
  }
}

final investmentRepositoryProvider = Provider<InvestmentRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoInvestmentRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
    case DataSourceMode.live:
      liveNotWired('InvestmentRepository');
  }
});

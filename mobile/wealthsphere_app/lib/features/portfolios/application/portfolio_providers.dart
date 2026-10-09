import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/design_system/components/period_selector.dart';
import '../../../shared/domain/wealth_models.dart';
import '../data/portfolio_repository.dart';

/// The portfolio the user is looking at: a portfolio id, or [PortfolioRef.consolidatedId] for all
/// of them. Shared by the Portfolio tab and the AI scope.
class SelectedPortfolioNotifier extends Notifier<String> {
  @override
  String build() => PortfolioRef.consolidatedId;

  void select(String id) => state = id;
}

final selectedPortfolioIdProvider =
    NotifierProvider<SelectedPortfolioNotifier, String>(
      SelectedPortfolioNotifier.new,
    );

/// The periods the portfolio chart offers.
const List<ChartPeriod> portfolioPeriods = [
  ChartPeriod.month,
  ChartPeriod.threeMonths,
  ChartPeriod.sixMonths,
  ChartPeriod.year,
  ChartPeriod.all,
];

class PortfolioPeriodNotifier extends Notifier<ChartPeriod> {
  @override
  ChartPeriod build() => ChartPeriod.year;

  void select(ChartPeriod period) => state = period;
}

final portfolioPeriodProvider =
    NotifierProvider<PortfolioPeriodNotifier, ChartPeriod>(
      PortfolioPeriodNotifier.new,
    );

final portfolioListProvider = FutureProvider<List<PortfolioRef>>(
  (ref) => ref.watch(portfolioRepositoryProvider).portfolios(),
);

final portfolioSummaryProvider =
    FutureProvider.family<PortfolioSummary, String>(
      (ref, id) => ref.watch(portfolioRepositoryProvider).summary(id),
    );

final portfolioSeriesProvider =
    FutureProvider.family<PerformanceSeries, ({String id, ChartPeriod period})>(
      (ref, key) => ref
          .watch(portfolioRepositoryProvider)
          .performance(key.id, key.period),
    );

final portfolioAllocationProvider =
    FutureProvider.family<List<AllocationShare>, String>(
      (ref, id) => ref.watch(portfolioRepositoryProvider).allocation(id),
    );

final portfolioMetricsProvider =
    FutureProvider.family<PerformanceMetrics, String>(
      (ref, id) => ref.watch(portfolioRepositoryProvider).metrics(id),
    );

final portfolioHoldingsProvider =
    FutureProvider.family<List<HoldingSummary>, String>(
      (ref, id) => ref.watch(portfolioRepositoryProvider).holdings(id),
    );

/// Re-requests everything for the selected portfolio (pull to refresh).
void refreshPortfolio(WidgetRef ref) {
  ref
    ..invalidate(portfolioListProvider)
    ..invalidate(portfolioSummaryProvider)
    ..invalidate(portfolioSeriesProvider)
    ..invalidate(portfolioAllocationProvider)
    ..invalidate(portfolioMetricsProvider)
    ..invalidate(portfolioHoldingsProvider);
}

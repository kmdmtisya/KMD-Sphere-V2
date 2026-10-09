import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/design_system/components/period_selector.dart';
import '../../../shared/domain/wealth_models.dart';
import '../../portfolios/data/portfolio_repository.dart';
import '../data/dashboard_repository.dart';
import '../domain/dashboard_layout.dart';

/// Each dashboard section has its own provider, so one failing section does not blank the page
/// and each can be retried on its own.
final greetingNameProvider = FutureProvider<String>(
  (ref) => ref.watch(dashboardRepositoryProvider).greetingName(),
);

final dashboardNetWorthProvider = FutureProvider<NetWorthSummary>(
  (ref) => ref.watch(dashboardRepositoryProvider).netWorth(),
);

final dashboardIncomeProvider = FutureProvider<IncomeSummary>(
  (ref) => ref.watch(dashboardRepositoryProvider).income(),
);

final dashboardGoalsProvider = FutureProvider<GoalsSummary>(
  (ref) => ref.watch(dashboardRepositoryProvider).goals(),
);

final dashboardInsightProvider = FutureProvider<InsightSummary>(
  (ref) => ref.watch(dashboardRepositoryProvider).insight(),
);

/// Totals across every portfolio.
final homeSummaryProvider = FutureProvider<PortfolioSummary>(
  (ref) => ref
      .watch(portfolioRepositoryProvider)
      .summary(PortfolioRef.consolidatedId),
);

/// The periods the home chart offers.
const List<ChartPeriod> homePeriods = [
  ChartPeriod.week,
  ChartPeriod.month,
  ChartPeriod.year,
  ChartPeriod.all,
];

class HomePeriodNotifier extends Notifier<ChartPeriod> {
  @override
  ChartPeriod build() => ChartPeriod.month;

  void select(ChartPeriod period) => state = period;
}

final homePeriodProvider = NotifierProvider<HomePeriodNotifier, ChartPeriod>(
  HomePeriodNotifier.new,
);

final homeSeriesProvider =
    FutureProvider.family<PerformanceSeries, ChartPeriod>(
      (ref, period) => ref
          .watch(portfolioRepositoryProvider)
          .performance(PortfolioRef.consolidatedId, period),
    );

/// The personalised layout. Changes are saved as they are made.
class DashboardLayoutNotifier extends AsyncNotifier<DashboardLayout> {
  @override
  Future<DashboardLayout> build() =>
      ref.watch(dashboardLayoutRepositoryProvider).load();

  Future<void> _apply(DashboardLayout Function(DashboardLayout) change) async {
    final current = state.value ?? DashboardLayout.initial();
    final next = change(current);
    if (next == current) return;
    state = AsyncData(next);
    await ref.read(dashboardLayoutRepositoryProvider).save(next);
  }

  Future<void> move(DashboardSection section, int delta) =>
      _apply((l) => l.move(section, delta));

  Future<void> setVisible(DashboardSection section, {required bool visible}) =>
      _apply((l) => l.withVisibility(section, visible: visible));
}

final dashboardLayoutProvider =
    AsyncNotifierProvider<DashboardLayoutNotifier, DashboardLayout>(
      DashboardLayoutNotifier.new,
    );

/// Re-requests every section (pull to refresh).
void refreshDashboard(WidgetRef ref) {
  ref
    ..invalidate(greetingNameProvider)
    ..invalidate(dashboardNetWorthProvider)
    ..invalidate(dashboardIncomeProvider)
    ..invalidate(dashboardGoalsProvider)
    ..invalidate(dashboardInsightProvider)
    ..invalidate(homeSummaryProvider)
    ..invalidate(homeSeriesProvider);
}

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/design_system/components/period_selector.dart';
import '../../../shared/domain/wealth_models.dart';
import '../../transactions/application/ledger_view.dart';
import '../../transactions/domain/ledger_entry.dart';
import '../data/investment_repository.dart';
import '../domain/investment_models.dart';

/// The periods the price chart offers.
const List<ChartPeriod> investmentPeriods = [
  ChartPeriod.month,
  ChartPeriod.threeMonths,
  ChartPeriod.sixMonths,
  ChartPeriod.year,
  ChartPeriod.all,
];

class InvestmentPeriodNotifier extends Notifier<ChartPeriod> {
  @override
  ChartPeriod build() => ChartPeriod.year;

  void select(ChartPeriod period) => state = period;
}

final investmentPeriodProvider =
    NotifierProvider<InvestmentPeriodNotifier, ChartPeriod>(
      InvestmentPeriodNotifier.new,
    );

final investmentDetailProvider =
    FutureProvider.family<InvestmentDetail, String>(
      (ref, symbol) => ref.watch(investmentRepositoryProvider).detail(symbol),
    );

final investmentHistoryProvider =
    FutureProvider.family<
      PerformanceSeries,
      ({String symbol, ChartPeriod period})
    >(
      (ref, key) => ref
          .watch(investmentRepositoryProvider)
          .priceHistory(key.symbol, key.period),
    );

/// The ledger entries that involve [symbol], across all portfolios, newest first.
final investmentLedgerProvider =
    FutureProvider.family<List<LedgerEntry>, String>((ref, symbol) async {
      final all = await ref.watch(
        ledgerProvider(PortfolioRef.consolidatedId).future,
      );
      final mine = [
        for (final e in all)
          if (e.assetSymbol == symbol) e,
      ];
      return [for (final month in groupByMonth(mine)) ...month.entries];
    });

/// The investments the user is watching (in memory for this session in the demo).
class WatchlistNotifier extends Notifier<Set<String>> {
  @override
  Set<String> build() => const {};

  bool isWatching(String symbol) => state.contains(symbol);

  void toggle(String symbol) {
    state = state.contains(symbol)
        ? ({...state}..remove(symbol))
        : {...state, symbol};
  }
}

final watchlistProvider = NotifierProvider<WatchlistNotifier, Set<String>>(
  WatchlistNotifier.new,
);

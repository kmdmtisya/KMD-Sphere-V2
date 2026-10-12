import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/design_system/components/transaction_tile.dart';
import '../../dashboard/application/dashboard_providers.dart';
import '../../portfolios/application/portfolio_providers.dart';
import '../data/transaction_repository.dart';
import '../domain/ledger_entry.dart';

/// The filter chips of the ledger: groups of entry types.
enum TxFilter {
  all,
  trades,
  cash,
  income,
  costs,
  other;

  bool matches(TransactionKind kind) => switch (this) {
    all => true,
    trades => kind == TransactionKind.buy || kind == TransactionKind.sell,
    cash =>
      kind == TransactionKind.deposit || kind == TransactionKind.withdrawal,
    income =>
      kind == TransactionKind.dividend ||
          kind == TransactionKind.interest ||
          kind == TransactionKind.coupon ||
          kind == TransactionKind.rent ||
          kind == TransactionKind.distribution,
    costs => kind == TransactionKind.fee || kind == TransactionKind.tax,
    other =>
      kind == TransactionKind.transferIn ||
          kind == TransactionKind.transferOut ||
          kind == TransactionKind.valuationAdjustment,
  };
}

class TxFilterNotifier extends Notifier<TxFilter> {
  @override
  TxFilter build() => TxFilter.all;

  void select(TxFilter filter) => state = filter;
}

final txFilterProvider = NotifierProvider<TxFilterNotifier, TxFilter>(
  TxFilterNotifier.new,
);

/// The filters that have at least one entry (so a chip never leads to an empty list), in order.
List<TxFilter> filtersPresent(List<LedgerEntry> entries) => [
  for (final f in TxFilter.values)
    if (f == TxFilter.all || entries.any((e) => f.matches(e.kind))) f,
];

List<LedgerEntry> filterEntries(List<LedgerEntry> entries, TxFilter filter) => [
  for (final e in entries)
    if (filter.matches(e.kind)) e,
];

/// The entries of one calendar month, newest first.
class LedgerMonth {
  const LedgerMonth(this.month, this.entries);

  /// The first day of the month.
  final DateTime month;
  final List<LedgerEntry> entries;
}

/// Groups entries by the month of their trade date, newest month first and newest entry first
/// within a month. Ties break on creation time and id so the order never jumps.
List<LedgerMonth> groupByMonth(List<LedgerEntry> entries) {
  final sorted = [...entries]
    ..sort((a, b) {
      final byDate = b.tradeDate.compareTo(a.tradeDate);
      if (byDate != 0) return byDate;
      final byCreated = b.createdAt.compareTo(a.createdAt);
      return byCreated != 0 ? byCreated : a.id.compareTo(b.id);
    });
  final groups = <LedgerMonth>[];
  for (final e in sorted) {
    final month = DateTime(e.tradeDate.year, e.tradeDate.month);
    if (groups.isEmpty || groups.last.month != month) {
      groups.add(LedgerMonth(month, []));
    }
    groups.last.entries.add(e);
  }
  return groups;
}

/// The current moment; tests override it. Used for the "not in the future" date rule.
final todayProvider = Provider<DateTime>((ref) => DateTime.now());

final ledgerProvider = FutureProvider.family<List<LedgerEntry>, String>(
  (ref, portfolioId) =>
      ref.watch(transactionRepositoryProvider).entries(portfolioId),
);

final ledgerEntryProvider = FutureProvider.family<LedgerEntry, String>(
  (ref, id) => ref.watch(transactionRepositoryProvider).entry(id),
);

/// Refreshes every ledger view after an entry was added or reversed.
/// The figures that depend on the ledger are re-read from the server too (it recomputes them;
/// the app never adjusts a total itself).
void refreshLedger(WidgetRef ref) {
  ref
    ..invalidate(ledgerProvider)
    ..invalidate(ledgerEntryProvider)
    ..invalidate(portfolioSummaryProvider)
    ..invalidate(portfolioHoldingsProvider)
    ..invalidate(portfolioSeriesProvider)
    ..invalidate(portfolioAllocationProvider)
    ..invalidate(portfolioMetricsProvider)
    ..invalidate(homeSummaryProvider)
    ..invalidate(homeSeriesProvider)
    ..invalidate(dashboardNetWorthProvider)
    ..invalidate(dashboardIncomeProvider);
}

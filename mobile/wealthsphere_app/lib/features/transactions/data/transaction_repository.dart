import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/asset_catalog.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../../shared/domain/wealth_models.dart';
import '../../portfolios/data/portfolio_repository.dart';
import '../application/transaction_draft.dart';
import '../domain/ledger_entry.dart';
import 'live_transaction_repository.dart';

/// Why a correction was refused.
enum LedgerRule { notFound, alreadyReversed, isReversal }

class LedgerRuleException implements Exception {
  const LedgerRuleException(this.rule);

  final LedgerRule rule;

  @override
  String toString() => 'LedgerRuleException: $rule';
}

/// The portfolio ledger. It is append-only: [add] and [reverse] each create a new entry, and no
/// call edits or deletes one. A [portfolioId] of [PortfolioRef.consolidatedId] means all portfolios.
abstract interface class TransactionRepository {
  Future<List<LedgerEntry>> entries(String portfolioId);
  Future<LedgerEntry> entry(String id);
  Future<LedgerEntry> add(NewTransaction transaction);

  /// Cancels a live entry by appending a linked reversal. Returns the reversal.
  Future<LedgerEntry> reverse(String id, {String? note});
}

/// Reads `assets/demo/transactions.json`. New entries and reversals live in memory for the
/// session only (nothing is saved anywhere), so the add and correct flows can be tried end to end.
class DemoTransactionRepository implements TransactionRepository {
  DemoTransactionRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;
  final List<LedgerEntry> _added = [];
  final Map<String, String> _reversedBy = {};
  int _counter = 0;

  Future<List<LedgerEntry>> _all() async {
    await _gate();
    final doc = JsonReader(await _assets.load('transactions.json'));
    final base = doc
        .mapOf('transactions', (r) => r)[PortfolioRef.consolidatedId]
        ?.list('items', LedgerEntry.fromJson);
    if (base == null) {
      throw const DataLoadException(
        'transactions.json has no consolidated list',
      );
    }
    return [
      for (final e in [...base, ..._added])
        _reversedBy.containsKey(e.id)
            ? e.withReversedBy(_reversedBy[e.id]!)
            : e,
    ];
  }

  @override
  Future<List<LedgerEntry>> entries(String portfolioId) async {
    final all = await _all();
    return portfolioId == PortfolioRef.consolidatedId
        ? all
        : [
            for (final e in all)
              if (e.portfolioId == portfolioId) e,
          ];
  }

  @override
  Future<LedgerEntry> entry(String id) async {
    final found = (await _all()).where((e) => e.id == id).firstOrNull;
    if (found == null) throw const LedgerRuleException(LedgerRule.notFound);
    return found;
  }

  @override
  Future<LedgerEntry> add(NewTransaction t) async {
    await _gate();
    _counter++;
    // DEMO stand-in for the server: the real backend derives a trade's total from quantity and
    // unit price. The app never does this arithmetic for real data.
    final gross = t.amount ?? (t.quantity! * t.unitPrice!).round(scale: 2);
    final entry = LedgerEntry(
      id: 'demo-new-$_counter',
      portfolioId: t.portfolioId,
      kind: t.kind,
      tradeDate: t.date,
      gross: Money(gross, t.currency),
      source: 'manual',
      createdAt: DateTime.now().toUtc(),
      assetSymbol: t.assetSymbol,
      assetName: t.assetName,
      quantity: t.quantity,
      unitPrice: t.unitPrice == null ? null : Money(t.unitPrice!, t.currency),
      fees: t.fee == null ? null : Money(t.fee!, t.currency),
      note: t.note,
    );
    _added.add(entry);
    return entry;
  }

  @override
  Future<LedgerEntry> reverse(String id, {String? note}) async {
    final original = await entry(id);
    if (original.isReversal) {
      throw const LedgerRuleException(LedgerRule.isReversal);
    }
    if (original.isReversed) {
      throw const LedgerRuleException(LedgerRule.alreadyReversed);
    }
    _counter++;
    final reversal = LedgerEntry(
      id: 'demo-new-$_counter',
      portfolioId: original.portfolioId,
      kind: original.kind,
      tradeDate: DateTime.now(),
      gross: original.gross,
      source: 'manual',
      createdAt: DateTime.now().toUtc(),
      assetSymbol: original.assetSymbol,
      assetName: original.assetName,
      quantity: original.quantity,
      unitPrice: original.unitPrice,
      fees: original.fees,
      note: note,
      reversesId: original.id,
    );
    _added.add(reversal);
    _reversedBy[original.id] = reversal.id;
    return reversal;
  }
}

final transactionRepositoryProvider = Provider<TransactionRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoTransactionRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
    case DataSourceMode.live:
      final portfolios = ref.watch(portfolioRepositoryProvider);
      return LiveTransactionRepository(
        ref.watch(apiClientProvider),
        ref.watch(assetCatalogProvider),
        () async => [for (final p in await portfolios.portfolios()) p.id],
      );
  }
});

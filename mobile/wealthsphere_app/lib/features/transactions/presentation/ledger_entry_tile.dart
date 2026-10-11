import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../domain/ledger_entry.dart';

/// A [TransactionTile] for a ledger entry. A reversal reads "`Reversal of ...`" and moves cash
/// the opposite way to the entry it cancels; a reversed entry is struck through.
class LedgerEntryTile extends StatelessWidget {
  const LedgerEntryTile({required this.entry, this.onTap, super.key});

  final LedgerEntry entry;
  final VoidCallback? onTap;

  static CashDirection _opposite(CashDirection d) => switch (d) {
    CashDirection.inflow => CashDirection.outflow,
    CashDirection.outflow => CashDirection.inflow,
    CashDirection.none => CashDirection.none,
  };

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final base = TransactionTile.defaultDirection(entry.kind);
    final fee = entry.fees;
    return TransactionTile(
      kind: entry.kind,
      date: entry.tradeDate,
      amount: entry.gross,
      direction: entry.isReversal ? _opposite(base) : base,
      assetName: entry.isReversal
          ? (entry.assetName == null
                ? l10n.ledgerReversalPlain
                : l10n.ledgerReversalOf(entry.assetName!))
          : entry.assetName,
      quantity: entry.quantity?.toString(),
      unitPrice: entry.unitPrice == null
          ? null
          : context.moneyFormatter.format(entry.unitPrice!),
      fee: fee == null || fee.amount.sign == 0 ? null : fee,
      reversed: entry.isReversed,
      onTap: onTap,
    );
  }
}

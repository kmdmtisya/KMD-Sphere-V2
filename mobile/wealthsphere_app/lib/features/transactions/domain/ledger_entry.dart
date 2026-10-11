import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';
import '../../../shared/design_system/components/transaction_tile.dart';
import '../../../shared/design_system/formatting/money.dart';

/// One entry of the portfolio ledger as the API returns it (`TransactionOut`).
///
/// The ledger is append-only: an entry is never edited. A correction is a **reversal**, a new
/// entry whose [reversesId] points at the entry it cancels; the cancelled entry in turn carries
/// [reversedById]. Amounts are ready-made by the backend; nothing here is calculated.
@immutable
class LedgerEntry {
  const LedgerEntry({
    required this.id,
    required this.portfolioId,
    required this.kind,
    required this.tradeDate,
    required this.gross,
    required this.source,
    required this.createdAt,
    this.assetSymbol,
    this.assetName,
    this.quantity,
    this.unitPrice,
    this.fees,
    this.note,
    this.reversesId,
    this.reversedById,
  });

  factory LedgerEntry.fromJson(JsonReader r) {
    final day = r.date('trade_date');
    return LedgerEntry(
      id: r.string('id'),
      portfolioId: r.string('portfolio_id'),
      kind: TransactionKind.parse(r.string('transaction_type')),
      // A calendar day, kept as a local date so it never shifts across a time zone.
      tradeDate: DateTime(day.year, day.month, day.day),
      gross: r.money('gross_amount'),
      source: r.string('source'),
      createdAt: r.timestamp('created_at'),
      assetSymbol: r.stringOrNull('asset_symbol'),
      assetName: r.stringOrNull('asset_name'),
      quantity: r.has('quantity') ? r.decimal('quantity') : null,
      unitPrice: r.has('unit_price') ? r.money('unit_price') : null,
      fees: r.has('fees') ? r.money('fees') : null,
      note: r.stringOrNull('note'),
      reversesId: r.stringOrNull('reverses_transaction_id'),
      reversedById: r.stringOrNull('reversed_by_transaction_id'),
    );
  }

  final String id;
  final String portfolioId;
  final TransactionKind kind;
  final DateTime tradeDate;

  /// The posted amount in the posting currency.
  final Money gross;

  /// `manual`, `import` or `system`.
  final String source;
  final DateTime createdAt;
  final String? assetSymbol;
  final String? assetName;
  final Decimal? quantity;
  final Money? unitPrice;
  final Money? fees;
  final String? note;

  /// Set on a reversal: the entry it cancels.
  final String? reversesId;

  /// Set when a reversal has cancelled this entry.
  final String? reversedById;

  bool get isReversal => reversesId != null;
  bool get isReversed => reversedById != null;

  /// Only a live original can be corrected: a reversal is final and a reversed entry is done.
  bool get canCorrect => !isReversal && !isReversed;

  LedgerEntry withReversedBy(String reversalId) => LedgerEntry(
    id: id,
    portfolioId: portfolioId,
    kind: kind,
    tradeDate: tradeDate,
    gross: gross,
    source: source,
    createdAt: createdAt,
    assetSymbol: assetSymbol,
    assetName: assetName,
    quantity: quantity,
    unitPrice: unitPrice,
    fees: fees,
    note: note,
    reversesId: reversesId,
    reversedById: reversalId,
  );
}

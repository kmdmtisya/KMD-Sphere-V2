import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../shared/design_system/components/transaction_tile.dart';
import '../../../shared/design_system/formatting/currency_info.dart';

/// The entry types a person can add by hand. The others (transfers, interest, coupons, ...) come
/// from imports or the system.
const List<TransactionKind> addableKinds = [
  TransactionKind.buy,
  TransactionKind.sell,
  TransactionKind.deposit,
  TransactionKind.withdrawal,
  TransactionKind.dividend,
  TransactionKind.fee,
];

enum TxField { kind, portfolio, asset, date, quantity, unitPrice, amount, fee }

enum TxFieldError {
  required,
  notANumber,
  notPositive,
  negative,
  tooManyDecimals,
  tooLarge,
  futureDate,
  tooOld,
}

/// What is wrong with one field. [places] is the allowed number of decimal places, for
/// [TxFieldError.tooManyDecimals].
@immutable
class TxIssue {
  const TxIssue(this.error, {this.places});

  final TxFieldError error;
  final int? places;

  @override
  bool operator ==(Object other) =>
      other is TxIssue && other.error == error && other.places == places;

  @override
  int get hashCode => Object.hash(error, places);

  @override
  String toString() => 'TxIssue($error${places == null ? '' : ', $places'})';
}

/// What the form holds: the raw text the person typed, before any checking.
@immutable
class TransactionDraft {
  const TransactionDraft({
    required this.kind,
    this.portfolioId,
    this.assetSymbol,
    this.assetName,
    this.date,
    this.quantity = '',
    this.unitPrice = '',
    this.amount = '',
    this.fee = '',
    this.note = '',
  });

  final TransactionKind kind;
  final String? portfolioId;
  final String? assetSymbol;
  final String? assetName;
  final DateTime? date;
  final String quantity;
  final String unitPrice;
  final String amount;
  final String fee;
  final String note;
}

/// A draft that passed every check, with the numbers parsed exactly (decimals, never doubles).
@immutable
class NewTransaction {
  const NewTransaction({
    required this.kind,
    required this.portfolioId,
    required this.currency,
    required this.date,
    this.assetSymbol,
    this.assetName,
    this.quantity,
    this.unitPrice,
    this.amount,
    this.fee,
    this.note,
  });

  final TransactionKind kind;
  final String portfolioId;
  final String currency;
  final DateTime date;
  final String? assetSymbol;
  final String? assetName;
  final Decimal? quantity;
  final Decimal? unitPrice;

  /// The amount typed for cash entries and dividends. Trades carry quantity and price instead:
  /// the server derives the total.
  final Decimal? amount;
  final Decimal? fee;
  final String? note;
}

/// The result of checking a draft: the problems by field, or the validated transaction.
@immutable
class DraftValidation {
  const DraftValidation(this.issues, this.value);

  final Map<TxField, TxIssue> issues;
  final NewTransaction? value;

  bool get isValid => issues.isEmpty;
}

/// Which fields an entry type needs.
extension TransactionKindForm on TransactionKind {
  bool get isTrade =>
      this == TransactionKind.buy || this == TransactionKind.sell;
  bool get needsAsset => isTrade || this == TransactionKind.dividend;
  bool get needsAmount => !isTrade;
  bool get allowsFee => isTrade;
}

const int quantityPlaces = 8;
const int unitPricePlaces = 6;
final Decimal _maxValue = Decimal.parse('1000000000000');
final RegExp _plainNumber = RegExp(r'^\d+(\.\d+)?$');
final DateTime earliestTradeDate = DateTime(2000);

/// Reads [text] as a positive (or, with [allowZero], non-negative) decimal with at most
/// [places] decimals. Returns the number or the problem, never both.
(Decimal?, TxIssue?) parseNumber(
  String text, {
  required int places,
  bool allowZero = false,
}) {
  final t = text.trim();
  if (t.isEmpty) return (null, const TxIssue(TxFieldError.required));
  if (t.startsWith('-') && _plainNumber.hasMatch(t.substring(1))) {
    return (null, const TxIssue(TxFieldError.negative));
  }
  if (!_plainNumber.hasMatch(t)) {
    return (null, const TxIssue(TxFieldError.notANumber));
  }
  final value = Decimal.parse(t);
  if (value.scale > places) {
    return (null, TxIssue(TxFieldError.tooManyDecimals, places: places));
  }
  if (value == Decimal.zero && !allowZero) {
    return (null, const TxIssue(TxFieldError.notPositive));
  }
  if (value >= _maxValue) return (null, const TxIssue(TxFieldError.tooLarge));
  return (value, null);
}

/// Checks a draft against the rules for its type. The server checks again (and is the authority,
/// for example that a sale does not exceed the units held); this only gives instant, readable
/// feedback. [today] is the current calendar day and [currency] the posting currency.
DraftValidation validateDraft(
  TransactionDraft draft, {
  required DateTime today,
  required String currency,
}) {
  final issues = <TxField, TxIssue>{};
  final kind = draft.kind;
  final minor = CurrencyInfo.of(currency).minorUnits;

  if (draft.portfolioId == null) {
    issues[TxField.portfolio] = const TxIssue(TxFieldError.required);
  }
  if (kind.needsAsset && draft.assetSymbol == null) {
    issues[TxField.asset] = const TxIssue(TxFieldError.required);
  }

  final date = draft.date;
  if (date == null) {
    issues[TxField.date] = const TxIssue(TxFieldError.required);
  } else {
    final day = DateTime(date.year, date.month, date.day);
    final limit = DateTime(today.year, today.month, today.day);
    if (day.isAfter(limit)) {
      issues[TxField.date] = const TxIssue(TxFieldError.futureDate);
    } else if (day.isBefore(earliestTradeDate)) {
      issues[TxField.date] = const TxIssue(TxFieldError.tooOld);
    }
  }

  Decimal? quantity;
  Decimal? unitPrice;
  Decimal? amount;
  Decimal? fee;
  if (kind.isTrade) {
    final (q, qi) = parseNumber(draft.quantity, places: quantityPlaces);
    quantity = q;
    if (qi != null) issues[TxField.quantity] = qi;
    final (p, pi) = parseNumber(draft.unitPrice, places: unitPricePlaces);
    unitPrice = p;
    if (pi != null) issues[TxField.unitPrice] = pi;
  }
  if (kind.needsAmount) {
    final (a, ai) = parseNumber(draft.amount, places: minor);
    amount = a;
    if (ai != null) issues[TxField.amount] = ai;
  }
  if (kind.allowsFee && draft.fee.trim().isNotEmpty) {
    final (f, fi) = parseNumber(draft.fee, places: minor, allowZero: true);
    fee = f;
    if (fi != null) issues[TxField.fee] = fi;
  }

  if (issues.isNotEmpty) return DraftValidation(issues, null);
  final note = draft.note.trim();
  return DraftValidation(
    const {},
    NewTransaction(
      kind: kind,
      portfolioId: draft.portfolioId!,
      currency: currency,
      date: DateTime(date!.year, date.month, date.day),
      assetSymbol: kind.needsAsset ? draft.assetSymbol : null,
      assetName: kind.needsAsset ? draft.assetName : null,
      quantity: quantity,
      unitPrice: unitPrice,
      amount: amount,
      fee: fee,
      note: note.isEmpty ? null : note,
    ),
  );
}

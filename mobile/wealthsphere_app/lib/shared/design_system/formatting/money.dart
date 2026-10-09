import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

/// An amount of money: exact [Decimal] plus an ISO 4217-style currency code (ADR-0003).
///
/// Amounts travel as **strings** in JSON (`{"amount": "1234.50", "currency": "USD"}`); JSON
/// numbers are rejected because they cannot be trusted to carry exact decimal values. The client
/// only holds and formats money: it never adds, converts or derives amounts (the backend is
/// authoritative for financial calculations).
@immutable
class Money {
  Money(this.amount, String currencyCode)
    : currencyCode = _checkCurrency(currencyCode);

  /// Parses a plain decimal string such as `"1234.50"` or `"-0.005"`.
  factory Money.parse(String amount, String currencyCode) {
    if (!_amountPattern.hasMatch(amount)) {
      throw FormatException(
        'Invalid money amount "$amount": expected a plain decimal string',
      );
    }
    return Money(Decimal.parse(amount), currencyCode);
  }

  /// Builds a [Money] from the API representation. Throws [FormatException] for anything that is
  /// not `{"amount": <string>, "currency": <string>}`.
  factory Money.fromJson(Object? json) {
    if (json is! Map<String, dynamic>) {
      throw FormatException(
        'Money must be a JSON object, got ${json.runtimeType}',
      );
    }
    final amount = json['amount'];
    final currency = json['currency'];
    if (amount is! String) {
      throw FormatException(
        'Money.amount must be a string (money is never a JSON number), got ${amount.runtimeType}',
      );
    }
    if (currency is! String) {
      throw FormatException(
        'Money.currency must be a string, got ${currency.runtimeType}',
      );
    }
    return Money.parse(amount, currency);
  }

  factory Money.zero(String currencyCode) => Money(Decimal.zero, currencyCode);

  final Decimal amount;
  final String currencyCode;

  static final RegExp _amountPattern = RegExp(r'^-?\d+(\.\d+)?$');
  static final RegExp _currencyPattern = RegExp(r'^[A-Z][A-Z0-9]{2,9}$');

  static String _checkCurrency(String code) {
    if (!_currencyPattern.hasMatch(code)) {
      throw FormatException(
        'Invalid currency code "$code": expected 3 to 10 upper-case letters or digits',
      );
    }
    return code;
  }

  bool get isNegative => amount.sign < 0;
  bool get isZero => amount.sign == 0;
  bool get isPositive => amount.sign > 0;

  Money abs() => Money(amount.abs(), currencyCode);

  Map<String, String> toJson() => <String, String>{
    'amount': amount.toString(),
    'currency': currencyCode,
  };

  @override
  bool operator ==(Object other) =>
      other is Money &&
      other.currencyCode == currencyCode &&
      other.amount == amount;

  @override
  int get hashCode => Object.hash(currencyCode, amount);

  @override
  String toString() => '$amount $currencyCode';
}

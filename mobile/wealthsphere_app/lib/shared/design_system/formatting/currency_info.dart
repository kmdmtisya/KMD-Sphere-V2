import 'package:flutter/foundation.dart';

/// Display facts about a currency: ISO 4217 minor units (how many decimals an amount is rounded
/// to when shown or posted, ADR-0006) and an optional unambiguous symbol.
///
/// Symbols are only provided where they are unambiguous. Everything else is shown with its code
/// ("AED 1,234.50"), never with a guessed symbol.
@immutable
class CurrencyInfo {
  const CurrencyInfo(this.code, this.minorUnits, {this.symbol});

  final String code;

  /// Number of decimal places for amounts of this currency.
  final int minorUnits;

  final String? symbol;

  /// Known currency, or a 2-decimal default with no symbol for anything else (custom assets,
  /// crypto tickers). Use `fractionDigits` on the formatter for assets that need more precision.
  static CurrencyInfo of(String code) => _table[code] ?? CurrencyInfo(code, 2);

  static const Map<String, CurrencyInfo> _table = <String, CurrencyInfo>{
    // Two decimals (the ISO 4217 default) with an unambiguous symbol.
    'USD': CurrencyInfo('USD', 2, symbol: r'$'),
    'EUR': CurrencyInfo('EUR', 2, symbol: '€'),
    'GBP': CurrencyInfo('GBP', 2, symbol: '£'),
    'INR': CurrencyInfo('INR', 2, symbol: '₹'),
    'ILS': CurrencyInfo('ILS', 2, symbol: '₪'),
    'PHP': CurrencyInfo('PHP', 2, symbol: '₱'),
    // Two decimals, shown with the code.
    'AED': CurrencyInfo('AED', 2),
    'SAR': CurrencyInfo('SAR', 2),
    'QAR': CurrencyInfo('QAR', 2),
    'KES': CurrencyInfo('KES', 2),
    'TZS': CurrencyInfo('TZS', 2),
    'NGN': CurrencyInfo('NGN', 2),
    'ZAR': CurrencyInfo('ZAR', 2),
    'EGP': CurrencyInfo('EGP', 2),
    'CHF': CurrencyInfo('CHF', 2),
    'CAD': CurrencyInfo('CAD', 2),
    'AUD': CurrencyInfo('AUD', 2),
    'NZD': CurrencyInfo('NZD', 2),
    'CNY': CurrencyInfo('CNY', 2),
    'HKD': CurrencyInfo('HKD', 2),
    'SGD': CurrencyInfo('SGD', 2),
    // Zero decimals.
    'JPY': CurrencyInfo('JPY', 0, symbol: '¥'),
    'KRW': CurrencyInfo('KRW', 0, symbol: '₩'),
    'VND': CurrencyInfo('VND', 0, symbol: '₫'),
    'UGX': CurrencyInfo('UGX', 0),
    'RWF': CurrencyInfo('RWF', 0),
    'XAF': CurrencyInfo('XAF', 0),
    'XOF': CurrencyInfo('XOF', 0),
    'CLP': CurrencyInfo('CLP', 0),
    'ISK': CurrencyInfo('ISK', 0),
    'PYG': CurrencyInfo('PYG', 0),
    // Three decimals.
    'KWD': CurrencyInfo('KWD', 3),
    'BHD': CurrencyInfo('BHD', 3),
    'OMR': CurrencyInfo('OMR', 3),
    'JOD': CurrencyInfo('JOD', 3),
    'TND': CurrencyInfo('TND', 3),
    // Crypto tickers are not ISO 4217; eight decimals is a display convention, not a rounding rule
    // for ledger values (those keep full precision).
    'BTC': CurrencyInfo('BTC', 8),
    'ETH': CurrencyInfo('ETH', 8),
  };
}

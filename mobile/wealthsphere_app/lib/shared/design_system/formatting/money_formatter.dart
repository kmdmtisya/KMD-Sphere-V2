import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import 'currency_info.dart';
import 'money.dart';
import 'number_style.dart';

/// How the currency is written next to the number.
enum CurrencyDisplay {
  /// The unambiguous symbol when one exists (`$`, `€`, `£`), otherwise the code (`AED`).
  symbol,

  /// Always the ISO code (`USD 1,234.50`).
  code,

  /// Number only.
  none,
}

/// Magnitude suffixes for compact amounts. Replace for other languages (localised in the UI
/// layer); index 0 is "no suffix", then thousands, millions, billions, trillions.
@immutable
class CompactLabels {
  const CompactLabels(this.suffixes);

  static const CompactLabels english = CompactLabels(<String>[
    '',
    'K',
    'M',
    'B',
    'T',
  ]);

  final List<String> suffixes;
}

/// Formats [Money] for display (ADR-0003, ADR-0006).
///
/// - Rounding is half-up (ties away from zero) to the currency's minor units, applied once at
///   display time; the underlying amount is never altered.
/// - The sign never shows for a value that rounds to zero ("-0.004" displays as "0.00").
/// - Works on [Decimal] only, so amounts beyond 2^53 are exact.
@immutable
class MoneyFormatter {
  const MoneyFormatter({this.locale = 'en'});

  final String locale;

  NumberStyle get _style => NumberStyle.forLocale(locale);

  /// Full amount, e.g. `$1,234.50`, `-€1.234,50` (de), `¥3`, `KWD 1.001`.
  String format(
    Money money, {
    CurrencyDisplay currency = CurrencyDisplay.symbol,
    SignDisplay sign = SignDisplay.auto,
    int? fractionDigits,
  }) {
    final digits =
        fractionDigits ?? CurrencyInfo.of(money.currencyCode).minorUnits;
    final rounded = money.amount.round(scale: digits);
    final number = _style.renderUnsigned(rounded.abs(), digits);
    return _compose(money, rounded, number, currency, sign);
  }

  /// Short amount for tight spaces and chart axes: `$999`, `$1.2K`, `$1.9M`, `$1.3B`.
  /// Values are rounded half-up to one decimal of the chosen magnitude; a value that rounds up
  /// to the next magnitude is promoted (999,950 -> `$1M`, not `$1,000K`).
  String formatCompact(
    Money money, {
    CurrencyDisplay currency = CurrencyDisplay.symbol,
    SignDisplay sign = SignDisplay.auto,
    CompactLabels labels = CompactLabels.english,
  }) {
    final magnitude = money.amount.abs();
    final top = labels.suffixes.length - 1;
    var index = 0;
    while (index < top && magnitude >= _thousandPowers[index + 1]) {
      index++;
    }
    var rounded = _scaleAndRound(magnitude, index);
    if (index < top && rounded >= _thousand) {
      index++;
      rounded = _scaleAndRound(magnitude, index);
    }
    final digits = rounded.scale;
    final number =
        '${_style.renderUnsigned(rounded, digits)}${labels.suffixes[index]}';
    final signed = money.isNegative && rounded.sign != 0 ? -rounded : rounded;
    return _compose(money, signed, number, currency, sign);
  }

  /// Number only, grouped and rounded to [fractionDigits], with sign handling.
  String formatNumber(
    Decimal value, {
    int fractionDigits = 2,
    SignDisplay sign = SignDisplay.auto,
  }) {
    final rounded = value.round(scale: fractionDigits);
    final number = _style.renderUnsigned(rounded.abs(), fractionDigits);
    final signText = _style.signText(
      sign,
      isNegative: rounded.sign < 0,
      isZero: rounded.sign == 0,
    );
    return '$signText$number';
  }

  /// A plain spoken-friendly form for screen readers: `1,234.50 USD`, with the sign as a word
  /// handled by the caller's localisation.
  String formatForSpeech(Money money, {int? fractionDigits}) => format(
    money,
    currency: CurrencyDisplay.code,
    sign: SignDisplay.auto,
    fractionDigits: fractionDigits,
  );

  // ---------------------------------------------------------------------------------------
  static final Decimal _thousand = Decimal.fromInt(1000);
  static final List<Decimal> _thousandPowers = <Decimal>[
    Decimal.one,
    Decimal.fromInt(1000),
    Decimal.fromInt(1000000),
    Decimal.fromInt(1000000000),
    Decimal.fromBigInt(BigInt.from(1000000000000)),
  ];

  /// `magnitude / 1000^index` rounded to one decimal (none below 1,000; two below 1 so that
  /// small amounts do not collapse to zero).
  static Decimal _scaleAndRound(Decimal magnitude, int index) {
    final scaled = magnitude.shift(-3 * index);
    if (index > 0) return scaled.round(scale: 1);
    return scaled < Decimal.one ? scaled.round(scale: 2) : scaled.round();
  }

  String _compose(
    Money money,
    Decimal roundedSigned,
    String number,
    CurrencyDisplay currency,
    SignDisplay sign,
  ) {
    final style = _style;
    final negative = roundedSigned.sign < 0;
    final zero = roundedSigned.sign == 0;
    final signText = style.signText(sign, isNegative: negative, isZero: zero);
    if (currency == CurrencyDisplay.none) return '$signText$number';

    final info = CurrencyInfo.of(money.currencyCode);
    final symbol = currency == CurrencyDisplay.symbol
        ? (info.symbol ?? info.code)
        : info.code;
    final (positive, negativePattern) = NumberStyle.subPatterns(
      style.symbols.CURRENCY_PATTERN,
    );

    // Locales with a dedicated negative pattern (e.g. Arabic) own the sign placement.
    final useNegativePattern =
        negative && sign == SignDisplay.auto && negativePattern != null;
    final pattern = useNegativePattern ? negativePattern : positive;
    final (before, after) = NumberStyle.splitPattern(pattern);

    final alphabetic = RegExp(r'^[A-Za-z]+$').hasMatch(symbol);
    var prefix = before.replaceAll('¤', alphabetic ? '$symbol ' : symbol);
    var suffix = after.replaceAll('¤', alphabetic ? ' $symbol' : symbol);
    // A code that sits directly against the number needs a separating space ("AED 1,234.50"),
    // but not when the pattern already has one (de: "1.234,50 €").
    if (alphabetic) {
      prefix = prefix.replaceAll('  ', ' ').replaceAll('  ', ' ');
      suffix = suffix.replaceAll('  ', ' ');
    }
    final body = '$prefix$number$suffix';
    return useNegativePattern ? body : '$signText$body';
  }
}

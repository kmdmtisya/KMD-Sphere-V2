import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import 'number_style.dart';

/// Formats percentages. Inputs are **percentage points** as delivered by the API
/// (`"6.32"` means 6.32%), never fractions, so nothing is multiplied or divided on the client.
///
/// Rounding is half-up (ADR-0006) and a value that rounds to zero shows without a sign.
@immutable
class PercentFormatter {
  const PercentFormatter({this.locale = 'en'});

  final String locale;

  /// `6.32%`, `-1.50%`, `+0.25%` (with [SignDisplay.always]); `de`: `6,32 %`.
  String format(
    Decimal percentPoints, {
    int fractionDigits = 2,
    SignDisplay sign = SignDisplay.auto,
  }) {
    final style = NumberStyle.forLocale(locale);
    final rounded = percentPoints.round(scale: fractionDigits);
    final number = style.renderUnsigned(rounded.abs(), fractionDigits);
    final signText = style.signText(
      sign,
      isNegative: rounded.sign < 0,
      isZero: rounded.sign == 0,
    );
    final (before, after) = NumberStyle.splitPattern(
      style.symbols.PERCENT_PATTERN,
    );
    final percent = style.symbols.PERCENT;
    final body =
        '${before.replaceAll('%', percent)}$number${after.replaceAll('%', percent)}';
    return '$signText$body';
  }
}

import 'package:decimal/decimal.dart';
import 'package:flutter/services.dart';

import '../../shared/design_system/formatting/number_style.dart';

/// Reads and edits decimal numbers typed in the user's locale (`1234,50` in German, `1234.50` in
/// English). The result is an exact [Decimal]: nothing passes through a binary float.
///
/// Digits are the ASCII digits 0-9 and the only separators accepted are the locale's decimal
/// separator and an optional leading minus; thousands separators are not typed (the field shows
/// plain digits), and pasted ones are removed by [formatter].
class DecimalInput {
  DecimalInput(String locale)
    : decimalSeparator = NumberStyle.forLocale(locale).symbols.DECIMAL_SEP,
      groupSeparator = NumberStyle.forLocale(locale).symbols.GROUP_SEP;

  final String decimalSeparator;
  final String groupSeparator;

  /// The decimal for [text], or null if it is empty or malformed.
  Decimal? parse(String text) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return null;
    // Only digits, a leading minus and the locale's decimal separator are meaningful. A '.' in a
    // comma-decimal locale (or a grouping separator) would otherwise be misread, so reject it.
    for (var i = 0; i < trimmed.length; i++) {
      final ch = trimmed[i];
      final digit = ch.codeUnitAt(0) >= 0x30 && ch.codeUnitAt(0) <= 0x39;
      if (!digit && ch != decimalSeparator && !(ch == '-' && i == 0)) {
        return null;
      }
    }
    final dotted = trimmed.replaceAll(decimalSeparator, '.');
    if (!_plain.hasMatch(dotted)) return null;
    return Decimal.tryParse(dotted);
  }

  /// Number of digits after the decimal separator, or 0.
  int fractionDigits(String text) {
    final at = text.indexOf(decimalSeparator);
    return at == -1 ? 0 : text.length - at - decimalSeparator.length;
  }

  /// Text for [value] as the field shows it: plain digits, locale decimal separator, no grouping.
  String format(Decimal value, {int minFractionDigits = 0}) {
    var text = value.toString();
    final dot = text.indexOf('.');
    final have = dot == -1 ? 0 : text.length - dot - 1;
    if (have < minFractionDigits) {
      text =
          '${dot == -1 ? '$text.' : text}${'0' * (minFractionDigits - have)}';
    }
    return text.replaceAll('.', decimalSeparator);
  }

  /// Restricts typing to digits, one decimal separator, at most [maxFractionDigits] decimals and
  /// (when [allowNegative]) a single leading minus. Pasted grouping separators are dropped.
  TextInputFormatter formatter({
    required int maxFractionDigits,
    bool allowNegative = false,
  }) => _DecimalFormatter(
    separator: decimalSeparator,
    group: groupSeparator,
    maxFractionDigits: maxFractionDigits,
    allowNegative: allowNegative,
  );

  static final RegExp _plain = RegExp(r'^-?\d+(\.\d+)?$');
}

class _DecimalFormatter extends TextInputFormatter {
  _DecimalFormatter({
    required this.separator,
    required this.group,
    required this.maxFractionDigits,
    required this.allowNegative,
  });

  final String separator;
  final String group;
  final int maxFractionDigits;
  final bool allowNegative;

  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    final buffer = StringBuffer();
    var seenSeparator = false;
    var fraction = 0;
    for (var i = 0; i < newValue.text.length; i++) {
      final ch = newValue.text[i];
      if (ch == '-' && allowNegative && buffer.isEmpty) {
        buffer.write(ch);
      } else if (ch == separator && maxFractionDigits > 0 && !seenSeparator) {
        seenSeparator = true;
        buffer.write(ch);
      } else if (ch.codeUnitAt(0) >= 0x30 && ch.codeUnitAt(0) <= 0x39) {
        if (seenSeparator) {
          if (fraction >= maxFractionDigits) continue;
          fraction++;
        }
        buffer.write(ch);
      }
      // Anything else (letters, grouping separators, a second separator) is dropped.
    }
    final text = buffer.toString();
    if (text == newValue.text) return newValue;
    final offset = text.length < newValue.selection.baseOffset
        ? text.length
        : newValue.selection.baseOffset.clamp(0, text.length);
    return TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: offset),
    );
  }
}

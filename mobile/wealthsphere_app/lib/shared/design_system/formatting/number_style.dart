import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';
import 'package:intl/intl.dart';
import 'package:intl/number_symbols.dart';
import 'package:intl/number_symbols_data.dart';

/// How the sign of a value is shown.
enum SignDisplay {
  /// Minus for negative values only (default).
  auto,

  /// Plus for positive, minus for negative, nothing for zero.
  always,

  /// Never a sign (absolute value).
  never,
}

/// Locale conventions for rendering numbers: separators, digit set and digit grouping.
///
/// All rendering works on [Decimal] and strings. Values are never converted to a binary
/// floating-point number, so amounts far beyond 2^53 and exact ties (x.005) format correctly.
@immutable
class NumberStyle {
  const NumberStyle._(
    this.locale,
    this.symbols,
    this.primaryGroup,
    this.secondaryGroup,
  );

  /// Resolves [locale] (`en`, `en_IN`, `de-DE`, ...), falling back to the language and then `en`.
  factory NumberStyle.forLocale(String locale) {
    final canonical = Intl.canonicalizedLocale(locale);
    final symbols =
        numberFormatSymbols[canonical] ??
        numberFormatSymbols[canonical.split('_').first] ??
        numberFormatSymbols['en']!;
    final resolved = numberFormatSymbols.containsKey(canonical)
        ? canonical
        : numberFormatSymbols.containsKey(canonical.split('_').first)
        ? canonical.split('_').first
        : 'en';
    final grouping = _groupingFrom(symbols.DECIMAL_PATTERN);
    return NumberStyle._(resolved, symbols, grouping.$1, grouping.$2);
  }

  final String locale;
  final NumberSymbols symbols;

  /// Size of the group nearest the decimal point (3 in nearly all locales).
  final int primaryGroup;

  /// Size of the remaining groups (2 in en_IN: 12,34,567). Equal to [primaryGroup] elsewhere.
  final int secondaryGroup;

  /// `#,##,##0.###` -> (3, 2); `#,##0.###` -> (3, 3); no comma -> (0, 0) meaning no grouping.
  static (int, int) _groupingFrom(String pattern) {
    final integerPart = pattern.split('.').first;
    final segments = integerPart.split(',');
    if (segments.length < 2) return (0, 0);
    final primary = segments.last.length;
    final secondary = segments.length >= 3
        ? segments[segments.length - 2].length
        : primary;
    return (primary, secondary);
  }

  /// Renders a **non-negative**, already-rounded [value] with exactly [fractionDigits] decimals.
  String renderUnsigned(Decimal value, int fractionDigits) {
    assert(value.sign >= 0, 'renderUnsigned expects a non-negative value');
    final fixed = value.toStringAsFixed(fractionDigits);
    final dot = fixed.indexOf('.');
    final integer = dot == -1 ? fixed : fixed.substring(0, dot);
    final fraction = dot == -1 ? '' : fixed.substring(dot + 1);
    final grouped = _group(integer);
    return _localiseDigits(
      fractionDigits > 0 ? '$grouped${symbols.DECIMAL_SEP}$fraction' : grouped,
    );
  }

  String _group(String digits) {
    if (primaryGroup == 0 || digits.length <= primaryGroup) return digits;
    final parts = <String>[];
    var end = digits.length;
    var size = primaryGroup;
    while (end > size) {
      parts.insert(0, digits.substring(end - size, end));
      end -= size;
      size = secondaryGroup;
    }
    parts.insert(0, digits.substring(0, end));
    return parts.join(symbols.GROUP_SEP);
  }

  String _localiseDigits(String text) {
    final zero = symbols.ZERO_DIGIT;
    if (zero == '0') return text;
    final offset = zero.codeUnitAt(0) - 0x30;
    return String.fromCharCodes(
      text.codeUnits.map((u) => u >= 0x30 && u <= 0x39 ? u + offset : u),
    );
  }

  /// The sign prefix for a value, or '' when none should be shown. [isNegative] and [isZero]
  /// must describe the value *after rounding* so that -0.004 never shows as "-0.00".
  String signText(
    SignDisplay display, {
    required bool isNegative,
    required bool isZero,
  }) {
    if (isZero || display == SignDisplay.never) return '';
    if (isNegative) return symbols.MINUS_SIGN;
    return display == SignDisplay.always ? symbols.PLUS_SIGN : '';
  }

  static final RegExp _numberSlot = RegExp(r'[#0,]+(\.[#0]+)?');

  /// Splits a locale pattern such as `¤#,##0.00` or `#,##0.00 ¤` into the text before and after
  /// the number slot.
  static (String, String) splitPattern(String pattern) {
    final match = _numberSlot.firstMatch(pattern);
    if (match == null) return ('', pattern);
    return (pattern.substring(0, match.start), pattern.substring(match.end));
  }

  /// The positive and (if the locale defines one) negative sub-patterns of [pattern].
  static (String, String?) subPatterns(String pattern) {
    final parts = pattern.split(';');
    return (parts.first, parts.length > 1 ? parts[1] : null);
  }
}

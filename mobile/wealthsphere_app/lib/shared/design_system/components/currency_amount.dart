import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import 'context_locale.dart';

/// Shows a [Money] value with locale-correct formatting, and optionally the same holding in its
/// own (native) currency on a second line.
///
/// - Display only: nothing is converted or calculated; both amounts come from the backend.
/// - Screen readers get one spoken label ("minus 1,234.50 USD") instead of symbol-by-symbol
///   reading, and the secondary line is announced as the original currency.
/// - A very wide figure scales down to fit instead of overflowing, so large wealth values stay on
///   one line at large text sizes.
class CurrencyAmount extends StatelessWidget {
  const CurrencyAmount({
    required this.money,
    this.nativeMoney,
    this.style,
    this.compact = false,
    this.currency = CurrencyDisplay.symbol,
    this.sign = SignDisplay.auto,
    this.alignment = AlignmentDirectional.centerStart,
    super.key,
  });

  final Money money;

  /// The same value in the asset's own currency. Shown only when its currency differs.
  final Money? nativeMoney;

  /// Defaults to the tabular `amount` style.
  final TextStyle? style;

  /// `$1.2M` instead of `$1,234,567.89`.
  final bool compact;

  final CurrencyDisplay currency;
  final SignDisplay sign;
  final AlignmentGeometry alignment;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final formatter = context.moneyFormatter;
    final text = compact
        ? formatter.formatCompact(money, currency: currency, sign: sign)
        : formatter.format(money, currency: currency, sign: sign);

    final native = nativeMoney;
    final showNative =
        native != null && native.currencyCode != money.currencyCode;

    final spoken = StringBuffer(_spoken(l10n, formatter, money));
    if (showNative) {
      spoken
        ..write(', ')
        ..write(l10n.nativeAmountSpoken(_spoken(l10n, formatter, native)));
    }

    return Semantics(
      label: spoken.toString(),
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: alignment,
            child: Text(
              text,
              style: style ?? context.wealthText.amount,
              maxLines: 1,
              softWrap: false,
            ),
          ),
          if (showNative)
            Text(
              formatter.format(native, currency: CurrencyDisplay.code),
              style: context.wealthText.caption,
            ),
        ],
      ),
    );
  }

  static String _spoken(
    AppLocalizations l10n,
    MoneyFormatter formatter,
    Money value,
  ) {
    final digits = CurrencyInfo.of(value.currencyCode).minorUnits;
    final rounded = value.amount.round(scale: digits);
    final number = formatter.formatNumber(
      rounded.abs(),
      fractionDigits: digits,
    );
    return rounded.sign < 0
        ? l10n.amountSpokenNegative(number, value.currencyCode)
        : l10n.amountSpoken(number, value.currencyCode);
  }
}

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'context_locale.dart';

enum ChangeDirection { up, down, flat }

/// A gain or loss, shown with an arrow icon, an explicit sign and the value, so it never relies
/// on colour alone, and announced as one phrase ("up 8.42 percent year to date").
///
/// Give a [percent] (percentage points, as delivered by the API), an [amount], or both. The
/// direction follows the percent when present, otherwise the amount, **after** rounding to the
/// displayed precision: a change that rounds to 0.00% is shown as unchanged.
class ChangeIndicator extends StatelessWidget {
  const ChangeIndicator({
    this.percent,
    this.amount,
    this.periodLabel,
    this.percentDigits = 2,
    this.style,
    super.key,
  }) : assert(
         percent != null || amount != null,
         'Provide a percent, an amount or both',
       );

  final Decimal? percent;
  final Money? amount;

  /// Already-localised period text such as "YTD" or "year to date". Spoken after the value.
  final String? periodLabel;

  final int percentDigits;
  final TextStyle? style;

  ChangeDirection get direction {
    if (percent != null) {
      return _directionOf(percent!.round(scale: percentDigits).sign);
    }
    final money = amount!;
    final digits = CurrencyInfo.of(money.currencyCode).minorUnits;
    return _directionOf(money.amount.round(scale: digits).sign);
  }

  static ChangeDirection _directionOf(int sign) => sign > 0
      ? ChangeDirection.up
      : sign < 0
      ? ChangeDirection.down
      : ChangeDirection.flat;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final money = context.moneyFormatter;
    final percents = context.percentFormatter;
    final dir = direction;

    final color = switch (dir) {
      ChangeDirection.up => colors.positiveText,
      ChangeDirection.down => colors.negativeText,
      ChangeDirection.flat => colors.textMuted,
    };
    final icon = switch (dir) {
      ChangeDirection.up => Icons.arrow_upward_rounded,
      ChangeDirection.down => Icons.arrow_downward_rounded,
      ChangeDirection.flat => Icons.remove_rounded,
    };

    final shown = <String>[];
    final spokenValues = <String>[];
    if (amount != null) {
      shown.add(money.format(amount!, sign: SignDisplay.always));
      final digits = CurrencyInfo.of(amount!.currencyCode).minorUnits;
      spokenValues.add(
        money.formatForSpeech(
          Money(
            amount!.amount.round(scale: digits).abs(),
            amount!.currencyCode,
          ),
        ),
      );
    }
    if (percent != null) {
      final text = percents.format(
        percent!,
        fractionDigits: percentDigits,
        sign: SignDisplay.always,
      );
      shown.add(amount != null ? '($text)' : text);
      final rounded = percent!.round(scale: percentDigits).abs();
      spokenValues.add(
        l10n.percentSpoken(
          money.formatNumber(rounded, fractionDigits: percentDigits),
        ),
      );
    }

    final phrase = <String>[
      switch (dir) {
        ChangeDirection.up => l10n.changeUpSpoken(spokenValues.join(', ')),
        ChangeDirection.down => l10n.changeDownSpoken(spokenValues.join(', ')),
        ChangeDirection.flat => l10n.changeUnchangedSpoken,
      },
      ?periodLabel,
    ].join(' ');

    return Semantics(
      label: phrase,
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: AppSpacing.xxs),
          Flexible(
            child: Text(
              shown.join(' '),
              style: (style ?? context.wealthText.label).copyWith(
                color: color,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

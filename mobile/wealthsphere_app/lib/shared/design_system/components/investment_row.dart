import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';

import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'change_indicator.dart';
import 'currency_amount.dart';

/// One holding in a list: initials avatar, symbol and name, value in the portfolio currency (and
/// the native-currency line when different) and the change. The whole row is one focus target and
/// is read as a single phrase.
///
/// The avatar shows initials only: remote logos are not loaded from content-supplied URLs.
class InvestmentRow extends StatelessWidget {
  const InvestmentRow({
    required this.symbol,
    required this.name,
    required this.value,
    this.nativeValue,
    this.changePercent,
    this.changeAmount,
    this.onTap,
    super.key,
  });

  final String symbol;
  final String name;
  final Money value;
  final Money? nativeValue;
  final Decimal? changePercent;
  final Money? changeAmount;
  final VoidCallback? onTap;

  String get _initials {
    final trimmed = symbol.trim();
    if (trimmed.isEmpty) return '?';
    return trimmed.substring(0, trimmed.length < 2 ? 1 : 2).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final text = context.wealthText;
    final colors = context.wealthColors;
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: AppTouchTarget.android),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: AppSpacing.m,
            vertical: AppSpacing.s,
          ),
          child: Row(
            children: [
              ExcludeSemantics(
                child: CircleAvatar(
                  backgroundColor: colors.surfaceElevated,
                  foregroundColor: colors.textPrimary,
                  child: Text(_initials, style: text.label),
                ),
              ),
              const SizedBox(width: AppSpacing.s),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(symbol, style: text.title),
                    Text(
                      name,
                      style: text.caption.copyWith(color: colors.textMuted),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.s),
              Flexible(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    CurrencyAmount(
                      money: value,
                      nativeMoney: nativeValue,
                      alignment: AlignmentDirectional.centerEnd,
                    ),
                    if (changePercent != null || changeAmount != null)
                      ChangeIndicator(
                        percent: changePercent,
                        amount: changeAmount,
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

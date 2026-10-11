import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'context_locale.dart';
import 'currency_amount.dart';

/// The kinds of ledger entry (docs/design/data-model.md). The ledger is append-only: a correction
/// is a reversal, shown on the corrected entry as [TransactionTile.reversed].
enum TransactionKind {
  buy,
  sell,
  deposit,
  withdrawal,
  dividend,
  interest,
  coupon,
  rent,
  distribution,
  fee,
  tax,
  transferIn,
  transferOut,
  valuationAdjustment;

  /// The API's name for the kind (`BUY`, `TRANSFER_IN`, ...).
  static TransactionKind parse(String apiName) => switch (apiName) {
    'BUY' => buy,
    'SELL' => sell,
    'DEPOSIT' => deposit,
    'WITHDRAWAL' => withdrawal,
    'DIVIDEND' => dividend,
    'INTEREST' => interest,
    'COUPON' => coupon,
    'RENT' => rent,
    'DISTRIBUTION' => distribution,
    'FEE' => fee,
    'TAX' => tax,
    'TRANSFER_IN' => transferIn,
    'TRANSFER_OUT' => transferOut,
    'VALUATION_ADJUSTMENT' => valuationAdjustment,
    _ => throw FormatException('Unknown transaction type "$apiName"'),
  };
}

/// What an entry does to cash: money in, money out, or nothing (units or value move instead).
enum CashDirection { inflow, outflow, none }

/// One ledger entry in a list: a type icon, the type and its detail, the date and the amount.
///
/// The direction is shown by an icon **and** a sign **and** spoken words, never colour alone. The
/// whole tile is one focus target read as a single phrase. A reversed entry is struck through
/// and says so in words. Amounts arrive ready-made from the backend; nothing is calculated here.
class TransactionTile extends StatelessWidget {
  const TransactionTile({
    required this.kind,
    required this.date,
    required this.amount,
    this.direction,
    this.assetName,
    this.quantity,
    this.unitPrice,
    this.fee,
    this.reversed = false,
    this.onTap,
    super.key,
  });

  final TransactionKind kind;

  /// The trade date.
  final DateTime date;

  /// The posted amount in the posting currency (never negative, except a valuation adjustment).
  final Money amount;

  /// The cash effect. Defaults from [kind]: buys, withdrawals, fees and taxes pay out; sales,
  /// deposits and income pay in; transfers and valuation adjustments move no cash.
  final CashDirection? direction;
  final String? assetName;

  /// Units and unit price of a trade, as ready-made text ("10", "$52.30").
  final String? quantity;
  final String? unitPrice;
  final Money? fee;
  final bool reversed;
  final VoidCallback? onTap;

  CashDirection get _direction => direction ?? defaultDirection(kind);

  /// The cash effect of an entry of [kind] (see [direction]).
  static CashDirection defaultDirection(TransactionKind kind) => switch (kind) {
    TransactionKind.buy ||
    TransactionKind.withdrawal ||
    TransactionKind.fee ||
    TransactionKind.tax => CashDirection.outflow,
    TransactionKind.sell ||
    TransactionKind.deposit ||
    TransactionKind.dividend ||
    TransactionKind.interest ||
    TransactionKind.coupon ||
    TransactionKind.rent ||
    TransactionKind.distribution => CashDirection.inflow,
    TransactionKind.transferIn ||
    TransactionKind.transferOut ||
    TransactionKind.valuationAdjustment => CashDirection.none,
  };

  static IconData _icon(TransactionKind kind) => switch (kind) {
    TransactionKind.buy => Icons.add_shopping_cart_rounded,
    TransactionKind.sell => Icons.sell_outlined,
    TransactionKind.deposit => Icons.south_west_rounded,
    TransactionKind.withdrawal => Icons.north_east_rounded,
    TransactionKind.dividend => Icons.payments_outlined,
    TransactionKind.interest => Icons.percent_rounded,
    TransactionKind.coupon => Icons.receipt_long_outlined,
    TransactionKind.rent => Icons.home_work_outlined,
    TransactionKind.distribution => Icons.call_split_rounded,
    TransactionKind.fee => Icons.price_change_outlined,
    TransactionKind.tax => Icons.account_balance_outlined,
    TransactionKind.transferIn => Icons.login_rounded,
    TransactionKind.transferOut => Icons.logout_rounded,
    TransactionKind.valuationAdjustment => Icons.tune_rounded,
  };

  static String label(AppLocalizations l10n, TransactionKind kind) =>
      switch (kind) {
        TransactionKind.buy => l10n.txBuy,
        TransactionKind.sell => l10n.txSell,
        TransactionKind.deposit => l10n.txDeposit,
        TransactionKind.withdrawal => l10n.txWithdrawal,
        TransactionKind.dividend => l10n.txDividend,
        TransactionKind.interest => l10n.txInterest,
        TransactionKind.coupon => l10n.txCoupon,
        TransactionKind.rent => l10n.txRent,
        TransactionKind.distribution => l10n.txDistribution,
        TransactionKind.fee => l10n.txFee,
        TransactionKind.tax => l10n.txTax,
        TransactionKind.transferIn => l10n.txTransferIn,
        TransactionKind.transferOut => l10n.txTransferOut,
        TransactionKind.valuationAdjustment => l10n.txValuationAdjustment,
      };

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final money = context.moneyFormatter;
    final title = label(l10n, kind);
    final dateText = DateLabels.date(date, locale: context.formatLocale);
    final detail = [
      ?assetName,
      if (quantity != null && unitPrice != null)
        l10n.txQuantityAt(quantity!, unitPrice!)
      else
        ?quantity,
    ].join(' · ');
    final feeText = fee == null ? null : l10n.txFeeLine(money.format(fee!));
    final direction = _direction;
    final directionWord = switch (direction) {
      CashDirection.inflow => l10n.txMoneyIn,
      CashDirection.outflow => l10n.txMoneyOut,
      CashDirection.none => l10n.txNoCash,
    };
    // Money in shows "+", money out shows "-" (the amount is negated for display only).
    final sign = direction == CashDirection.inflow
        ? SignDisplay.always
        : SignDisplay.auto;
    final shown = direction == CashDirection.outflow
        ? Money(-amount.amount, amount.currencyCode)
        : amount;
    final amountSpoken = money.format(amount);
    final spoken = [
      title,
      if (detail.isNotEmpty) detail,
      dateText,
      if (direction == CashDirection.none)
        directionWord
      else
        '$directionWord $amountSpoken',
      ?feeText,
      if (reversed) l10n.txReversed,
    ].join(', ');
    final struck = reversed ? TextDecoration.lineThrough : null;

    return Semantics(
      container: true,
      button: onTap != null,
      label: spoken,
      excludeSemantics: true,
      onTap: onTap,
      child: InkWell(
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
                    child: Icon(_icon(kind), size: 20),
                  ),
                ),
                const SizedBox(width: AppSpacing.s),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: text.title.copyWith(decoration: struck),
                      ),
                      if (detail.isNotEmpty)
                        Text(
                          detail,
                          style: text.caption.copyWith(color: colors.textMuted),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      Text(
                        dateText,
                        style: text.caption.copyWith(color: colors.textMuted),
                      ),
                      if (reversed)
                        Text(
                          l10n.txReversed,
                          style: text.caption.copyWith(
                            color: colors.warningText,
                          ),
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
                        money: shown,
                        sign: sign,
                        alignment: AlignmentDirectional.centerEnd,
                      ),
                      Text(
                        directionWord,
                        style: text.caption.copyWith(color: colors.textMuted),
                      ),
                      if (feeText != null)
                        Text(
                          feeText,
                          style: text.caption.copyWith(color: colors.textMuted),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

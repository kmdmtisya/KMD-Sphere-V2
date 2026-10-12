import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/more_providers.dart';
import '../domain/more_models.dart';

/// Income received: the monthly average, the last 12 months, where it came from and the latest
/// payments. It is a record of the past; the screen says it is not a forecast.
class IncomeScreen extends ConsumerWidget {
  const IncomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final income = ref.watch(incomeDetailProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.moreIncome),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(incomeDetailProvider),
        child: AsyncValueView<IncomeDetail>(
          value: income,
          onRetry: () => ref.invalidate(incomeDetailProvider),
          data: (d) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsetsDirectional.all(AppSpacing.m),
            children: [
              _Headline(detail: d),
              const SizedBox(height: AppSpacing.m),
              _Sources(detail: d),
              const SizedBox(height: AppSpacing.m),
              _Recent(detail: d),
              const SizedBox(height: AppSpacing.m),
              Text(
                l10n.incomeNote,
                style: context.wealthText.caption.copyWith(
                  color: context.wealthColors.textMuted,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Headline extends StatelessWidget {
  const _Headline({required this.detail});

  final IncomeDetail detail;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final muted = text.caption.copyWith(color: context.wealthColors.textMuted);
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.incomeMonthly, style: muted),
          CurrencyAmount(money: detail.monthly, style: text.displayAmount),
          const SizedBox(height: AppSpacing.s),
          Text(l10n.incomeYearly, style: muted),
          CurrencyAmount(money: detail.yearly, style: text.title),
          const SizedBox(height: AppSpacing.xs),
          DataAsOfLabel(asOf: detail.asOf),
          DataQualityNotice(complete: detail.complete),
        ],
      ),
    );
  }
}

class _Sources extends StatelessWidget {
  const _Sources({required this.detail});

  final IncomeDetail detail;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final muted = text.caption.copyWith(color: context.wealthColors.textMuted);
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            header: true,
            child: Text(l10n.incomeBySource, style: text.title),
          ),
          const SizedBox(height: AppSpacing.xs),
          for (final s in detail.bySource)
            MergeSemantics(
              child: Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  vertical: AppSpacing.xs,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(s.label, style: text.body),
                          if (s.sharePercent != null)
                            Text(
                              context.percentFormatter.format(
                                s.sharePercent!,
                                fractionDigits: 1,
                              ),
                              style: muted,
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(width: AppSpacing.s),
                    Flexible(
                      child: CurrencyAmount(
                        money: s.yearly,
                        alignment: AlignmentDirectional.centerEnd,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Recent extends StatelessWidget {
  const _Recent({required this.detail});

  final IncomeDetail detail;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final muted = text.caption.copyWith(color: context.wealthColors.textMuted);
    final locale = context.formatLocale;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            header: true,
            child: Text(l10n.incomeRecent, style: text.title),
          ),
          const SizedBox(height: AppSpacing.xs),
          if (detail.recent.isEmpty)
            Text(l10n.incomeNoRecent, style: text.body),
          for (final p in detail.recent)
            MergeSemantics(
              child: Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  vertical: AppSpacing.xs,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${p.transactionKind == null ? p.kind : TransactionTile.label(l10n, p.transactionKind!)}'
                            ' · ${p.assetName}',
                            style: text.body,
                          ),
                          Text(
                            DateLabels.date(p.date, locale: locale),
                            style: muted,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: AppSpacing.s),
                    Flexible(
                      child: CurrencyAmount(
                        money: p.amount,
                        sign: SignDisplay.always,
                        alignment: AlignmentDirectional.centerEnd,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

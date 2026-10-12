import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/more_providers.dart';
import '../domain/more_models.dart';

/// Net worth: what is owned, what is owed and what is left, each item with its value. Every
/// figure comes from the backend; the screen adds nothing up.
class NetWorthScreen extends ConsumerWidget {
  const NetWorthScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final detail = ref.watch(netWorthDetailProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.moreNetWorth),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(netWorthDetailProvider),
        child: AsyncValueView<NetWorthDetail>(
          value: detail,
          onRetry: () => ref.invalidate(netWorthDetailProvider),
          data: (d) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsetsDirectional.all(AppSpacing.m),
            children: [
              WealthCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      l10n.nwNetWorth,
                      style: context.wealthText.caption.copyWith(
                        color: context.wealthColors.textMuted,
                      ),
                    ),
                    CurrencyAmount(
                      money: d.netWorth,
                      style: context.wealthText.displayAmount,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    DataAsOfLabel(asOf: d.asOf),
                    DataQualityNotice(complete: d.complete),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.m),
              _Section(
                title: l10n.nwAssets,
                section: d.assets,
                showShare: true,
              ),
              const SizedBox(height: AppSpacing.m),
              _Section(
                title: l10n.nwLiabilities,
                section: d.liabilities,
                emptyText: l10n.nwNoLiabilities,
              ),
              const SizedBox(height: AppSpacing.m),
              Text(
                l10n.nwNote,
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

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.section,
    this.showShare = false,
    this.emptyText,
  });

  final String title;
  final NetWorthSection section;
  final bool showShare;
  final String? emptyText;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(header: true, child: Text(title, style: text.title)),
          const SizedBox(height: AppSpacing.xxs),
          CurrencyAmount(money: section.total, style: text.displayAmount),
          const SizedBox(height: AppSpacing.s),
          if (section.items.isEmpty && emptyText != null)
            Text(emptyText!, style: text.body),
          for (final item in section.items)
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
                          Text(item.label, style: text.body),
                          if (showShare && item.sharePercent != null)
                            Text(
                              l10n.nwShare(
                                context.percentFormatter.format(
                                  item.sharePercent!,
                                  fractionDigits: 1,
                                ),
                              ),
                              style: text.caption.copyWith(
                                color: colors.textMuted,
                              ),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(width: AppSpacing.s),
                    Flexible(
                      child: CurrencyAmount(
                        money: item.value,
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

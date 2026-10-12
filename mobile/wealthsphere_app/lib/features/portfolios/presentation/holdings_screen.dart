import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../../shared/domain/wealth_models.dart';
import '../application/holdings_query.dart';
import '../application/portfolio_providers.dart';

String holdingSortLabel(AppLocalizations l10n, HoldingSort sort) =>
    switch (sort) {
      HoldingSort.valueDesc => l10n.holdingsSortValueDesc,
      HoldingSort.valueAsc => l10n.holdingsSortValueAsc,
      HoldingSort.nameAsc => l10n.holdingsSortNameAsc,
      HoldingSort.changeDesc => l10n.holdingsSortChangeDesc,
      HoldingSort.changeAsc => l10n.holdingsSortChangeAsc,
    };

/// Screen 5: the investments of the selected portfolio (or of all of them): search, asset-class
/// chips and a sort. Every holding shows its value in the portfolio currency and, when the asset
/// is in another currency, its own value too. Searching, filtering and sorting are announced to
/// screen readers through a live region, and an empty result says so and offers to clear.
class HoldingsScreen extends ConsumerStatefulWidget {
  const HoldingsScreen({this.onOpen, super.key});

  /// Called with the holding the user taps. Null leaves the rows inert.
  final void Function(HoldingSummary holding)? onOpen;

  @override
  ConsumerState<HoldingsScreen> createState() => _HoldingsScreenState();
}

class _HoldingsScreenState extends ConsumerState<HoldingsScreen> {
  final TextEditingController _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final id = ref.watch(selectedPortfolioIdProvider);
    final holdings = ref.watch(portfolioHoldingsProvider(id));
    final query = ref.watch(holdingsQueryProvider);
    final notifier = ref.read(holdingsQueryProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.holdingsTitle),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(portfolioHoldingsProvider(id)),
        child: AsyncValueView<List<HoldingSummary>>(
          value: holdings,
          onRetry: () => ref.invalidate(portfolioHoldingsProvider(id)),
          isEmpty: (h) => h.isEmpty,
          empty: EmptyState(
            title: l10n.noInvestmentsTitle,
            message: l10n.noInvestmentsMessage,
            icon: Icons.pie_chart_outline_rounded,
          ),
          data: (all) {
            final shown = applyQuery(all, query);
            final classes = assetClassesOf(all);
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsetsDirectional.symmetric(
                vertical: AppSpacing.m,
              ),
              children: [
                Padding(
                  padding: const EdgeInsetsDirectional.symmetric(
                    horizontal: AppSpacing.m,
                  ),
                  child: _SearchField(
                    controller: _search,
                    onChanged: notifier.search,
                    onClear: () {
                      _search.clear();
                      notifier.search('');
                    },
                  ),
                ),
                const SizedBox(height: AppSpacing.s),
                _ClassChips(
                  classes: classes,
                  selected: query.assetClass,
                  onSelected: notifier.filter,
                ),
                const SizedBox(height: AppSpacing.xs),
                Padding(
                  padding: const EdgeInsetsDirectional.symmetric(
                    horizontal: AppSpacing.m,
                  ),
                  child: _ResultsBar(
                    count: shown.length,
                    query: query,
                    onSort: notifier.sortBy,
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                if (shown.isEmpty)
                  _NoMatches(
                    onClear: () {
                      _search.clear();
                      notifier.clearFilters();
                    },
                  )
                else ...[
                  for (final h in shown)
                    InvestmentRow(
                      symbol: h.symbol,
                      name: h.name,
                      value: h.value,
                      nativeValue:
                          h.nativeValue?.currencyCode == h.value?.currencyCode
                          ? null
                          : h.nativeValue,
                      changePercent: h.changePercent,
                      onTap: widget.onOpen == null
                          ? null
                          : () => widget.onOpen!(h),
                    ),
                  Padding(
                    padding: const EdgeInsetsDirectional.all(AppSpacing.m),
                    child: Text(
                      l10n.holdingsValueNote,
                      style: context.wealthText.caption.copyWith(
                        color: context.wealthColors.textMuted,
                      ),
                    ),
                  ),
                ],
              ],
            );
          },
        ),
      ),
    );
  }
}

class _SearchField extends StatelessWidget {
  const _SearchField({
    required this.controller,
    required this.onChanged,
    required this.onClear,
  });

  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return TextField(
      controller: controller,
      onChanged: onChanged,
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        labelText: l10n.holdingsSearchLabel,
        hintText: l10n.holdingsSearchHint,
        prefixIcon: const Icon(Icons.search_rounded),
        suffixIcon: ValueListenableBuilder<TextEditingValue>(
          valueListenable: controller,
          builder: (context, value, _) => value.text.isEmpty
              ? const SizedBox.shrink()
              : IconButton(
                  tooltip: l10n.holdingsClearSearch,
                  onPressed: onClear,
                  icon: const Icon(Icons.close_rounded),
                ),
        ),
      ),
    );
  }
}

class _ClassChips extends StatelessWidget {
  const _ClassChips({
    required this.classes,
    required this.selected,
    required this.onSelected,
  });

  final List<String> classes;
  final String? selected;
  final ValueChanged<String?> onSelected;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    Widget chip(String label, bool isSelected, VoidCallback onTap) {
      return Semantics(
        container: true,
        inMutuallyExclusiveGroup: true,
        selected: isSelected,
        button: true,
        label: isSelected ? '$label, ${l10n.selected}' : label,
        excludeSemantics: true,
        onTap: onTap,
        child: ChoiceChip(
          label: Text(label),
          selected: isSelected,
          showCheckmark: true,
          onSelected: (_) => onTap(),
          materialTapTargetSize: MaterialTapTargetSize.padded,
        ),
      );
    }

    // Chips wrap onto further lines (never a sideways scroller that cuts one in half), so every
    // chip is fully visible and reachable at any text size.
    return Padding(
      padding: const EdgeInsetsDirectional.symmetric(horizontal: AppSpacing.m),
      child: Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xxs,
        children: [
          chip(
            l10n.holdingsFilterAll,
            selected == null,
            () => onSelected(null),
          ),
          for (final c in classes) chip(c, selected == c, () => onSelected(c)),
        ],
      ),
    );
  }
}

class _ResultsBar extends StatelessWidget {
  const _ResultsBar({
    required this.count,
    required this.query,
    required this.onSort,
  });

  final int count;
  final HoldingsQuery query;
  final ValueChanged<HoldingSort> onSort;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final sortLabel = holdingSortLabel(l10n, query.sort);
    final summary = [
      l10n.holdingsCount(count),
      if (query.assetClass != null) l10n.holdingsInClass(query.assetClass!),
      if (query.search.trim().isNotEmpty)
        l10n.holdingsMatching(query.search.trim()),
      l10n.holdingsSortedBy(sortLabel),
    ].join(', ');
    return Row(
      children: [
        // A live region: when the count, filter or sort changes, screen readers read it out.
        Expanded(
          child: Semantics(
            liveRegion: true,
            label: summary,
            excludeSemantics: true,
            child: Text(summary, style: text.caption),
          ),
        ),
        PopupMenuButton<HoldingSort>(
          tooltip: l10n.holdingsSortLabel,
          initialValue: query.sort,
          onSelected: onSort,
          itemBuilder: (context) => [
            for (final sort in HoldingSort.values)
              CheckedPopupMenuItem(
                value: sort,
                checked: sort == query.sort,
                child: Text(holdingSortLabel(l10n, sort)),
              ),
          ],
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              minHeight: AppTouchTarget.android,
              minWidth: AppTouchTarget.android,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.sort_rounded),
                const SizedBox(width: AppSpacing.xxs),
                Text(l10n.holdingsSortLabel, style: text.label),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _NoMatches extends StatelessWidget {
  const _NoMatches({required this.onClear});

  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return EmptyState(
      icon: Icons.search_off_rounded,
      title: l10n.holdingsNoMatchTitle,
      message: l10n.holdingsNoMatchMessage,
      actionLabel: l10n.holdingsClearFilters,
      onAction: onClear,
    );
  }
}

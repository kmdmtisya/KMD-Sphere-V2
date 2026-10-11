import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../portfolios/application/portfolio_providers.dart';
import '../application/ledger_view.dart';
import '../domain/ledger_entry.dart';
import 'ledger_entry_tile.dart';
import 'ledger_labels.dart';

/// Screen 8: the ledger of the selected portfolio (or of all of them): filter chips, entries
/// grouped by month and a way to add one. Entries are never edited; a corrected entry shows as
/// reversed and its reversal appears beside it as a linked entry.
class TransactionsScreen extends ConsumerWidget {
  const TransactionsScreen({this.onOpen, this.onAdd, super.key});

  /// Called with the entry the user taps. Null leaves the rows inert.
  final void Function(LedgerEntry entry)? onOpen;

  /// Called when the user asks to add a transaction. Null hides the button.
  final VoidCallback? onAdd;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final id = ref.watch(selectedPortfolioIdProvider);
    final ledger = ref.watch(ledgerProvider(id));
    final filter = ref.watch(txFilterProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.ledgerTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      floatingActionButton: onAdd == null
          ? null
          : FloatingActionButton.extended(
              onPressed: onAdd,
              icon: const Icon(Icons.add_rounded),
              label: Text(l10n.ledgerAdd),
            ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(ledgerProvider(id)),
        child: AsyncValueView<List<LedgerEntry>>(
          value: ledger,
          onRetry: () => ref.invalidate(ledgerProvider(id)),
          isEmpty: (entries) => entries.isEmpty,
          empty: EmptyState(
            title: l10n.ledgerEmptyTitle,
            message: l10n.ledgerEmptyMessage,
            icon: Icons.receipt_long_outlined,
            actionLabel: onAdd == null ? null : l10n.ledgerAdd,
            onAction: onAdd,
          ),
          data: (all) {
            // A filter whose group has no entries here falls back to showing everything.
            final present = filtersPresent(all);
            final active = present.contains(filter) ? filter : TxFilter.all;
            final shown = filterEntries(all, active);
            final months = groupByMonth(shown);
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsetsDirectional.only(
                top: AppSpacing.m,
                bottom: 96,
              ),
              children: [
                _FilterChips(
                  present: present,
                  selected: active,
                  onSelected: ref.read(txFilterProvider.notifier).select,
                ),
                const SizedBox(height: AppSpacing.xs),
                Padding(
                  padding: const EdgeInsetsDirectional.symmetric(
                    horizontal: AppSpacing.m,
                  ),
                  child: _ResultsLine(count: shown.length, filter: active),
                ),
                if (shown.isEmpty)
                  EmptyState(
                    icon: Icons.filter_list_off_rounded,
                    title: l10n.ledgerNoMatchTitle,
                    message: l10n.ledgerNoMatchMessage,
                    actionLabel: l10n.ledgerShowAll,
                    onAction: () => ref
                        .read(txFilterProvider.notifier)
                        .select(TxFilter.all),
                  )
                else
                  for (final month in months) ...[
                    _MonthHeader(month: month.month),
                    for (final entry in month.entries)
                      LedgerEntryTile(
                        entry: entry,
                        onTap: onOpen == null ? null : () => onOpen!(entry),
                      ),
                  ],
                Padding(
                  padding: const EdgeInsetsDirectional.all(AppSpacing.m),
                  child: Text(
                    l10n.ledgerAppendOnlyNote,
                    style: context.wealthText.caption.copyWith(
                      color: context.wealthColors.textMuted,
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _FilterChips extends StatelessWidget {
  const _FilterChips({
    required this.present,
    required this.selected,
    required this.onSelected,
  });

  final List<TxFilter> present;
  final TxFilter selected;
  final ValueChanged<TxFilter> onSelected;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    // Chips wrap onto further lines instead of scrolling sideways, so each is fully visible and
    // reachable at any text size.
    return Padding(
      padding: const EdgeInsetsDirectional.symmetric(horizontal: AppSpacing.m),
      child: Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xxs,
        children: [
          for (final f in present)
            Semantics(
              container: true,
              inMutuallyExclusiveGroup: true,
              selected: f == selected,
              button: true,
              label: f == selected
                  ? '${txFilterLabel(l10n, f)}, ${l10n.selected}'
                  : txFilterLabel(l10n, f),
              excludeSemantics: true,
              onTap: () => onSelected(f),
              child: ChoiceChip(
                label: Text(txFilterLabel(l10n, f)),
                selected: f == selected,
                showCheckmark: true,
                onSelected: (_) => onSelected(f),
                materialTapTargetSize: MaterialTapTargetSize.padded,
              ),
            ),
        ],
      ),
    );
  }
}

class _ResultsLine extends StatelessWidget {
  const _ResultsLine({required this.count, required this.filter});

  final int count;
  final TxFilter filter;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final summary = [
      l10n.ledgerCount(count),
      if (filter != TxFilter.all)
        l10n.ledgerShowing(txFilterLabel(l10n, filter)),
    ].join(', ');
    // A live region: a change of filter is read out by screen readers.
    return Semantics(
      liveRegion: true,
      label: summary,
      excludeSemantics: true,
      child: Text(summary, style: context.wealthText.caption),
    );
  }
}

class _MonthHeader extends StatelessWidget {
  const _MonthHeader({required this.month});

  final DateTime month;

  @override
  Widget build(BuildContext context) {
    final label = DateLabels.monthYear(month, locale: context.formatLocale);
    return Semantics(
      header: true,
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
          AppSpacing.m,
          AppSpacing.m,
          AppSpacing.m,
          AppSpacing.xxs,
        ),
        child: Text(label, style: context.wealthText.label),
      ),
    );
  }
}

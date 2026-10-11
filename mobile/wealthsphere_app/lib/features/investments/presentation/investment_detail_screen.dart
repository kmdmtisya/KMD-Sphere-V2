import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/charts/charts.dart' as charts;
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../../shared/domain/chart_mapping.dart';
import '../../transactions/domain/ledger_entry.dart';
import '../../transactions/presentation/ledger_entry_tile.dart';
import '../application/investment_providers.dart';
import '../domain/investment_models.dart';

/// Screen 7: one investment. A header with the latest price, where it came from and when; a price
/// chart with a period selector; tabs for fundamentals, income, the position, its transactions
/// and research; and a watchlist action.
///
/// Information only: there is deliberately no Buy or Sell action (this app never places trades).
/// Every figure is the backend's; the position, yield and gain or loss are not calculated here.
class InvestmentDetailScreen extends ConsumerStatefulWidget {
  const InvestmentDetailScreen({
    required this.symbol,
    this.onOpenTransaction,
    super.key,
  });

  final String symbol;

  /// Opens a ledger entry from the Transactions tab. Null leaves the rows inert.
  final void Function(LedgerEntry entry)? onOpenTransaction;

  @override
  ConsumerState<InvestmentDetailScreen> createState() =>
      _InvestmentDetailScreenState();
}

class _InvestmentDetailScreenState
    extends ConsumerState<InvestmentDetailScreen> {
  /// 0 fundamentals, 1 income, 2 position, 3 transactions, 4 research.
  int _section = 0;

  void _toggleWatch(AppLocalizations l10n) {
    final notifier = ref.read(watchlistProvider.notifier);
    final adding = !notifier.isWatching(widget.symbol);
    notifier.toggle(widget.symbol);
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(
            adding ? l10n.investWatchAdded : l10n.investWatchRemoved,
          ),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final detail = ref.watch(investmentDetailProvider(widget.symbol));
    final watching = ref.watch(watchlistProvider).contains(widget.symbol);
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.symbol),
        actions: [
          IconButton(
            tooltip: watching ? l10n.investWatchRemove : l10n.investWatchAdd,
            isSelected: watching,
            icon: const Icon(Icons.star_border_rounded),
            selectedIcon: const Icon(Icons.star_rounded),
            onPressed: () => _toggleWatch(l10n),
          ),
          const DemoBadge(),
          const SizedBox(width: AppSpacing.m),
        ],
      ),
      body: AsyncValueView<InvestmentDetail>(
        value: detail,
        onRetry: () => ref.invalidate(investmentDetailProvider(widget.symbol)),
        data: (d) => ListView(
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          children: [
            _Header(detail: d),
            const SizedBox(height: AppSpacing.m),
            _PriceChart(detail: d),
            const SizedBox(height: AppSpacing.m),
            _SectionChips(
              labels: [
                l10n.investTabFundamentals,
                l10n.investTabIncome,
                l10n.investTabPosition,
                l10n.investTabTransactions,
                l10n.investTabResearch,
              ],
              selected: _section,
              onSelected: (i) => setState(() => _section = i),
            ),
            const SizedBox(height: AppSpacing.s),
            switch (_section) {
              0 => _FundamentalsTab(facts: d.fundamentals),
              1 => _IncomeTab(income: d.income),
              2 => _PositionTab(position: d.position),
              3 => _TransactionsTab(
                symbol: d.symbol,
                onOpen: widget.onOpenTransaction,
              ),
              _ => _ResearchTab(notes: d.research),
            },
            const SizedBox(height: AppSpacing.m),
            Text(
              l10n.investNoTrading,
              style: context.wealthText.caption.copyWith(
                color: context.wealthColors.textMuted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The detail sections as a wrapping group of choice chips (never a sideways scroller, so every
/// section is visible and reachable at any text size).
class _SectionChips extends StatelessWidget {
  const _SectionChips({
    required this.labels,
    required this.selected,
    required this.onSelected,
  });

  final List<String> labels;
  final int selected;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Semantics(
      container: true,
      label: l10n.investTabsLabel,
      child: Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xxs,
        children: [
          for (var i = 0; i < labels.length; i++)
            Semantics(
              container: true,
              inMutuallyExclusiveGroup: true,
              selected: i == selected,
              button: true,
              label: i == selected
                  ? '${labels[i]}, ${l10n.selected}'
                  : labels[i],
              excludeSemantics: true,
              onTap: () => onSelected(i),
              child: ChoiceChip(
                label: Text(labels[i]),
                selected: i == selected,
                showCheckmark: true,
                onSelected: (_) => onSelected(i),
                materialTapTargetSize: MaterialTapTargetSize.padded,
              ),
            ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.detail});

  final InvestmentDetail detail;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(header: true, child: Text(detail.name, style: text.title)),
          Text(
            '${detail.symbol} · ${detail.assetClass}',
            style: text.caption.copyWith(color: colors.textMuted),
          ),
          const SizedBox(height: AppSpacing.s),
          CurrencyAmount(money: detail.price, style: text.displayAmount),
          Text(
            l10n.investPricePerUnit,
            style: text.caption.copyWith(color: colors.textMuted),
          ),
          const SizedBox(height: AppSpacing.xs),
          ChangeIndicator(percent: detail.changePercent),
          const SizedBox(height: AppSpacing.xs),
          Wrap(
            spacing: AppSpacing.s,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              DataAsOfLabel(asOf: detail.priceSource.asOf),
              EvidenceSourceChip(source: detail.priceSource),
            ],
          ),
        ],
      ),
    );
  }
}

class _PriceChart extends ConsumerWidget {
  const _PriceChart({required this.detail});

  final InvestmentDetail detail;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final period = ref.watch(investmentPeriodProvider);
    final key = (symbol: detail.symbol, period: period);
    final series = ref.watch(investmentHistoryProvider(key));
    return WealthCard(
      child: Column(
        children: [
          series.when(
            loading: () => charts.PerformanceLineChart(
              series: charts.ChartSeries(
                id: 'loading',
                label: detail.name,
                currencyCode: detail.currency,
                points: const [],
              ),
              loading: true,
            ),
            error: (_, _) => ErrorState(
              onRetry: () => ref.invalidate(investmentHistoryProvider(key)),
            ),
            data: (data) => charts.PerformanceLineChart(
              series: data.toChartSeries(detail.name),
              rangeLabel: period.spokenLabel(l10n),
            ),
          ),
          const SizedBox(height: AppSpacing.s),
          PeriodSelector(
            periods: investmentPeriods,
            selected: period,
            onChanged: ref.read(investmentPeriodProvider.notifier).select,
          ),
        ],
      ),
    );
  }
}

/// Label and value rows, each read as one phrase.
class _Rows extends StatelessWidget {
  const _Rows(this.rows);

  final List<(String, Widget)> rows;

  @override
  Widget build(BuildContext context) {
    final text = context.wealthText;
    return Column(
      children: [
        for (final (label, value) in rows)
          MergeSemantics(
            child: Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                vertical: AppSpacing.xxs,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    flex: 2,
                    child: Text(
                      label,
                      style: text.caption.copyWith(
                        color: context.wealthColors.textMuted,
                      ),
                    ),
                  ),
                  Expanded(
                    flex: 3,
                    child: Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: value,
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

Widget _plain(BuildContext context, String value) =>
    Text(value, style: context.wealthText.body);

class _Sourced extends StatelessWidget {
  const _Sourced({required this.source});

  final EvidenceSource source;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: AppSpacing.s,
    crossAxisAlignment: WrapCrossAlignment.center,
    children: [
      DataAsOfLabel(asOf: source.asOf),
      EvidenceSourceChip(source: source),
    ],
  );
}

class _Empty extends StatelessWidget {
  const _Empty(this.message);

  final String message;

  @override
  Widget build(BuildContext context) => WealthCard(
    child: Text(
      message,
      style: context.wealthText.body.copyWith(
        color: context.wealthColors.textMuted,
      ),
    ),
  );
}

class _FundamentalsTab extends StatelessWidget {
  const _FundamentalsTab({required this.facts});

  final SourcedFacts facts;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    if (facts.items.isEmpty) return _Empty(l10n.investFundamentalsEmpty);
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Rows([
            for (final f in facts.items) (f.label, _plain(context, f.value)),
          ]),
          const SizedBox(height: AppSpacing.xs),
          _Sourced(source: facts.source),
        ],
      ),
    );
  }
}

class _IncomeTab extends StatelessWidget {
  const _IncomeTab({required this.income});

  final IncomeInfo? income;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final info = income;
    if (info == null) return _Empty(l10n.investIncomeEmpty);
    final locale = context.formatLocale;
    final money = context.moneyFormatter;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Rows([
            (
              l10n.investIncomeYield,
              _plain(
                context,
                context.percentFormatter.format(info.yieldPercent),
              ),
            ),
            (l10n.investIncomeFrequency, _plain(context, info.frequency)),
          ]),
          const SizedBox(height: AppSpacing.s),
          Semantics(
            header: true,
            child: Text(l10n.investIncomeRecent, style: text.label),
          ),
          _Rows([
            for (final e in info.events)
              (
                '${e.kind} · ${DateLabels.date(e.date, locale: locale)}',
                _plain(context, money.format(e.amount)),
              ),
          ]),
          const SizedBox(height: AppSpacing.xs),
          Text(
            l10n.investIncomeNote,
            style: text.caption.copyWith(color: context.wealthColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.xs),
          _Sourced(source: info.source),
        ],
      ),
    );
  }
}

class _PositionTab extends StatelessWidget {
  const _PositionTab({required this.position});

  final PositionInfo position;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final money = context.moneyFormatter;
    final p = position;
    final text = context.wealthText;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Rows([
            (
              l10n.investPositionQuantity,
              _plain(context, p.quantity.toString()),
            ),
            (
              l10n.investPositionAverageCost,
              _plain(
                context,
                money.format(
                  p.averageCost,
                  fractionDigits: p.averageCost.amount.scale > 2 ? 4 : null,
                ),
              ),
            ),
            (
              l10n.investPositionCostBasis,
              _plain(context, money.format(p.costBasis)),
            ),
            (l10n.investPositionValue, _plain(context, money.format(p.value))),
            if (p.nativeValue.currencyCode != p.value.currencyCode)
              (
                l10n.investPositionValueNative(p.nativeValue.currencyCode),
                _plain(context, money.format(p.nativeValue)),
              ),
            (
              l10n.investPositionPl,
              ChangeIndicator(
                percent: p.unrealisedPlPercent,
                amount: p.unrealisedPl,
              ),
            ),
          ]),
          const SizedBox(height: AppSpacing.xs),
          Text(
            l10n.investPositionNote,
            style: text.caption.copyWith(color: context.wealthColors.textMuted),
          ),
          DataAsOfLabel(asOf: p.asOf),
        ],
      ),
    );
  }
}

class _TransactionsTab extends ConsumerWidget {
  const _TransactionsTab({required this.symbol, required this.onOpen});

  final String symbol;
  final void Function(LedgerEntry entry)? onOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final entries = ref.watch(investmentLedgerProvider(symbol));
    return AsyncValueView<List<LedgerEntry>>(
      value: entries,
      onRetry: () => ref.invalidate(investmentLedgerProvider(symbol)),
      isEmpty: (e) => e.isEmpty,
      empty: _Empty(l10n.investTransactionsEmpty),
      data: (all) => WealthCard(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            for (final e in all)
              LedgerEntryTile(
                entry: e,
                onTap: onOpen == null ? null : () => onOpen!(e),
              ),
          ],
        ),
      ),
    );
  }
}

class _ResearchTab extends StatelessWidget {
  const _ResearchTab({required this.notes});

  final List<ResearchNote> notes;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    if (notes.isEmpty) return _Empty(l10n.investResearchEmpty);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final n in notes) ...[
          WealthCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(
                  header: true,
                  child: Text(n.title, style: text.title),
                ),
                const SizedBox(height: AppSpacing.xxs),
                Text(n.summary, style: text.body),
                const SizedBox(height: AppSpacing.xs),
                _Sourced(source: n.source),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.s),
        ],
        Text(
          l10n.investResearchNote,
          style: text.caption.copyWith(color: context.wealthColors.textMuted),
        ),
      ],
    );
  }
}

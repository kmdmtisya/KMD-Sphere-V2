import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/charts/charts.dart' as charts;
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../../shared/domain/chart_mapping.dart';
import '../../alerts/application/alerts_providers.dart';
import '../../alerts/presentation/price_alert_dialog.dart';
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

  void _say(String message) => ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));

  Future<void> _toggleWatch(AppLocalizations l10n) async {
    try {
      final added = await toggleWatch(ref, widget.symbol);
      if (mounted) {
        _say(added ? l10n.investWatchAdded : l10n.investWatchRemoved);
      }
    } on Object {
      if (mounted) _say(l10n.watchUpdateFailed);
    }
  }

  Future<void> _setAlert(AppLocalizations l10n, InvestmentDetail detail) async {
    final created = await showDialog<bool>(
      context: context,
      builder: (_) => PriceAlertDialog(assetKey: widget.symbol, detail: detail),
    );
    if (created == true && mounted) _say(l10n.alertCreated);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final detail = ref.watch(investmentDetailProvider(widget.symbol));
    final watching = ref.watch(isWatchingProvider(widget.symbol)) ?? false;
    return Scaffold(
      appBar: AppBar(
        // The id the screen was opened with is not a name: show the ticker or name once loaded.
        title: Text(
          detail.value == null
              ? ''
              : detail.requireValue.symbol ?? detail.requireValue.name,
        ),
        actions: [
          IconButton(
            tooltip: watching ? l10n.investWatchRemove : l10n.investWatchAdd,
            isSelected: watching,
            icon: const Icon(Icons.star_border_rounded),
            selectedIcon: const Icon(Icons.star_rounded),
            onPressed: () => unawaited(_toggleWatch(l10n)),
          ),
          IconButton(
            tooltip: l10n.alertSetPrice,
            icon: const Icon(Icons.add_alert_outlined),
            onPressed: detail.value == null
                ? null
                : () => unawaited(_setAlert(l10n, detail.requireValue)),
          ),
          const DataSourceBadge(),
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
            _PriceChart(detail: d, assetKey: widget.symbol),
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
              2 => _PositionTab(positions: d.positions),
              3 => _TransactionsTab(
                symbol: widget.symbol,
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
    final price = detail.price;
    final source = detail.priceSource;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(header: true, child: Text(detail.name, style: text.title)),
          Text(
            [?detail.symbol, detail.assetClass].join(' · '),
            style: text.caption.copyWith(color: colors.textMuted),
          ),
          const SizedBox(height: AppSpacing.s),
          if (price == null)
            Text(
              l10n.investNoPriceYet,
              style: text.body.copyWith(color: colors.textMuted),
            )
          else ...[
            CurrencyAmount(money: price, style: text.displayAmount),
            Text(
              l10n.investPricePerUnit,
              style: text.caption.copyWith(color: colors.textMuted),
            ),
          ],
          if (detail.priceStale) ...[
            const SizedBox(height: AppSpacing.xs),
            StaleChip(label: l10n.priceOutOfDate),
          ],
          if (detail.changePercent != null) ...[
            const SizedBox(height: AppSpacing.xs),
            ChangeIndicator(percent: detail.changePercent),
          ],
          if (source != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Wrap(
              spacing: AppSpacing.s,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                DataAsOfLabel(asOf: source.asOf),
                EvidenceSourceChip(source: source),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _PriceChart extends ConsumerWidget {
  const _PriceChart({required this.detail, required this.assetKey});

  final InvestmentDetail detail;

  /// What the screen was opened with (the asset id live, the symbol in DEMO).
  final String assetKey;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final period = ref.watch(investmentPeriodProvider);
    final key = (symbol: assetKey, period: period);
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

  final SourcedFacts? facts;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final facts = this.facts;
    if (facts == null || facts.items.isEmpty) {
      return _Empty(l10n.investFundamentalsEmpty);
    }
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
  const _PositionTab({required this.positions});

  final List<PositionInfo> positions;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    if (positions.isEmpty) return _Empty(l10n.investPositionEmpty);
    return Column(
      children: [
        for (final p in positions) ...[
          _PositionCard(position: p),
          const SizedBox(height: AppSpacing.s),
        ],
      ],
    );
  }
}

class _PositionCard extends StatelessWidget {
  const _PositionCard({required this.position});

  final PositionInfo position;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final money = context.moneyFormatter;
    final p = position;
    final text = context.wealthText;
    final averageCost = p.averageCost;
    final value = p.value;
    final native = p.nativeValue;
    final asOf = p.asOf;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (p.portfolioName != null)
            Semantics(
              header: true,
              child: Text(p.portfolioName!, style: text.label),
            ),
          _Rows([
            (
              l10n.investPositionQuantity,
              _plain(context, p.quantity.toString()),
            ),
            (
              l10n.investPositionAverageCost,
              _plain(
                context,
                averageCost == null
                    ? l10n.valueNotAvailable
                    : money.format(
                        averageCost,
                        fractionDigits: averageCost.amount.scale > 2 ? 4 : null,
                      ),
              ),
            ),
            (
              l10n.investPositionCostBasis,
              _plain(context, money.format(p.costBasis)),
            ),
            (
              l10n.investPositionValue,
              _plain(
                context,
                value == null ? l10n.noValueYet : money.format(value),
              ),
            ),
            if (native != null &&
                value != null &&
                native.currencyCode != value.currencyCode)
              (
                l10n.investPositionValueNative(native.currencyCode),
                _plain(context, money.format(native)),
              ),
            (
              l10n.investPositionPl,
              p.unrealisedPl == null && p.unrealisedPlPercent == null
                  ? _plain(context, l10n.valueNotAvailable)
                  : ChangeIndicator(
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
          if (asOf != null) DataAsOfLabel(asOf: asOf),
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

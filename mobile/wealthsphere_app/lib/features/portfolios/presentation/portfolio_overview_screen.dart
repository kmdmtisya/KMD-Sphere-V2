import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/app_routes.dart';
import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/charts/charts.dart' as charts;
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../../shared/domain/chart_mapping.dart';
import '../../../shared/domain/wealth_models.dart';
import '../application/portfolio_providers.dart';
import 'portfolio_scope_switcher.dart';

/// The Portfolio tab for one portfolio, or all of them combined. Switching the portfolio reloads
/// every section; each section loads, fails and retries on its own.
class PortfolioOverviewScreen extends ConsumerWidget {
  const PortfolioOverviewScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final id = ref.watch(selectedPortfolioIdProvider);
    final holdings = ref.watch(portfolioHoldingsProvider(id));

    return Scaffold(
      appBar: AppBar(
        title: const PortfolioScopeSwitcher(),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => refreshPortfolio(ref),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          children: [
            _SummarySection(id: id),
            const SizedBox(height: AppSpacing.m),
            if (holdings.hasValue && holdings.requireValue.isEmpty)
              const _EmptyPortfolio()
            else ...[
              _AllocationSection(id: id),
              const SizedBox(height: AppSpacing.m),
              _MetricsSection(id: id),
              const SizedBox(height: AppSpacing.m),
              _HoldingsPreview(id: id),
            ],
            const SizedBox(height: AppSpacing.m),
            OutlinedButton.icon(
              onPressed: () => context.go(
                AppRoutes.aiWith(AiScope(AiScopeKind.portfolio, id)),
              ),
              icon: const Icon(Icons.auto_awesome_outlined),
              label: Text(l10n.askAiPortfolio),
            ),
          ],
        ),
      ),
    );
  }
}

/// A percentage from the backend, or "Not available" when it has none.
String _pct(PercentFormatter percents, Decimal? value, AppLocalizations l10n) =>
    value == null ? l10n.valueNotAvailable : percents.format(value);

// ----------------------------------------------------------------------------- summary
class _SummarySection extends ConsumerWidget {
  const _SummarySection({required this.id});

  final String id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final period = ref.watch(portfolioPeriodProvider);
    final summary = ref.watch(portfolioSummaryProvider(id));
    final series = ref.watch(portfolioSeriesProvider((id: id, period: period)));

    return AsyncValueView<PortfolioSummary>(
      value: summary,
      onRetry: () => ref.invalidate(portfolioSummaryProvider(id)),
      data: (s) => WealthSummaryCard(
        label: l10n.homePortfolioValue,
        amount: CurrencyAmount(
          money: s.value,
          style: context.wealthText.displayAmount,
        ),
        change: s.returnPercent == null && s.profitLoss == null
            ? null
            : ChangeIndicator(percent: s.returnPercent, amount: s.profitLoss),
        chart: series.when(
          loading: () => charts.PerformanceLineChart(
            series: charts.ChartSeries(
              id: 'loading',
              label: s.name,
              currencyCode: s.value.currencyCode,
              points: const [],
            ),
            loading: true,
          ),
          error: (_, _) => ErrorState(
            onRetry: () => ref.invalidate(
              portfolioSeriesProvider((id: id, period: period)),
            ),
          ),
          data: (data) => charts.PerformanceLineChart(
            series: data.toChartSeries(s.name),
            rangeLabel: period.spokenLabel(l10n),
          ),
        ),
        periodSelector: PeriodSelector(
          periods: portfolioPeriods,
          selected: period,
          onChanged: ref.read(portfolioPeriodProvider.notifier).select,
        ),
        footer: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DataAsOfLabel(asOf: s.asOf),
            DataQualityNotice(
              complete: s.complete,
              stalePriceCount: s.stalePriceCount,
            ),
          ],
        ),
      ),
    );
  }
}

// -------------------------------------------------------------------------- allocation
class _AllocationSection extends ConsumerWidget {
  const _AllocationSection({required this.id});

  final String id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final allocation = ref.watch(portfolioAllocationProvider(id));
    final summary = ref.watch(portfolioSummaryProvider(id)).value;
    return AsyncValueView<List<AllocationShare>>(
      value: allocation,
      onRetry: () => ref.invalidate(portfolioAllocationProvider(id)),
      isEmpty: (a) => a.isEmpty,
      data: (shares) => WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.allocationTitle, style: context.wealthText.title),
            const SizedBox(height: AppSpacing.s),
            charts.AllocationDonutChart(
              slices: [
                for (final s in shares)
                  charts.AllocationSlice(
                    id: s.label,
                    label: s.label,
                    percent: s.weightPercent,
                  ),
              ],
              centre: summary == null
                  ? null
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          l10n.allocationCentreLabel,
                          style: context.wealthText.caption,
                        ),
                        CurrencyAmount(
                          money: summary.value,
                          compact: true,
                          alignment: Alignment.center,
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

// ----------------------------------------------------------------------------- metrics
class _MetricsSection extends ConsumerWidget {
  const _MetricsSection({required this.id});

  final String id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final percents = context.percentFormatter;
    final metrics = ref.watch(portfolioMetricsProvider(id));
    return AsyncValueView<PerformanceMetrics>(
      value: metrics,
      onRetry: () => ref.invalidate(portfolioMetricsProvider(id)),
      data: (m) {
        Widget card(IconData icon, String label, String def, String value) =>
            MetricCard(
              icon: icon,
              label: label,
              definition: def,
              value: Text(value, style: context.wealthText.amount),
            );
        final cards = [
          card(
            Icons.trending_up_rounded,
            l10n.metricTotalReturn,
            l10n.metricTotalReturnDef,
            _pct(percents, m.totalReturnPercent, l10n),
          ),
          card(
            Icons.timeline_rounded,
            l10n.metricCagr,
            l10n.metricCagrDef,
            _pct(percents, m.cagrPercent, l10n),
          ),
          card(
            Icons.payments_outlined,
            l10n.metricDividendYield,
            l10n.metricDividendYieldDef,
            _pct(percents, m.dividendYieldPercent, l10n),
          ),
          card(
            Icons.show_chart_rounded,
            l10n.metricVolatility,
            l10n.metricVolatilityDef,
            _pct(percents, m.volatilityPercent, l10n),
          ),
        ];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.performanceTitle, style: context.wealthText.title),
            const SizedBox(height: AppSpacing.s),
            LayoutBuilder(
              builder: (context, c) {
                final wide = MediaQuery.textScalerOf(context).scale(1) <= 1.3;
                final width = wide
                    ? (c.maxWidth - AppSpacing.s) / 2
                    : c.maxWidth;
                return Wrap(
                  spacing: AppSpacing.s,
                  runSpacing: AppSpacing.s,
                  children: [
                    for (final card in cards)
                      SizedBox(width: width, child: card),
                  ],
                );
              },
            ),
          ],
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------- holdings
class _HoldingsPreview extends ConsumerWidget {
  const _HoldingsPreview({required this.id});

  final String id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final holdings = ref.watch(portfolioHoldingsProvider(id));
    return AsyncValueView<List<HoldingSummary>>(
      value: holdings,
      onRetry: () => ref.invalidate(portfolioHoldingsProvider(id)),
      isEmpty: (h) => h.isEmpty,
      data: (all) => WealthCard(
        padding: EdgeInsets.zero,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                AppSpacing.m,
                AppSpacing.m,
                AppSpacing.m,
                AppSpacing.xs,
              ),
              child: Text(
                l10n.topHoldingsTitle,
                style: context.wealthText.title,
              ),
            ),
            for (final h in all.take(5))
              InvestmentRow(
                symbol: h.symbol,
                name: h.name,
                value: h.value,
                nativeValue: h.nativeValue,
                changePercent: h.changePercent,
              ),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: Wrap(
                alignment: WrapAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => context.go(AppRoutes.transactions),
                    child: Text(l10n.ledgerOpen),
                  ),
                  TextButton(
                    onPressed: () => context.go(AppRoutes.holdings),
                    child: Text(l10n.viewAllHoldings),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ------------------------------------------------------------------------------- empty
class _EmptyPortfolio extends StatelessWidget {
  const _EmptyPortfolio();

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Column(
      children: [
        EmptyState(
          title: l10n.noInvestmentsTitle,
          message: l10n.noInvestmentsMessage,
          icon: Icons.pie_chart_outline_rounded,
        ),
        Tooltip(
          message: l10n.demoNotConnected,
          // Adding investments arrives with the portfolio core (P05); disabled in demo mode.
          child: const FilledButton(onPressed: null, child: _AddLabel()),
        ),
      ],
    );
  }
}

class _AddLabel extends StatelessWidget {
  const _AddLabel();

  @override
  Widget build(BuildContext context) =>
      Text(AppLocalizations.of(context).addInvestment);
}

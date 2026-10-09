import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../app/app_routes.dart';
import '../../../../core/data/demo_support.dart';
import '../../../../l10n/generated/app_localizations.dart';
import '../../../../shared/design_system/charts/charts.dart' as charts;
import '../../../../shared/design_system/components/components.dart';
import '../../../../shared/design_system/formatting/formatting.dart';
import '../../../../shared/design_system/theme/theme.dart';
import '../../../../shared/design_system/tokens/tokens.dart';
import '../../../forecast/domain/forecast_models.dart';
import '../../application/calculator_providers.dart';
import '../calculator_screen.dart' show frequencyLabel;

String scenarioName(AppLocalizations l10n, ForecastScenarioKind k) =>
    switch (k) {
      ForecastScenarioKind.conservative => l10n.scenarioConservative,
      ForecastScenarioKind.base => l10n.scenarioBase,
      ForecastScenarioKind.growth => l10n.scenarioGrowth,
    };

/// The id used in the AI scope for "the forecast on screen". Real forecasts get an id from the
/// backend at gate 4.
const String currentForecastScopeId = 'current';

/// Wealth Forecast. Every number on this screen is a field of the backend's
/// [CompoundForecastResponse]: nothing is projected, inflated or summed in the app.
class ForecastScreen extends ConsumerStatefulWidget {
  const ForecastScreen({super.key});

  @override
  ConsumerState<ForecastScreen> createState() => _ForecastScreenState();
}

class _ForecastScreenState extends ConsumerState<ForecastScreen> {
  ForecastScenarioKind _selected = ForecastScenarioKind.base;
  bool _real = false;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final result = ref.watch(forecastResultProvider);
    final demo = ref.watch(dataSourceModeProvider) == DataSourceMode.demo;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.forecastTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: result == null
          ? EmptyState(
              title: l10n.forecastNoResultTitle,
              message: l10n.forecastNoResultMessage,
              icon: Icons.insights_outlined,
              actionLabel: l10n.openCalculator,
              onAction: () => context.go(AppRoutes.calculator),
            )
          : _Body(
              result: result,
              selected: _selected,
              real: _real,
              showDemoMismatch:
                  demo && !result.response.matches(result.request),
              onSelect: (k) => setState(() => _selected = k),
              onReal: (v) => setState(() => _real = v),
            ),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({
    required this.result,
    required this.selected,
    required this.real,
    required this.showDemoMismatch,
    required this.onSelect,
    required this.onReal,
  });

  final ForecastResult result;
  final ForecastScenarioKind selected;
  final bool real;
  final bool showDemoMismatch;
  final ValueChanged<ForecastScenarioKind> onSelect;
  final ValueChanged<bool> onReal;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final response = result.response;
    final assumptions = response.assumptions;
    final chosen = response.scenarios[selected]!;
    final finalValue = real ? chosen.finalReal : chosen.finalNominal;
    final years = l10n.yearsCount(assumptions.years);

    return ListView(
      padding: const EdgeInsetsDirectional.all(AppSpacing.m),
      children: [
        if (showDemoMismatch) ...[
          StatusBanner(
            icon: Icons.science_outlined,
            message: l10n.forecastDemoMismatch,
          ),
          const SizedBox(height: AppSpacing.m),
        ],
        Text(l10n.forecastScenariosTitle, style: text.title),
        const SizedBox(height: AppSpacing.s),
        for (final kind in ForecastScenarioKind.values) ...[
          ScenarioCard(
            key: ValueKey('scenario-${kind.name}'),
            name: scenarioName(l10n, kind),
            annualReturnPercent: response.scenarios[kind]!.annualReturnPercent,
            finalValue: real
                ? response.scenarios[kind]!.finalReal
                : response.scenarios[kind]!.finalNominal,
            selected: kind == selected,
            onSelected: () => onSelect(kind),
          ),
          const SizedBox(height: AppSpacing.s),
        ],
        const SizedBox(height: AppSpacing.s),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: Semantics(
            label: l10n.forecastValuesLabel,
            container: true,
            child: SegmentedButton<bool>(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(value: false, label: Text(l10n.forecastNominal)),
                ButtonSegment(value: true, label: Text(l10n.forecastReal)),
              ],
              selected: {real},
              onSelectionChanged: (s) => onReal(s.first),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.m),
        WealthCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                l10n.forecastFinalValue(years),
                style: text.label.copyWith(
                  color: context.wealthColors.textMuted,
                ),
              ),
              CurrencyAmount(
                key: const ValueKey('final-value'),
                money: finalValue,
                style: text.displayAmount,
              ),
              const SizedBox(height: AppSpacing.m),
              Text(l10n.forecastChartTitle, style: text.title),
              const SizedBox(height: AppSpacing.s),
              charts.ForecastComparisonChart(
                selectedId: selected.name,
                series: [
                  for (final kind in ForecastScenarioKind.values)
                    charts.ForecastSeries(
                      id: kind.name,
                      label: scenarioName(l10n, kind),
                      currencyCode: response.currencyCode,
                      points: [
                        for (final p
                            in real
                                ? response.scenarios[kind]!.real
                                : response.scenarios[kind]!.nominal)
                          charts.ForecastPoint(p.year, p.value),
                      ],
                    ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.m),
        _Breakdown(scenario: chosen),
        const SizedBox(height: AppSpacing.m),
        _Assumptions(assumptions: assumptions, notice: response.notice),
        const SizedBox(height: AppSpacing.m),
        FilledButton.tonalIcon(
          onPressed: () => context.canPop()
              ? context.pop()
              : context.go(AppRoutes.calculator),
          icon: const Icon(Icons.tune_rounded),
          label: Text(l10n.editAssumptions),
        ),
        const SizedBox(height: AppSpacing.xs),
        OutlinedButton.icon(
          onPressed: () => context.go(
            AppRoutes.aiWith(
              const AiScope(AiScopeKind.forecast, currentForecastScopeId),
            ),
          ),
          icon: const Icon(Icons.auto_awesome_outlined),
          label: Text(l10n.askAiForecast),
        ),
      ],
    );
  }
}

/// Contributions vs growth, as a stacked bar **and** as text (never colour alone). Both amounts
/// come from the response; the bar widths are only a drawing of their sizes.
class _Breakdown extends StatelessWidget {
  const _Breakdown({required this.scenario});

  final ScenarioResult scenario;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final text = context.wealthText;
    final money = context.moneyFormatter;
    final contributions = scenario.totalContributions;
    final growth = scenario.totalGrowth;
    // Drawing proportions only (flex factors), not financial values.
    final c = contributions.amount.toDouble().clamp(0, double.infinity);
    final g = growth.amount.toDouble().clamp(0, double.infinity);
    final total = c + g;
    final cFlex = total == 0 ? 1 : ((c / total) * 1000).round().clamp(1, 999);

    Widget legend(Color color, String label, Money value) => Padding(
      padding: const EdgeInsetsDirectional.only(top: AppSpacing.xs),
      child: Row(
        children: [
          Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(3),
            ),
          ),
          const SizedBox(width: AppSpacing.xs),
          Expanded(child: Text(label, style: text.body)),
          Flexible(
            child: CurrencyAmount(
              money: value,
              alignment: AlignmentDirectional.centerEnd,
            ),
          ),
        ],
      ),
    );

    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.forecastBreakdownTitle, style: text.title),
          const SizedBox(height: AppSpacing.s),
          Semantics(
            container: true,
            label: l10n.forecastBreakdownSpoken(
              money.format(contributions),
              money.format(growth),
            ),
            excludeSemantics: true,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppRadii.small),
              child: SizedBox(
                height: 16,
                child: Row(
                  children: [
                    Expanded(
                      flex: cFlex,
                      child: ColoredBox(color: colors.chartContributions),
                    ),
                    Expanded(
                      flex: 1000 - cFlex,
                      child: ColoredBox(color: colors.chartGrowth),
                    ),
                  ],
                ),
              ),
            ),
          ),
          legend(
            colors.chartContributions,
            l10n.forecastContributions,
            contributions,
          ),
          legend(colors.chartGrowth, l10n.forecastGrowth, growth),
          const SizedBox(height: AppSpacing.xxs),
          Text(
            l10n.forecastBreakdownNominalNote,
            style: text.caption.copyWith(color: colors.textMuted),
          ),
        ],
      ),
    );
  }
}

/// Every assumption the backend used, echoed back. The summary ("not guaranteed") is always
/// visible; the details expand.
class _Assumptions extends StatelessWidget {
  const _Assumptions({required this.assumptions, required this.notice});

  final CompoundForecastRequest assumptions;
  final String notice;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final money = context.moneyFormatter;
    final percent = context.percentFormatter;
    final text = context.wealthText;
    final a = assumptions;
    String pct(Decimal d) => percent.format(d);
    final rows = <(String, String)>[
      (l10n.calcInitialInvestment, money.format(a.initialInvestment)),
      (l10n.calcMonthlyContribution, money.format(a.monthlyContribution)),
      (l10n.assumptionYears, l10n.yearsCount(a.years)),
      (
        l10n.assumptionReturns,
        l10n.assumptionReturnsValue(
          pct(a.conservativeReturnPercent),
          pct(a.annualReturnPercent),
          pct(a.growthReturnPercent),
        ),
      ),
      (l10n.calcContributionGrowth, pct(a.contributionGrowthPercent)),
      (l10n.calcInflation, pct(a.inflationPercent)),
      (l10n.calcFee, pct(a.annualFeePercent)),
      (l10n.calcCompounding, frequencyLabel(l10n, a.compoundingFrequency)),
      (
        l10n.calcContributionFrequency,
        frequencyLabel(l10n, a.contributionFrequency),
      ),
    ];
    return DisclosurePanel(
      title: l10n.forecastAssumptionsTitle,
      summary: l10n.forecastAssumptionsSummary,
      icon: Icons.info_outline_rounded,
      details: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (label, value) in rows)
            Padding(
              padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: text.caption),
                  Text(value, style: text.body),
                ],
              ),
            ),
          const SizedBox(height: AppSpacing.xs),
          Text(notice, style: text.caption),
        ],
      ),
    );
  }
}

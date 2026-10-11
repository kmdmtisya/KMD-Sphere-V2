import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../l10n/generated/app_localizations.dart';
import '../../../../shared/design_system/components/components.dart';
import '../../../../shared/design_system/theme/theme.dart';
import '../../../../shared/design_system/tokens/tokens.dart';
import '../../../portfolios/application/portfolio_providers.dart';
import '../../../portfolios/presentation/portfolio_scope_switcher.dart';
import '../application/doctor_providers.dart';
import '../domain/doctor_models.dart';

/// Screen 12: the Portfolio Doctor. An overview of what the deterministic checks found (each
/// finding with its severity in words and an explanation), a closer look by type with the figures
/// behind each finding, and what-if scenarios that illustrate it.
///
/// It describes and illustrates only: there is no Buy, Sell or rebalance action anywhere.
class DoctorScreen extends ConsumerWidget {
  const DoctorScreen({this.onAskAi, super.key});

  /// Opens AI Wealth for the portfolio being checked. Null hides the button.
  final void Function(String portfolioId)? onAskAi;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final id = ref.watch(selectedPortfolioIdProvider);
    final report = ref.watch(doctorReportProvider(id));
    final filter = ref.watch(doctorKindFilterProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.doctorTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(doctorReportProvider(id)),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          children: [
            const Align(
              alignment: AlignmentDirectional.centerStart,
              child: PortfolioScopeSwitcher(),
            ),
            const SizedBox(height: AppSpacing.m),
            AsyncValueView<DoctorReport>(
              value: report,
              onRetry: () => ref.invalidate(doctorReportProvider(id)),
              data: (r) {
                final kinds = r.kinds;
                final active = kinds.contains(filter) ? filter : null;
                final shown = [
                  for (final f in r.findings)
                    if (active == null || f.kind == active) f,
                ];
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    PortfolioHealthCard(
                      findings: [for (final f in r.findings) f.toView()],
                      asOf: r.asOf,
                    ),
                    if (r.findings.isNotEmpty) ...[
                      const SizedBox(height: AppSpacing.l),
                      Semantics(
                        header: true,
                        child: Text(
                          l10n.doctorLookCloser,
                          style: context.wealthText.title,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      _KindChips(
                        report: r,
                        selected: active,
                        onSelected: ref
                            .read(doctorKindFilterProvider.notifier)
                            .select,
                      ),
                      const SizedBox(height: AppSpacing.s),
                      for (final f in shown) ...[
                        _FindingDetail(finding: f, report: r),
                        const SizedBox(height: AppSpacing.s),
                      ],
                    ],
                  ],
                );
              },
            ),
            const SizedBox(height: AppSpacing.s),
            if (onAskAi != null)
              OutlinedButton.icon(
                onPressed: () => onAskAi!(id),
                icon: const Icon(Icons.auto_awesome_outlined),
                label: Text(l10n.doctorAskAi),
              ),
            const SizedBox(height: AppSpacing.s),
            Text(
              l10n.doctorNoTrades,
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

class _KindChips extends StatelessWidget {
  const _KindChips({
    required this.report,
    required this.selected,
    required this.onSelected,
  });

  final DoctorReport report;
  final HealthFindingKind? selected;
  final ValueChanged<HealthFindingKind?> onSelected;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    Widget chip(String label, bool isSelected, VoidCallback onTap) => Semantics(
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

    return Semantics(
      container: true,
      label: l10n.doctorFilterGroup,
      child: Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xxs,
        children: [
          chip(
            l10n.doctorFilterCount(
              l10n.doctorFilterAll,
              report.findings.length,
            ),
            selected == null,
            () => onSelected(null),
          ),
          for (final k in report.kinds)
            chip(
              l10n.doctorFilterCount(
                PortfolioHealthCard.kindLabel(l10n, k),
                report.findings.where((f) => f.kind == k).length,
              ),
              selected == k,
              () => onSelected(k),
            ),
        ],
      ),
    );
  }
}

class _FindingDetail extends StatelessWidget {
  const _FindingDetail({required this.finding, required this.report});

  final DoctorFinding finding;
  final DoctorReport report;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final scenarios = [
      for (final id in finding.scenarioIds) ?report.scenario(id),
    ];
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: AppSpacing.xs,
            runSpacing: AppSpacing.xxs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                PortfolioHealthCard.kindLabel(l10n, finding.kind),
                style: text.caption.copyWith(color: colors.textMuted),
              ),
              RiskLabel(level: finding.severity),
            ],
          ),
          const SizedBox(height: AppSpacing.xxs),
          Semantics(
            header: true,
            child: Text(finding.title, style: text.title),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(l10n.doctorFactsHeading, style: text.label),
          for (final fact in finding.facts)
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
                        fact.label,
                        style: text.caption.copyWith(color: colors.textMuted),
                      ),
                    ),
                    Expanded(
                      flex: 3,
                      child: Text(fact.value, style: text.body),
                    ),
                  ],
                ),
              ),
            ),
          if (scenarios.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(l10n.doctorScenarioHeading, style: text.label),
            const SizedBox(height: AppSpacing.xxs),
            for (final s in scenarios)
              Padding(
                padding: const EdgeInsetsDirectional.only(
                  bottom: AppSpacing.xxs,
                ),
                child: OutlinedButton(
                  onPressed: () => _openScenario(context, s),
                  child: Text(s.title, textAlign: TextAlign.center),
                ),
              ),
          ],
        ],
      ),
    );
  }

  void _openScenario(BuildContext context, DoctorScenario scenario) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => _ScenarioSheet(scenario: scenario),
    );
  }
}

class _ScenarioSheet extends StatelessWidget {
  const _ScenarioSheet({required this.scenario});

  final DoctorScenario scenario;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final muted = text.caption.copyWith(color: context.wealthColors.textMuted);
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsetsDirectional.fromSTEB(
          AppSpacing.m,
          0,
          AppSpacing.m,
          AppSpacing.m,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Align(
              alignment: AlignmentDirectional.centerEnd,
              child: DemoBadge(),
            ),
            Semantics(
              header: true,
              child: Text(scenario.title, style: text.title),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(scenario.description, style: text.body),
            const SizedBox(height: AppSpacing.s),
            Semantics(
              header: true,
              child: Text(l10n.doctorScenarioAssumptions, style: text.label),
            ),
            for (final a in scenario.assumptions)
              Padding(
                padding: const EdgeInsetsDirectional.only(top: AppSpacing.xxs),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('• '),
                    Expanded(child: Text(a, style: text.body)),
                  ],
                ),
              ),
            const SizedBox(height: AppSpacing.s),
            Semantics(
              header: true,
              child: Text(l10n.doctorScenarioEffect, style: text.label),
            ),
            Text(scenario.effect, style: text.body),
            const SizedBox(height: AppSpacing.s),
            Text(l10n.doctorScenarioNote, style: muted),
            const SizedBox(height: AppSpacing.m),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(l10n.doctorScenarioClose),
            ),
          ],
        ),
      ),
    );
  }
}

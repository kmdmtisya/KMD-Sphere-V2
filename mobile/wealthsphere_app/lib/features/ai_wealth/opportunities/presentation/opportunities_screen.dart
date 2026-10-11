import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../l10n/generated/app_localizations.dart';
import '../../../../shared/design_system/components/components.dart';
import '../../../../shared/design_system/theme/theme.dart';
import '../../../../shared/design_system/tokens/tokens.dart';
import '../application/opportunity_providers.dart';
import '../domain/opportunity_models.dart';

/// Screen 13: research ideas from AI Investment Intelligence, in DEMO.
///
/// Every idea is a place to start looking, never a recommendation: it shows its risk, its
/// evidence with provider and as-of time, and how its score is made. The whole screen says the
/// data is mock, not live. The actions only navigate (research sheet, comparison, calculator);
/// nothing here places a trade.
class OpportunitiesScreen extends ConsumerWidget {
  const OpportunitiesScreen({this.onCompare, this.onSimulated, super.key});

  /// Opens the comparison of the ideas chosen. Null hides the compare bar.
  final VoidCallback? onCompare;

  /// Called after an idea's example assumptions were handed to the calculator (open it).
  final VoidCallback? onSimulated;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final list = ref.watch(opportunitiesProvider);
    final selection = ref.watch(compareSelectionProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.oppTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      bottomNavigationBar: selection.isEmpty || onCompare == null
          ? null
          : _CompareBar(selected: selection.length, onCompare: onCompare!),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(opportunitiesProvider),
        child: AsyncValueView<OpportunityList>(
          value: list,
          onRetry: () => ref.invalidate(opportunitiesProvider),
          data: (data) =>
              _Body(data: data, selection: selection, onSimulated: onSimulated),
        ),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  const _Body({
    required this.data,
    required this.selection,
    required this.onSimulated,
  });

  final OpportunityList data;
  final List<String> selection;
  final VoidCallback? onSimulated;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final filter = ref.watch(opportunityCategoryProvider);
    final active = data.categories.any((c) => c.id == filter) ? filter : null;
    final shown = inCategory(data, active);
    final categoryLabel = data.categories
        .where((c) => c.id == active)
        .map((c) => c.label)
        .firstOrNull;
    final summary = [
      l10n.oppCount(shown.length),
      if (categoryLabel != null) l10n.oppInCategory(categoryLabel),
    ].join(', ');

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsetsDirectional.all(AppSpacing.m),
      children: [
        // The backend's own statement that these ideas are mock data.
        StatusBanner(icon: Icons.science_outlined, message: data.notice),
        const SizedBox(height: AppSpacing.m),
        _CategoryChips(
          categories: data.categories,
          selected: active,
          onSelected: ref.read(opportunityCategoryProvider.notifier).select,
        ),
        const SizedBox(height: AppSpacing.xs),
        // A live region: a change of category is read out by screen readers.
        Semantics(
          liveRegion: true,
          label: summary,
          excludeSemantics: true,
          child: Text(summary, style: text.caption),
        ),
        const SizedBox(height: AppSpacing.s),
        if (shown.isEmpty)
          EmptyState(
            icon: Icons.search_off_rounded,
            title: l10n.oppEmptyTitle,
            message: l10n.oppEmptyMessage,
            actionLabel: l10n.oppShowAll,
            onAction: () =>
                ref.read(opportunityCategoryProvider.notifier).select(null),
          )
        else
          for (final c in shown) ...[
            _Candidate(
              candidate: c,
              chosen: selection.contains(c.id),
              onSimulated: onSimulated,
            ),
            const SizedBox(height: AppSpacing.m),
          ],
        Text(
          l10n.oppNoTrades,
          style: text.caption.copyWith(color: context.wealthColors.textMuted),
        ),
      ],
    );
  }
}

class _CategoryChips extends StatelessWidget {
  const _CategoryChips({
    required this.categories,
    required this.selected,
    required this.onSelected,
  });

  final List<OpportunityCategory> categories;
  final String? selected;
  final ValueChanged<String?> onSelected;

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
      label: l10n.oppFilterGroup,
      child: Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xxs,
        children: [
          chip(l10n.oppFilterAll, selected == null, () => onSelected(null)),
          for (final c in categories)
            chip(c.label, selected == c.id, () => onSelected(c.id)),
        ],
      ),
    );
  }
}

class _Candidate extends ConsumerWidget {
  const _Candidate({
    required this.candidate,
    required this.chosen,
    required this.onSimulated,
  });

  final OpportunityCandidate candidate;
  final bool chosen;
  final VoidCallback? onSimulated;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final c = candidate;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        OpportunityCard(
          name: c.name,
          symbol: c.symbol,
          assetClass: c.assetClass,
          summary: c.summary,
          risk: c.risk,
          evidence: c.evidence,
          asOf: c.asOf,
          score: c.score,
          scoreExplanation: c.score == null
              ? null
              : _ScoreExplanation(factors: c.scoreFactors),
          risks: c.risks,
          isDemo: true,
          onResearch: () => _openResearch(context, c),
          onCompare: () {
            final ok = ref.read(compareSelectionProvider.notifier).toggle(c.id);
            if (!ok) {
              ScaffoldMessenger.of(context)
                ..hideCurrentSnackBar()
                ..showSnackBar(
                  SnackBar(content: Text(l10n.oppCompareLimit(maxCompare))),
                );
            }
          },
          onSimulate: c.simulation == null
              ? null
              : () {
                  final locale = Localizations.localeOf(context).toString();
                  if (simulateInCalculator(ref, c, locale)) {
                    onSimulated?.call();
                  }
                },
        ),
        if (chosen)
          Padding(
            padding: const EdgeInsetsDirectional.only(top: AppSpacing.xxs),
            child: Row(
              children: [
                const Icon(Icons.check_circle_outline_rounded, size: 18),
                const SizedBox(width: AppSpacing.xxs),
                Expanded(
                  child: Text(
                    l10n.oppInComparison,
                    style: context.wealthText.label,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  void _openResearch(BuildContext context, OpportunityCandidate c) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => ResearchSheet(candidate: c),
    );
  }
}

/// How the score is made: the five factors, their points and what each measures.
class _ScoreExplanation extends StatelessWidget {
  const _ScoreExplanation({required this.factors});

  final List<ScoreFactor> factors;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(l10n.oppScoreIntro, style: text.body),
        for (final f in factors)
          Padding(
            padding: const EdgeInsetsDirectional.only(top: AppSpacing.xxs),
            child: Text(
              l10n.oppScoreFactor(f.label, f.points, f.max, f.note),
              style: text.caption,
            ),
          ),
      ],
    );
  }
}

/// The research sheet for one idea: what it is, what to check, its evidence and its risks.
class ResearchSheet extends StatelessWidget {
  const ResearchSheet({required this.candidate, super.key});

  final OpportunityCandidate candidate;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final c = candidate;
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
            Text(l10n.oppResearchTitle, style: text.caption),
            Semantics(
              header: true,
              child: Text('${c.symbol} · ${c.name}', style: text.title),
            ),
            const SizedBox(height: AppSpacing.xs),
            RiskLabel(level: c.risk),
            const SizedBox(height: AppSpacing.s),
            Text(c.summary, style: text.body),
            for (final section in c.research) ...[
              const SizedBox(height: AppSpacing.s),
              Semantics(
                header: true,
                child: Text(section.heading, style: text.label),
              ),
              Text(section.text, style: text.body),
            ],
            const SizedBox(height: AppSpacing.s),
            Text(l10n.opportunityRisksTitle, style: text.label),
            for (final r in c.risks)
              Padding(
                padding: const EdgeInsetsDirectional.only(top: AppSpacing.xxs),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('• ', style: text.body),
                    Expanded(child: Text(r, style: text.body)),
                  ],
                ),
              ),
            const SizedBox(height: AppSpacing.s),
            Text(l10n.opportunityEvidenceTitle, style: text.label),
            const SizedBox(height: AppSpacing.xxs),
            if (c.evidence.isEmpty)
              Text(
                l10n.opportunityNoEvidence,
                style: text.body.copyWith(color: colors.warningText),
              )
            else
              Wrap(
                spacing: AppSpacing.xs,
                runSpacing: AppSpacing.xs,
                children: [
                  for (final e in c.evidence) EvidenceSourceChip(source: e),
                ],
              ),
            const SizedBox(height: AppSpacing.s),
            DataAsOfLabel(asOf: c.asOf),
            const SizedBox(height: AppSpacing.xxs),
            Text(
              l10n.opportunityNotAdvice,
              style: text.caption.copyWith(color: colors.textMuted),
            ),
            const SizedBox(height: AppSpacing.m),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(l10n.oppResearchClose),
            ),
          ],
        ),
      ),
    );
  }
}

class _CompareBar extends ConsumerWidget {
  const _CompareBar({required this.selected, required this.onCompare});

  final int selected;
  final VoidCallback onCompare;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(top: BorderSide(color: colors.divider)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsetsDirectional.all(AppSpacing.s),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              FilledButton(
                onPressed: selected >= 2 ? onCompare : null,
                child: Text(l10n.oppCompareBar(selected)),
              ),
              if (selected < 2)
                Padding(
                  padding: const EdgeInsetsDirectional.only(
                    top: AppSpacing.xxs,
                  ),
                  child: Text(
                    l10n.oppCompareNeedTwo,
                    style: context.wealthText.caption,
                  ),
                ),
              TextButton(
                onPressed: ref.read(compareSelectionProvider.notifier).clear,
                child: Text(l10n.oppCompareClear),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

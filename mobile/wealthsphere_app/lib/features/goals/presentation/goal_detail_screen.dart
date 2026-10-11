import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../portfolios/application/portfolio_providers.dart';
import '../application/goal_providers.dart';
import '../domain/goal_models.dart';
import 'goal_labels.dart';

/// One goal: where it stands, the contribution it would take, the three scenarios and the
/// assumptions behind all of it. Every figure is the backend's and every status is an estimate.
class GoalDetailScreen extends ConsumerWidget {
  const GoalDetailScreen({
    required this.goalId,
    this.onEdit,
    this.onAskAi,
    super.key,
  });

  final String goalId;

  /// Opens the edit form. Null hides the button.
  final void Function(Goal goal)? onEdit;

  /// Opens AI Wealth with this goal as the context. Null hides the button.
  final void Function(Goal goal)? onAskAi;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final entry = ref.watch(goalProvider(goalId));
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.goalDetailTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: AsyncValueView<GoalEntry>(
        value: entry,
        onRetry: () => ref.invalidate(goalProvider(goalId)),
        data: (e) => ListView(
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          children: [
            _Summary(entry: e),
            const SizedBox(height: AppSpacing.m),
            _Required(entry: e),
            if (e.figures != null) ...[
              const SizedBox(height: AppSpacing.m),
              _Scenarios(goal: e.goal, figures: e.figures!),
            ],
            const SizedBox(height: AppSpacing.m),
            _Assumptions(goal: e.goal),
            if (e.figures != null) ...[
              const SizedBox(height: AppSpacing.m),
              Text(
                e.figures!.notice,
                style: context.wealthText.caption.copyWith(
                  color: context.wealthColors.textMuted,
                ),
              ),
            ],
            const SizedBox(height: AppSpacing.m),
            if (onEdit != null)
              FilledButton.tonalIcon(
                onPressed: () => onEdit!(e.goal),
                icon: const Icon(Icons.edit_outlined),
                label: Text(l10n.goalDetailEdit),
              ),
            if (onAskAi != null)
              TextButton.icon(
                onPressed: () => onAskAi!(e.goal),
                icon: const Icon(Icons.auto_awesome_outlined),
                label: Text(l10n.goalAskAi),
              ),
          ],
        ),
      ),
    );
  }
}

Widget _plain(BuildContext context, String value) =>
    Text(value, style: context.wealthText.body);

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

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.xs),
    child: Semantics(
      header: true,
      child: Text(text, style: context.wealthText.title),
    ),
  );
}

class _Summary extends StatelessWidget {
  const _Summary({required this.entry});

  final GoalEntry entry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final goal = entry.goal;
    final f = entry.figures;
    final money = context.moneyFormatter;
    final locale = context.formatLocale;
    if (f == null) {
      return WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              header: true,
              child: Text(goal.name, style: context.wealthText.title),
            ),
            Text(
              l10n.goalCardTarget(
                money.format(goal.target),
                DateLabels.date(goal.targetDate, locale: locale),
              ),
              style: context.wealthText.body,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              l10n.goalsPendingNote,
              style: context.wealthText.caption.copyWith(
                color: context.wealthColors.textMuted,
              ),
            ),
          ],
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GoalProgressCard(
          name: goal.name,
          progressPercent: f.progressPercent,
          status: f.status,
          target: goal.target,
          targetDate: goal.targetDate,
          current: f.currentValue,
        ),
        if (!f.valueComplete) ...[
          const SizedBox(height: AppSpacing.s),
          StatusBanner(
            icon: Icons.info_outline_rounded,
            message: l10n.goalValueIncomplete,
          ),
        ],
        const SizedBox(height: AppSpacing.s),
        WealthCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Rows([
                (
                  l10n.goalFigCurrent,
                  _plain(context, money.format(f.currentValue)),
                ),
                (l10n.goalFigGap, _plain(context, money.format(f.gap))),
                (
                  l10n.goalFigTimeLeft,
                  _plain(
                    context,
                    f.overdue
                        ? l10n.goalOverdue
                        : l10n.goalMonths(f.monthsLeft.clamp(0, 1 << 30)),
                  ),
                ),
                (
                  l10n.goalFigEstimatedCompletion,
                  _plain(
                    context,
                    f.estimatedCompletion == null
                        ? l10n.goalEstimatedNone
                        : DateLabels.date(
                            f.estimatedCompletion!,
                            locale: locale,
                          ),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.xs),
              DataAsOfLabel(asOf: f.valueAsOf),
            ],
          ),
        ),
      ],
    );
  }
}

class _Required extends StatelessWidget {
  const _Required({required this.entry});

  final GoalEntry entry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final muted = text.caption.copyWith(color: context.wealthColors.textMuted);
    final money = context.moneyFormatter;
    final f = entry.figures;
    final a = entry.goal.assumptions;
    final period = goalPeriodLabel(l10n, a.contributionFrequency);

    final String headline;
    final String? explain;
    if (f == null) {
      headline = l10n.goalRequiredPending;
      explain = null;
    } else if (f.requiredContribution != null) {
      headline = l10n.goalRequiredValue(
        money.format(f.requiredContribution!),
        period,
      );
      explain = l10n.goalRequiredExplain;
    } else if (f.status == GoalProgressStatus.reached) {
      headline = l10n.goalRequiredReached;
      explain = null;
    } else {
      headline = l10n.goalRequiredUnavailable;
      explain = null;
    }

    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Heading(l10n.goalRequiredTitle),
          Text(
            headline,
            style: f?.requiredContribution != null
                ? text.displayAmount
                : text.body,
          ),
          if (explain != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(explain, style: muted),
          ],
          const SizedBox(height: AppSpacing.xs),
          Text(
            l10n.goalYourContribution(money.format(a.contribution), period),
            style: muted,
          ),
        ],
      ),
    );
  }
}

class _Scenarios extends StatelessWidget {
  const _Scenarios({required this.goal, required this.figures});

  final Goal goal;
  final GoalFigures figures;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final money = context.moneyFormatter;
    final percents = context.percentFormatter;
    final text = context.wealthText;
    final colors = context.wealthColors;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Heading(l10n.goalScenariosTitle),
          for (final s in figures.scenarios)
            MergeSemantics(
              child: Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  vertical: AppSpacing.xxs,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      s.reachesTarget
                          ? Icons.check_circle_outline_rounded
                          : Icons.remove_circle_outline_rounded,
                      size: 20,
                      color: s.reachesTarget
                          ? colors.positiveText
                          : colors.warningText,
                    ),
                    const SizedBox(width: AppSpacing.xs),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${scenarioLabel(l10n, s.kind)}: '
                            '${s.reachesTarget ? l10n.goalScenarioReaches : l10n.goalScenarioMisses}',
                            style: text.label,
                          ),
                          Text(
                            l10n.goalScenarioLine(
                              percents.format(s.annualReturnPercent),
                              money.format(s.projectedValue),
                            ),
                            style: text.caption.copyWith(
                              color: colors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            l10n.goalScenariosNote,
            style: text.caption.copyWith(color: colors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _Assumptions extends ConsumerWidget {
  const _Assumptions({required this.goal});

  final Goal goal;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final a = goal.assumptions;
    final money = context.moneyFormatter;
    final percents = context.percentFormatter;
    String pct(Decimal v) => percents.format(v);
    final portfolios = ref.watch(portfolioListProvider).value ?? const [];
    final fundedBy = goal.portfolioId == null
        ? l10n.goalFundedAll
        : portfolios
                  .where((p) => p.id == goal.portfolioId)
                  .map((p) => p.name)
                  .firstOrNull ??
              goal.portfolioId!;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Heading(l10n.goalAssumptionsTitle),
          _Rows([
            (l10n.goalFundedBy, _plain(context, fundedBy)),
            (
              l10n.goalAssumpContribution,
              _plain(
                context,
                l10n.goalRequiredValue(
                  money.format(a.contribution),
                  goalPeriodLabel(l10n, a.contributionFrequency),
                ),
              ),
            ),
            (
              l10n.goalAssumpContributionGrowth,
              _plain(context, pct(a.contributionGrowthPercent)),
            ),
            (l10n.goalAssumpBase, _plain(context, pct(a.baseReturnPercent))),
            if (a.conservativeReturnPercent != null)
              (
                l10n.goalAssumpConservative,
                _plain(context, pct(a.conservativeReturnPercent!)),
              ),
            if (a.growthReturnPercent != null)
              (
                l10n.goalAssumpGrowthReturn,
                _plain(context, pct(a.growthReturnPercent!)),
              ),
            (
              l10n.goalAssumpInflation,
              _plain(context, pct(a.inflationPercent)),
            ),
            (l10n.goalAssumpFee, _plain(context, pct(a.annualFeePercent))),
            (
              l10n.goalAssumpTodaysMoney,
              _plain(
                context,
                goal.targetInTodaysMoney ? l10n.goalYes : l10n.goalNo,
              ),
            ),
          ]),
        ],
      ),
    );
  }
}

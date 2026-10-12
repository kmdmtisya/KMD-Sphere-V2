import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/goal_providers.dart';
import '../domain/goal_models.dart';

/// Screen 11 (the Goals tab): a card per goal with its progress ring, target and date, and a
/// status that is always worded as an estimate. Figures are the backend's.
class GoalsScreen extends ConsumerWidget {
  const GoalsScreen({this.onOpen, this.onAdd, super.key});

  /// Called with the goal the user taps. Null leaves the cards inert.
  final void Function(GoalEntry entry)? onOpen;

  /// Called when the user asks to add a goal. Null hides the button.
  final VoidCallback? onAdd;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final goals = ref.watch(goalsProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.tabGoals),
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
              label: Text(l10n.goalsAdd),
            ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(goalsProvider),
        child: AsyncValueView<List<GoalEntry>>(
          value: goals,
          onRetry: () => ref.invalidate(goalsProvider),
          isEmpty: (g) => g.isEmpty,
          empty: EmptyState(
            title: l10n.goalsEmptyTitle,
            message: l10n.goalsEmptyMessage,
            icon: Icons.flag_outlined,
            actionLabel: onAdd == null ? null : l10n.goalsAdd,
            onAction: onAdd,
          ),
          data: (all) {
            final withFigures = [
              for (final e in all)
                if (e.figures != null) e,
            ];
            final onTrack = withFigures
                .where((e) => e.figures!.status != GoalProgressStatus.behind)
                .length;
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsetsDirectional.only(
                top: AppSpacing.m,
                bottom: 96,
                start: AppSpacing.m,
                end: AppSpacing.m,
              ),
              children: [
                if (withFigures.isNotEmpty) ...[
                  Semantics(
                    liveRegion: true,
                    child: Text(
                      l10n.goalsSummary(onTrack, withFigures.length),
                      style: context.wealthText.title,
                    ),
                  ),
                  Text(
                    // The server's own wording for what the statuses rest on.
                    withFigures.first.figures!.notice,
                    style: context.wealthText.caption.copyWith(
                      color: context.wealthColors.textMuted,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.m),
                ],
                for (final e in all) ...[
                  _GoalCard(
                    entry: e,
                    onTap: onOpen == null ? null : () => onOpen!(e),
                  ),
                  const SizedBox(height: AppSpacing.s),
                ],
              ],
            );
          },
        ),
      ),
    );
  }
}

class _GoalCard extends StatelessWidget {
  const _GoalCard({required this.entry, required this.onTap});

  final GoalEntry entry;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final goal = entry.goal;
    final figures = entry.figures;
    if (figures != null) {
      return GoalProgressCard(
        name: goal.name,
        progressPercent: figures.progressPercent,
        status: figures.status,
        target: goal.target,
        targetDate: goal.targetDate,
        current: figures.currentValue,
        onTap: onTap,
      );
    }
    // No figures from the server: show the goal as it was set, and say plainly why there is no
    // estimate. Never fill the gap with a number.
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    return WealthCard(
      onTap: onTap,
      semanticLabel: [
        goal.name,
        l10n.goalCardTarget(
          context.moneyFormatter.format(goal.target),
          DateLabels.date(goal.targetDate, locale: context.formatLocale),
        ),
        l10n.goalsPendingNote,
      ].join(', '),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(goal.name, style: text.title),
          Text(
            l10n.goalCardTarget(
              context.moneyFormatter.format(goal.target),
              DateLabels.date(goal.targetDate, locale: context.formatLocale),
            ),
            style: text.body,
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.hourglass_empty_rounded, size: 20),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  l10n.goalsPendingNote,
                  style: text.caption.copyWith(
                    color: context.wealthColors.textMuted,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

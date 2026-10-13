import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../l10n/generated/app_localizations.dart';
import '../../../../shared/design_system/components/components.dart';
import '../../../../shared/design_system/theme/theme.dart';
import '../../../../shared/design_system/tokens/tokens.dart';
import '../application/opportunity_providers.dart';
import '../domain/opportunity_models.dart';

/// Compares the ideas chosen side by side: risk, score and the facts on file. It lays the facts
/// out; it never ranks the ideas or says which to pick.
class CompareScreen extends ConsumerWidget {
  const CompareScreen({this.onBack, super.key});

  /// Returns to the ideas list.
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final list = ref.watch(opportunitiesProvider);
    final selection = ref.watch(compareSelectionProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.oppCompareTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: AsyncValueView<OpportunityList>(
        value: list,
        onRetry: () => ref.invalidate(opportunitiesProvider),
        data: (data) {
          final chosen = [for (final id in selection) ?data.byId(id)];
          if (chosen.length < 2) {
            return EmptyState(
              icon: Icons.compare_arrows_rounded,
              title: l10n.oppCompareNeedTwo,
              actionLabel: onBack == null ? null : l10n.oppCompareBack,
              onAction: onBack,
            );
          }
          final facts = ref.watch(
            comparisonProvider([for (final c in chosen) c.id].join(',')),
          );
          return AsyncValueView<Map<String, List<OpportunityAttribute>>>(
            value: facts,
            onRetry: () => ref.invalidate(comparisonProvider),
            data: (byId) => _Table(candidates: chosen, attributes: byId),
          );
        },
      ),
    );
  }
}

class _Table extends StatelessWidget {
  const _Table({required this.candidates, required this.attributes});

  final List<OpportunityCandidate> candidates;

  /// The facts on file for each idea, by id (from the server in live mode).
  final Map<String, List<OpportunityAttribute>> attributes;

  String? _value(OpportunityCandidate c, String label) => attributes[c.id]
      ?.where((a) => a.label == label)
      .map((a) => a.value)
      .firstOrNull;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;

    // The attribute labels in the order of the first idea, then any others.
    final labels = <String>[];
    for (final c in candidates) {
      for (final a in attributes[c.id] ?? const <OpportunityAttribute>[]) {
        if (!labels.contains(a.label)) labels.add(a.label);
      }
    }

    Widget section(String heading, List<Widget> lines) => WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(header: true, child: Text(heading, style: text.title)),
          const SizedBox(height: AppSpacing.xs),
          ...lines,
        ],
      ),
    );

    Widget line(OpportunityCandidate c, String value) => MergeSemantics(
      child: Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          vertical: AppSpacing.xxs,
        ),
        child: Text(l10n.oppCompareValueLine(c.name, value), style: text.body),
      ),
    );

    return ListView(
      padding: const EdgeInsetsDirectional.all(AppSpacing.m),
      children: [
        Text(
          l10n.oppCompareNote,
          style: text.caption.copyWith(color: colors.textMuted),
        ),
        const SizedBox(height: AppSpacing.s),
        section(l10n.oppCompareRisk, [
          for (final c in candidates)
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                vertical: AppSpacing.xxs,
              ),
              child: Wrap(
                spacing: AppSpacing.xs,
                runSpacing: AppSpacing.xxs,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text('${c.name}:', style: text.body),
                  RiskLabel(level: c.risk),
                ],
              ),
            ),
        ]),
        const SizedBox(height: AppSpacing.s),
        section(l10n.oppCompareScore, [
          for (final c in candidates)
            line(
              c,
              c.score == null
                  ? l10n.oppCompareNoScore
                  : l10n.opportunityScore('${c.score}'),
            ),
        ]),
        for (final label in labels) ...[
          const SizedBox(height: AppSpacing.s),
          section(label, [
            for (final c in candidates) line(c, _value(c, label) ?? '-'),
          ]),
        ],
        const SizedBox(height: AppSpacing.s),
        Text(
          l10n.opportunityNotAdvice,
          style: text.caption.copyWith(color: colors.textMuted),
        ),
        Text(
          l10n.oppNoTrades,
          style: text.caption.copyWith(color: colors.textMuted),
        ),
      ],
    );
  }
}

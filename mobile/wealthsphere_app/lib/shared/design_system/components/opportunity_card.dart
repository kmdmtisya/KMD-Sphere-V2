import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'cards.dart';
import 'data_as_of_label.dart';
import 'demo_badge.dart';
import 'disclosure_panel.dart';
import 'evidence_source_chip.dart';
import 'risk_label.dart';

/// A research candidate from the AI Investment Intelligence feature: a place to start looking,
/// never a recommendation.
///
/// Every card carries its **risk**, its **evidence** (each source with provider and as-of time),
/// the **data-as-of** time and, when it has a score, an **explanation of the score**. A card
/// without evidence says so plainly and warns not to rely on it. The "not advice, returns never
/// guaranteed" wording is part of the card. DEMO cards say DEMO, so a mock idea is never taken for
/// a live one. The actions (research, compare, simulate) only navigate; nothing here trades.
class OpportunityCard extends StatelessWidget {
  const OpportunityCard({
    required this.name,
    required this.risk,
    required this.evidence,
    required this.asOf,
    this.symbol,
    this.assetClass,
    this.summary,
    this.score,
    this.scoreExplanation,
    this.risks = const [],
    this.isDemo = false,
    this.now,
    this.onResearch,
    this.onCompare,
    this.onSimulate,
    super.key,
  }) : assert(
         score == null || scoreExplanation != null,
         'A score needs an explanation of how it is made',
       ),
       assert(
         score == null || (score >= 0 && score <= 100),
         'The research score is between 0 and 100',
       );

  final String name;
  final String? symbol;

  /// The asset class as ready-made text ("Equity ETF").
  final String? assetClass;
  final String? summary;
  final RiskLevel risk;
  final List<EvidenceSource> evidence;
  final DateTime asOf;

  /// A whole-number research score (0 to 100) from the backend's transparent scoring.
  final int? score;
  final Widget? scoreExplanation;

  /// Risks and assumptions, as short statements.
  final List<String> risks;
  final bool isDemo;
  final DateTime? now;
  final VoidCallback? onResearch;
  final VoidCallback? onCompare;
  final VoidCallback? onSimulate;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final riskWord = switch (risk) {
      RiskLevel.low => l10n.riskLow,
      RiskLevel.medium => l10n.riskMedium,
      RiskLevel.high => l10n.riskHigh,
    };
    final title = symbol == null ? name : '$symbol · $name';
    final scoreText = score == null ? null : l10n.opportunityScore('$score');

    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            container: true,
            label: [
              l10n.opportunityCandidate,
              title,
              ?assetClass,
              riskWord,
              ?scoreText,
              if (isDemo) l10n.demoBadgeSpoken,
            ].join(', '),
            excludeSemantics: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xxs,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      l10n.opportunityCandidate,
                      style: text.caption.copyWith(color: colors.textMuted),
                    ),
                    if (isDemo) const DemoBadge(),
                  ],
                ),
                const SizedBox(height: AppSpacing.xxs),
                Text(title, style: text.title),
                if (assetClass != null)
                  Text(
                    assetClass!,
                    style: text.caption.copyWith(color: colors.textMuted),
                  ),
                const SizedBox(height: AppSpacing.xs),
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xxs,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    RiskLabel(level: risk),
                    if (scoreText != null) Text(scoreText, style: text.label),
                  ],
                ),
                if (summary != null) ...[
                  const SizedBox(height: AppSpacing.xs),
                  Text(summary!, style: text.body),
                ],
              ],
            ),
          ),
          if (score != null) ...[
            const SizedBox(height: AppSpacing.xs),
            DisclosurePanel(
              title: l10n.opportunityScoreWhy,
              summary: scoreText!,
              details: scoreExplanation!,
            ),
          ],
          if (risks.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.s),
            Text(l10n.opportunityRisksTitle, style: text.label),
            for (final r in risks)
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
          ],
          const SizedBox(height: AppSpacing.s),
          Text(l10n.opportunityEvidenceTitle, style: text.label),
          const SizedBox(height: AppSpacing.xxs),
          if (evidence.isEmpty)
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.warning_amber_rounded,
                  size: 18,
                  color: colors.warningText,
                ),
                const SizedBox(width: AppSpacing.xxs),
                Expanded(
                  child: Text(
                    l10n.opportunityNoEvidence,
                    style: text.body.copyWith(color: colors.warningText),
                  ),
                ),
              ],
            )
          else
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: [
                for (final source in evidence)
                  EvidenceSourceChip(source: source, now: now),
              ],
            ),
          const SizedBox(height: AppSpacing.s),
          DataAsOfLabel(asOf: asOf, now: now),
          const SizedBox(height: AppSpacing.xxs),
          Text(
            l10n.opportunityNotAdvice,
            style: text.caption.copyWith(color: colors.textMuted),
          ),
          if (onResearch != null ||
              onCompare != null ||
              onSimulate != null) ...[
            const SizedBox(height: AppSpacing.s),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: [
                if (onResearch != null)
                  FilledButton.tonal(
                    onPressed: onResearch,
                    child: Text(l10n.opportunityResearch),
                  ),
                if (onCompare != null)
                  OutlinedButton(
                    onPressed: onCompare,
                    child: Text(l10n.opportunityCompare),
                  ),
                if (onSimulate != null)
                  OutlinedButton(
                    onPressed: onSimulate,
                    child: Text(l10n.opportunitySimulate),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

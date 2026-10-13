import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'cards.dart';
import 'data_as_of_label.dart';
import 'risk_label.dart';

enum HealthFindingKind {
  concentration,
  currency,
  liquidity,
  volatility,
  income,
  goals,
  data,
}

/// One observation about a portfolio: what kind it is, how serious, and why. The explanation is
/// plain text from the backend's deterministic checks (never a recommendation).
class HealthFinding {
  const HealthFinding({
    required this.kind,
    required this.severity,
    required this.title,
    required this.explanation,
  });

  final HealthFindingKind kind;

  /// How much the finding matters (low, medium or high), shown with [RiskLabel].
  final RiskLevel severity;
  final String title;
  final String explanation;
}

/// The Portfolio Doctor's overview: how many findings there are and each one with its severity
/// (an icon **and** a word) and explanation. It states that these are observations from the
/// user's own data and not advice, and when the data was valid.
///
/// With no findings it says the checks that could be run flagged nothing, which is not a claim
/// that the portfolio is healthy.
class PortfolioHealthCard extends StatelessWidget {
  const PortfolioHealthCard({
    required this.findings,
    this.asOf,
    this.now,
    this.onTap,
    super.key,
  });

  final List<HealthFinding> findings;

  /// When the underlying data was valid.
  final DateTime? asOf;
  final DateTime? now;
  final VoidCallback? onTap;

  static IconData _icon(HealthFindingKind kind) => switch (kind) {
    HealthFindingKind.concentration => Icons.pie_chart_outline_rounded,
    HealthFindingKind.currency => Icons.currency_exchange_rounded,
    HealthFindingKind.liquidity => Icons.water_drop_outlined,
    HealthFindingKind.volatility => Icons.show_chart_rounded,
    HealthFindingKind.income => Icons.payments_outlined,
    HealthFindingKind.goals => Icons.flag_outlined,
    HealthFindingKind.data => Icons.dataset_outlined,
  };

  static String kindLabel(AppLocalizations l10n, HealthFindingKind kind) =>
      switch (kind) {
        HealthFindingKind.concentration => l10n.healthKindConcentration,
        HealthFindingKind.currency => l10n.healthKindCurrency,
        HealthFindingKind.liquidity => l10n.healthKindLiquidity,
        HealthFindingKind.volatility => l10n.healthKindVolatility,
        HealthFindingKind.income => l10n.healthKindIncome,
        HealthFindingKind.goals => l10n.healthKindGoals,
        HealthFindingKind.data => l10n.healthKindData,
      };

  static String _severity(AppLocalizations l10n, RiskLevel level) =>
      switch (level) {
        RiskLevel.low => l10n.riskLow,
        RiskLevel.medium => l10n.riskMedium,
        RiskLevel.high => l10n.riskHigh,
      };

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final count = l10n.healthFindingsCount(findings.length);
    final spoken = [
      '${l10n.healthTitle}, $count',
      for (final f in findings)
        l10n.healthFindingSpoken(
          kindLabel(l10n, f.kind),
          _severity(l10n, f.severity),
          f.title,
          f.explanation,
        ),
      l10n.healthNote,
    ].join('. ');

    return WealthCard(
      onTap: onTap,
      semanticLabel: spoken,
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: AppSpacing.s,
              runSpacing: AppSpacing.xxs,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(l10n.healthTitle, style: text.title),
                Text(
                  count,
                  style: text.label.copyWith(color: colors.textMuted),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.s),
            if (findings.isEmpty)
              Text(l10n.healthNoFindings, style: text.body)
            else
              for (var i = 0; i < findings.length; i++) ...[
                if (i > 0) const Divider(height: AppSpacing.l),
                _FindingRow(finding: findings[i]),
              ],
            const SizedBox(height: AppSpacing.s),
            Text(
              l10n.healthNote,
              style: text.caption.copyWith(color: colors.textMuted),
            ),
            if (asOf != null) ...[
              const SizedBox(height: AppSpacing.xxs),
              DataAsOfLabel(asOf: asOf!, now: now),
            ],
          ],
        ),
      ),
    );
  }
}

class _FindingRow extends StatelessWidget {
  const _FindingRow({required this.finding});

  final HealthFinding finding;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          PortfolioHealthCard._icon(finding.kind),
          size: 20,
          color: colors.textMuted,
        ),
        const SizedBox(width: AppSpacing.s),
        Expanded(
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
              Text(finding.title, style: text.title),
              Text(finding.explanation, style: text.body),
            ],
          ),
        ),
      ],
    );
  }
}

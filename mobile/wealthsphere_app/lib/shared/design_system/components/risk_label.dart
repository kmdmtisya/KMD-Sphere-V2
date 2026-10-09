import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';

enum RiskLevel { low, medium, high }

/// A risk level shown as an icon **and** a word ("Low risk"), never colour alone. Each level has
/// a different icon shape so the three are distinguishable without colour.
///
/// The level always comes from an authorised, evidence-backed service; this widget only displays
/// it. It makes no recommendation.
class RiskLabel extends StatelessWidget {
  const RiskLabel({required this.level, super.key});

  final RiskLevel level;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final (label, icon, color) = switch (level) {
      RiskLevel.low => (l10n.riskLow, Icons.shield_outlined, colors.riskLow),
      RiskLevel.medium => (
        l10n.riskMedium,
        Icons.warning_amber_rounded,
        colors.riskMedium,
      ),
      RiskLevel.high => (
        l10n.riskHigh,
        Icons.error_outline_rounded,
        colors.riskHigh,
      ),
    };
    return Semantics(
      label: label,
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: AppRadii.smallRadius,
          border: Border.all(color: colors.border),
        ),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: AppSpacing.xs,
            vertical: AppSpacing.xxs,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 16, color: color),
              const SizedBox(width: AppSpacing.xxs),
              Flexible(
                child: Text(
                  label,
                  style: context.wealthText.caption.copyWith(color: color),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';

/// "DEMO" marker for any screen that shows fixture data. Demo content must never be mistaken for
/// the user's real accounts or for live market data.
class DemoBadge extends StatelessWidget {
  const DemoBadge({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    return Semantics(
      label: l10n.demoBadgeSpoken,
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: colors.demoBadge,
          borderRadius: AppRadii.smallRadius,
        ),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: AppSpacing.xs,
            vertical: AppSpacing.xxs,
          ),
          child: Text(
            l10n.demoBadge,
            style: context.wealthText.caption.copyWith(
              color: colors.onDemoBadge,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.8,
            ),
          ),
        ),
      ),
    );
  }
}

/// Full-width notice explaining that the data on screen is a demonstration.
class DemoBanner extends StatelessWidget {
  const DemoBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    return Semantics(
      container: true,
      label: l10n.demoBannerText,
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(color: colors.demoBadge),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: AppSpacing.m,
            vertical: AppSpacing.xs,
          ),
          child: Row(
            children: [
              Icon(Icons.science_outlined, size: 18, color: colors.onDemoBadge),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  l10n.demoBannerText,
                  style: context.wealthText.caption.copyWith(
                    color: colors.onDemoBadge,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'context_locale.dart';
import 'data_as_of_label.dart';

/// A banner with an icon, a message and an optional action. Announced to screen readers when it
/// appears (live region). Meaning is carried by icon and text, never by colour alone.
class StatusBanner extends StatelessWidget {
  const StatusBanner({
    required this.icon,
    required this.message,
    this.actionLabel,
    this.onAction,
    super.key,
  });

  final IconData icon;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    return Semantics(
      container: true,
      liveRegion: true,
      child: DecoratedBox(
        decoration: BoxDecoration(color: colors.staleBanner),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: AppSpacing.m,
            vertical: AppSpacing.xs,
          ),
          child: Row(
            children: [
              Icon(icon, size: 20, color: colors.onStaleBanner),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  message,
                  style: context.wealthText.caption.copyWith(
                    color: colors.onStaleBanner,
                  ),
                ),
              ),
              if (actionLabel != null && onAction != null)
                TextButton(
                  onPressed: onAction,
                  style: TextButton.styleFrom(
                    foregroundColor: colors.onStaleBanner,
                  ),
                  child: Text(actionLabel!),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// "These figures may be out of date." with the age of the data when known.
class StaleDataBanner extends StatelessWidget {
  const StaleDataBanner({this.asOf, this.now, this.onRetry, super.key});

  final DateTime? asOf;
  final DateTime? now;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final age = asOf == null
        ? null
        : dataAsOfText(
            l10n,
            asOf!,
            now: now ?? DateTime.now(),
            locale: context.formatLocale,
          );
    return StatusBanner(
      icon: Icons.schedule_rounded,
      message: age == null
          ? l10n.staleBannerText
          : l10n.staleBannerWithAge(age),
      actionLabel: onRetry == null ? null : l10n.retry,
      onAction: onRetry,
    );
  }
}

/// Shown when there is no connection and saved data is displayed.
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({this.onRetry, super.key});

  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return StatusBanner(
      icon: Icons.wifi_off_rounded,
      message: l10n.offlineBannerText,
      actionLabel: onRetry == null ? null : l10n.retry,
      onAction: onRetry,
    );
  }
}

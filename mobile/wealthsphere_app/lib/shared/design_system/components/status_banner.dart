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

  /// Icon, message and optional action. With large text the action drops below the message so a
  /// long label never pushes the row past the screen edge.
  Widget _layout(BuildContext context, WealthColors colors) {
    final hasAction = actionLabel != null && onAction != null;
    final stacked = MediaQuery.textScalerOf(context).scale(1) > 1.3;
    final action = hasAction
        ? TextButton(
            onPressed: onAction,
            style: TextButton.styleFrom(foregroundColor: colors.onStaleBanner),
            child: Text(actionLabel!),
          )
        : null;
    final message = Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 20, color: colors.onStaleBanner),
        const SizedBox(width: AppSpacing.xs),
        Expanded(
          child: Text(
            this.message,
            style: context.wealthText.caption.copyWith(
              color: colors.onStaleBanner,
            ),
          ),
        ),
        if (!stacked && action != null) action,
      ],
    );
    if (!stacked || action == null) return message;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        message,
        Align(alignment: AlignmentDirectional.centerEnd, child: action),
      ],
    );
  }

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
          child: _layout(context, colors),
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

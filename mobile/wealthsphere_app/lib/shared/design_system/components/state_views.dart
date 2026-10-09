import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';

class _StateLayout extends StatelessWidget {
  const _StateLayout({
    required this.icon,
    required this.iconColor,
    required this.title,
    this.message,
    this.action,
  });

  final IconData icon;
  final Color iconColor;
  final String title;
  final String? message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final text = context.wealthText;
    return Center(
      child: Padding(
        padding: const EdgeInsetsDirectional.all(AppSpacing.l),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: AppBreakpoints.maxContentWidth,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 48, color: iconColor),
              const SizedBox(height: AppSpacing.m),
              Text(title, style: text.headline, textAlign: TextAlign.center),
              if (message != null) ...[
                const SizedBox(height: AppSpacing.xs),
                Text(message!, style: text.body, textAlign: TextAlign.center),
              ],
              if (action != null) ...[
                const SizedBox(height: AppSpacing.l),
                action!,
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// "Nothing here yet": an icon, a title, an optional explanation and an optional action.
class EmptyState extends StatelessWidget {
  const EmptyState({
    this.title,
    this.message,
    this.icon = Icons.inbox_outlined,
    this.actionLabel,
    this.onAction,
    super.key,
  });

  final String? title;
  final String? message;
  final IconData icon;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Semantics(
      container: true,
      child: _StateLayout(
        icon: icon,
        iconColor: context.wealthColors.textMuted,
        title: title ?? l10n.emptyDefaultTitle,
        message: message,
        action: actionLabel != null && onAction != null
            ? FilledButton(onPressed: onAction, child: Text(actionLabel!))
            : null,
      ),
    );
  }
}

/// A failed load with a clear message and a Retry button. Never shows raw exception text.
class ErrorState extends StatelessWidget {
  const ErrorState({this.title, this.message, this.onRetry, super.key});

  final String? title;
  final String? message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Semantics(
      container: true,
      liveRegion: true,
      child: _StateLayout(
        icon: Icons.error_outline_rounded,
        iconColor: context.wealthColors.negativeText,
        title: title ?? l10n.errorGenericTitle,
        message: message ?? l10n.errorGenericMessage,
        action: onRetry == null
            ? null
            : OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded),
                label: Text(l10n.retry),
              ),
      ),
    );
  }
}

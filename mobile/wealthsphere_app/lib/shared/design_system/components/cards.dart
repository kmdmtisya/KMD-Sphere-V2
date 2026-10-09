import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';

/// The shared card surface: themed colour, radius and border, with an optional ripple.
class WealthCard extends StatelessWidget {
  const WealthCard({
    required this.child,
    this.onTap,
    this.padding = const EdgeInsetsDirectional.all(AppSpacing.m),
    this.selected = false,
    this.semanticLabel,
    super.key,
  });

  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsetsGeometry padding;

  /// Draws the emphasised border. Callers must also show a non-colour cue (icon or text).
  final bool selected;

  /// When set, the whole card is read as one element with this label.
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    Widget card = Material(
      color: colors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadii.mediumRadius,
        side: BorderSide(
          color: selected ? colors.primary : colors.divider,
          width: selected ? 2 : 1,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: BoxConstraints(
            minHeight: onTap == null ? 0 : AppTouchTarget.android,
          ),
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
    if (semanticLabel != null) {
      card = Semantics(
        container: true,
        button: onTap != null,
        label: semanticLabel,
        excludeSemantics: true,
        onTap: onTap,
        child: card,
      );
    }
    return card;
  }
}

/// Hero card: a label, the headline amount, the change, and optional period and chart slots.
/// It takes ready-made widgets (no data fetching) so each screen decides where numbers come from.
class WealthSummaryCard extends StatelessWidget {
  const WealthSummaryCard({
    required this.label,
    required this.amount,
    this.change,
    this.periodSelector,
    this.chart,
    this.footer,
    super.key,
  });

  final String label;

  /// Usually a `CurrencyAmount` with the display-amount style.
  final Widget amount;

  /// Usually a `ChangeIndicator`.
  final Widget? change;
  final Widget? periodSelector;
  final Widget? chart;

  /// Usually a `DataAsOfLabel`.
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    final text = context.wealthText;
    final colors = context.wealthColors;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: text.label.copyWith(color: colors.textMuted)),
          const SizedBox(height: AppSpacing.xxs),
          amount,
          if (change != null) ...[
            const SizedBox(height: AppSpacing.xxs),
            change!,
          ],
          if (chart != null) ...[const SizedBox(height: AppSpacing.m), chart!],
          if (periodSelector != null) ...[
            const SizedBox(height: AppSpacing.s),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: periodSelector!,
            ),
          ],
          if (footer != null) ...[
            const SizedBox(height: AppSpacing.s),
            footer!,
          ],
        ],
      ),
    );
  }
}

/// A compact figure with a label: icon, label, value, optional sub-value and change.
/// Tappable when [onTap] is given. [definition] adds an info button that shows a tooltip.
class MetricCard extends StatelessWidget {
  const MetricCard({
    required this.icon,
    required this.label,
    required this.value,
    this.subValue,
    this.change,
    this.definition,
    this.onTap,
    super.key,
  });

  final IconData icon;
  final String label;

  /// Usually a `CurrencyAmount`.
  final Widget value;
  final String? subValue;
  final Widget? change;

  /// Plain-language definition of the metric.
  final String? definition;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    return WealthCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(icon, size: 20, color: colors.textMuted),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  label,
                  style: text.label.copyWith(color: colors.textMuted),
                ),
              ),
              if (definition != null)
                Semantics(
                  container: true,
                  button: true,
                  label: l10n.metricInfo(label),
                  excludeSemantics: true,
                  child: Tooltip(
                    message: definition,
                    triggerMode: TooltipTriggerMode.tap,
                    excludeFromSemantics: true,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(
                        minWidth: AppTouchTarget.android,
                        minHeight: AppTouchTarget.android,
                      ),
                      child: Icon(
                        Icons.info_outline_rounded,
                        size: 20,
                        color: colors.textMuted,
                      ),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.xxs),
          value,
          if (subValue != null)
            Padding(
              padding: const EdgeInsetsDirectional.only(top: AppSpacing.xxs),
              child: Text(
                subValue!,
                style: text.caption.copyWith(color: colors.textMuted),
              ),
            ),
          if (change != null)
            Padding(
              padding: const EdgeInsetsDirectional.only(top: AppSpacing.xxs),
              child: change,
            ),
        ],
      ),
    );
  }
}

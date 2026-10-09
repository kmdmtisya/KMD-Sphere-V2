import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';

/// An expandable panel for assumptions, definitions and disclaimers. The [summary] is **always**
/// visible, even collapsed, so a forecast's "not guaranteed" statement can never be hidden; the
/// [details] expand on demand.
///
/// Accessible: the header is a 48 dp button announced as expanded/collapsed, the chevron changes
/// with state, and the animation is removed when the platform asks for reduced motion.
class DisclosurePanel extends StatefulWidget {
  const DisclosurePanel({
    required this.title,
    required this.summary,
    required this.details,
    this.initiallyExpanded = false,
    this.icon = Icons.info_outline_rounded,
    super.key,
  });

  final String title;

  /// Always-visible one- or two-line statement.
  final String summary;

  /// Shown when expanded.
  final Widget details;

  final bool initiallyExpanded;
  final IconData icon;

  @override
  State<DisclosurePanel> createState() => _DisclosurePanelState();
}

class _DisclosurePanelState extends State<DisclosurePanel> {
  late bool _expanded = widget.initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final text = context.wealthText;
    final hint = _expanded ? l10n.disclosureHide : l10n.disclosureShow;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: AppRadii.mediumRadius,
        border: Border.all(color: colors.divider),
      ),
      child: Padding(
        padding: const EdgeInsetsDirectional.all(AppSpacing.m),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Semantics(
              button: true,
              expanded: _expanded,
              label: widget.title,
              hint: hint,
              excludeSemantics: true,
              onTap: _toggle,
              child: InkWell(
                onTap: _toggle,
                borderRadius: AppRadii.smallRadius,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    minHeight: AppTouchTarget.android,
                  ),
                  child: Row(
                    children: [
                      Icon(widget.icon, color: colors.textMuted),
                      const SizedBox(width: AppSpacing.xs),
                      Expanded(child: Text(widget.title, style: text.title)),
                      Icon(
                        _expanded
                            ? Icons.expand_less_rounded
                            : Icons.expand_more_rounded,
                        color: colors.textMuted,
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.xxs),
            Text(widget.summary, style: text.body),
            AnimatedSize(
              duration: AppMotion.resolve(context, AppMotion.standard),
              curve: AppMotion.curve,
              alignment: AlignmentDirectional.topStart,
              child: _expanded
                  ? Padding(
                      padding: const EdgeInsetsDirectional.only(
                        top: AppSpacing.s,
                      ),
                      child: DefaultTextStyle.merge(
                        style: text.body,
                        child: widget.details,
                      ),
                    )
                  : const SizedBox(width: double.infinity),
            ),
          ],
        ),
      ),
    );
  }

  void _toggle() => setState(() => _expanded = !_expanded);
}

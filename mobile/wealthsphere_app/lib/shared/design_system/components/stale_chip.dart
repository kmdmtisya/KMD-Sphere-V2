import 'package:flutter/material.dart';

import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';

/// A small "out of date" label for a figure older than its freshness window. Colour is never the
/// only signal: it carries an icon and text, and reads as one phrase.
class StaleChip extends StatelessWidget {
  const StaleChip({required this.label, super.key});

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    return Semantics(
      container: true,
      label: label,
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.schedule_rounded, size: 16, color: colors.warningText),
          const SizedBox(width: AppSpacing.xxs),
          Flexible(
            child: Text(
              label,
              style: context.wealthText.caption.copyWith(
                color: colors.warningText,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

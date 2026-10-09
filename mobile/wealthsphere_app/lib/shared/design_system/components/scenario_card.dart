import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'cards.dart';
import 'context_locale.dart';
import 'currency_amount.dart';

/// A selectable what-if scenario (Conservative / Base / Growth).
///
/// Selection is shown by a thicker border **and** a check icon **and** the word "Selected" for
/// screen readers, and the group is exposed as mutually exclusive (radio semantics). The rate is an
/// assumption supplied by the backend, never a promised return, and is worded that way.
class ScenarioCard extends StatelessWidget {
  const ScenarioCard({
    required this.name,
    required this.annualReturnPercent,
    required this.finalValue,
    required this.selected,
    required this.onSelected,
    super.key,
  });

  final String name;

  /// Assumed annual return, in percentage points (7 means 7%).
  final Decimal annualReturnPercent;
  final Money finalValue;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final rate = l10n.scenarioRate(
      context.percentFormatter.format(annualReturnPercent, fractionDigits: 1),
    );
    final value = context.moneyFormatter.format(finalValue);
    final spoken = [
      name,
      rate,
      '${l10n.scenarioProjected} $value',
      if (selected) l10n.selected,
    ].join(', ');

    return Semantics(
      container: true,
      inMutuallyExclusiveGroup: true,
      checked: selected,
      label: spoken,
      excludeSemantics: true,
      onTap: onSelected,
      child: WealthCard(
        selected: selected,
        onTap: onSelected,
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: text.title),
                  Text(
                    rate,
                    style: text.caption.copyWith(color: colors.textMuted),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    l10n.scenarioProjected,
                    style: text.caption.copyWith(color: colors.textMuted),
                  ),
                  CurrencyAmount(money: finalValue, compact: true),
                ],
              ),
            ),
            if (selected)
              Icon(Icons.check_circle_rounded, color: colors.primary),
          ],
        ),
      ),
    );
  }
}

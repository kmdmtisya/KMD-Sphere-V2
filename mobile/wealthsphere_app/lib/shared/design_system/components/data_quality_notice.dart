import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';

/// Says when a total is not the whole picture: some assets have no price or could not be
/// converted ([complete] is false), or some prices are older than their freshness window.
/// Renders nothing when the figures are complete and current.
class DataQualityNotice extends StatelessWidget {
  const DataQualityNotice({
    required this.complete,
    this.stalePriceCount = 0,
    super.key,
  });

  final bool complete;
  final int stalePriceCount;

  @override
  Widget build(BuildContext context) {
    if (complete && stalePriceCount == 0) return const SizedBox.shrink();
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final messages = [
      if (!complete) l10n.incompleteTotalsNotice,
      if (stalePriceCount > 0) l10n.stalePricesNotice(stalePriceCount),
    ];
    return Padding(
      padding: const EdgeInsetsDirectional.only(top: AppSpacing.xs),
      child: Semantics(
        container: true,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ExcludeSemantics(
              child: Icon(
                Icons.info_outline_rounded,
                size: 16,
                color: colors.textMuted,
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text(
                messages.join(' '),
                style: context.wealthText.caption.copyWith(
                  color: colors.textMuted,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../tokens/tokens.dart';

/// The time ranges a chart can show. Each screen passes the subset it supports.
enum ChartPeriod {
  week,
  month,
  threeMonths,
  sixMonths,
  yearToDate,
  year,
  all;

  String shortLabel(AppLocalizations l10n) => switch (this) {
    week => l10n.period1w,
    month => l10n.period1m,
    threeMonths => l10n.period3m,
    sixMonths => l10n.period6m,
    yearToDate => l10n.periodYtd,
    year => l10n.period1y,
    all => l10n.periodAll,
  };

  String spokenLabel(AppLocalizations l10n) => switch (this) {
    week => l10n.periodSpoken1w,
    month => l10n.periodSpoken1m,
    threeMonths => l10n.periodSpoken3m,
    sixMonths => l10n.periodSpoken6m,
    yearToDate => l10n.periodSpokenYtd,
    year => l10n.periodSpoken1y,
    all => l10n.periodSpokenAll,
  };
}

/// A segmented control over [ChartPeriod]s. The selected segment is exposed to screen readers,
/// and each segment is read with its long name ("3 months") rather than "3M".
class PeriodSelector extends StatelessWidget {
  const PeriodSelector({
    required this.periods,
    required this.selected,
    required this.onChanged,
    super.key,
  }) : assert(periods.length >= 2, 'Offer at least two periods');

  final List<ChartPeriod> periods;
  final ChartPeriod selected;
  final ValueChanged<ChartPeriod> onChanged;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Semantics(
      container: true,
      label: l10n.periodSelectorLabel,
      child: SegmentedButton<ChartPeriod>(
        showSelectedIcon: false,
        style: const ButtonStyle(
          minimumSize: WidgetStatePropertyAll(
            Size(AppTouchTarget.android, AppTouchTarget.android),
          ),
        ),
        segments: [
          for (final p in periods)
            ButtonSegment(
              value: p,
              label: Semantics(
                label: p.spokenLabel(l10n),
                excludeSemantics: true,
                child: Text(p.shortLabel(l10n)),
              ),
            ),
        ],
        selected: {selected},
        onSelectionChanged: (s) => onChanged(s.first),
      ),
    );
  }
}

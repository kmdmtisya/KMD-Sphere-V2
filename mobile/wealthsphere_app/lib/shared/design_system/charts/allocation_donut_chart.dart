import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../components/context_locale.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'chart_frame.dart';
import 'chart_models.dart';
import 'chart_semantics.dart';

/// A donut of portfolio allocation with a legend. Slice sizes and percentages come from the
/// backend; nothing is computed here. Each slice has a palette colour **and** a legend row with
/// its label and percentage, so colour is never the only cue. Tapping a slice or a legend row
/// highlights it; [centre] is shown inside the ring.
class AllocationDonutChart extends StatefulWidget {
  const AllocationDonutChart({
    required this.slices,
    this.centre,
    this.height = 220,
    super.key,
  });

  final List<AllocationSlice> slices;
  final Widget? centre;
  final double height;

  @override
  State<AllocationDonutChart> createState() => _AllocationDonutChartState();
}

class _AllocationDonutChartState extends State<AllocationDonutChart> {
  int? _highlighted;

  void _highlight(int? index) =>
      setState(() => _highlighted = index == _highlighted ? null : index);

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final percent = context.percentFormatter;
    final slices = widget.slices;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    Color colorOf(int i) => colors.chartSeries[i % colors.chartSeries.length];

    final chart = Stack(
      alignment: Alignment.center,
      children: [
        PieChart(
          duration: reduceMotion ? Duration.zero : AppMotion.standard,
          PieChartData(
            sectionsSpace: 2,
            centerSpaceRadius: widget.height * 0.28,
            pieTouchData: PieTouchData(
              touchCallback: (event, response) {
                final index = response?.touchedSection?.touchedSectionIndex;
                if (event is FlTapUpEvent && index != null && index >= 0) {
                  _highlight(index);
                }
              },
            ),
            sections: [
              for (var i = 0; i < slices.length; i++)
                PieChartSectionData(
                  value: slices[i].percent.toDouble(),
                  color: colorOf(i),
                  showTitle: false,
                  radius: i == _highlighted ? 38 : 30,
                ),
            ],
          ),
        ),
        ?widget.centre,
      ],
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        ChartFrame(
          summary: ChartSemantics.allocation(l10n, slices, percent: percent),
          height: widget.height,
          isEmpty: slices.isEmpty,
          tableHeaders: [l10n.chartTableName, l10n.chartTableValue],
          tableRows: [
            for (final s in slices) [s.label, percent.format(s.percent)],
          ],
          chart: chart,
        ),
        if (slices.isNotEmpty)
          AllocationLegend(
            slices: slices,
            highlighted: _highlighted,
            onTap: _highlight,
          ),
      ],
    );
  }
}

/// Legend for [AllocationDonutChart]: swatch, label and percentage per row.
class AllocationLegend extends StatelessWidget {
  const AllocationLegend({
    required this.slices,
    required this.onTap,
    this.highlighted,
    super.key,
  });

  final List<AllocationSlice> slices;
  final int? highlighted;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    final text = context.wealthText;
    final percent = context.percentFormatter;
    return Column(
      children: [
        for (var i = 0; i < slices.length; i++)
          Semantics(
            button: true,
            selected: i == highlighted,
            label: AppLocalizations.of(context).allocationSliceSpoken(
              slices[i].label,
              percent.format(slices[i].percent),
            ),
            excludeSemantics: true,
            onTap: () => onTap(i),
            child: InkWell(
              onTap: () => onTap(i),
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  minHeight: AppTouchTarget.android,
                ),
                child: Row(
                  children: [
                    Container(
                      width: 14,
                      height: 14,
                      decoration: BoxDecoration(
                        color:
                            colors.chartSeries[i % colors.chartSeries.length],
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.s),
                    Expanded(
                      child: Text(
                        slices[i].label,
                        style: i == highlighted ? text.title : text.body,
                      ),
                    ),
                    Text(percent.format(slices[i].percent), style: text.amount),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}

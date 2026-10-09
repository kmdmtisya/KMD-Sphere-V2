import 'package:decimal/decimal.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../components/context_locale.dart';
import '../components/skeleton_loader.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'chart_frame.dart';
import 'chart_models.dart';
import 'chart_semantics.dart';

/// A single-series value-over-time line chart with a soft area, touch tooltips (exact formatted
/// value and date), formatted axes, and loading and empty states.
///
/// Money stays [Decimal] until the very last step: only plotting coordinates are `double`
/// (ADR-0003); every label and tooltip is formatted from the original [Decimal].
class PerformanceLineChart extends StatelessWidget {
  const PerformanceLineChart({
    required this.series,
    this.rangeLabel,
    this.loading = false,
    this.height = 200,
    super.key,
  });

  final ChartSeries series;

  /// Spoken range, e.g. "1 year". Defaults to the first and last dates.
  final String? rangeLabel;
  final bool loading;
  final double height;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return SizedBox(
        height: height,
        child: SkeletonLoader(
          child: SkeletonBox(height: height, radius: AppRadii.small),
        ),
      );
    }
    final l10n = AppLocalizations.of(context);
    final money = context.moneyFormatter;
    final locale = context.formatLocale;
    final summary = ChartSemantics.summarize(
      l10n,
      series,
      money: money,
      locale: locale,
      rangeLabel: rangeLabel,
    );
    return ChartFrame(
      summary: summary,
      height: height,
      isEmpty: series.isEmpty,
      tableHeaders: [l10n.chartTableDate, l10n.chartTableValue],
      tableRows: [
        for (final p in series.points)
          [
            DateLabels.date(p.x, locale: locale),
            money.format(Money(p.y, series.currencyCode)),
          ],
      ],
      chart: series.isEmpty
          ? const SizedBox.shrink()
          : _Line(series: series, money: money, locale: locale),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({
    required this.series,
    required this.money,
    required this.locale,
  });

  final ChartSeries series;
  final MoneyFormatter money;
  final String locale;

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    final text = context.wealthText;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    final points = series.points;
    final spots = [
      for (var i = 0; i < points.length; i++)
        FlSpot(i.toDouble(), points[i].y.toDouble()),
    ];
    final axisStyle = text.caption.copyWith(color: colors.textMuted);
    final last = (points.length - 1).toDouble();
    // A single point still needs a non-empty x range.
    final maxX = last == 0 ? 1.0 : last;

    return LineChart(
      duration: reduceMotion ? Duration.zero : AppMotion.standard,
      LineChartData(
        minX: 0,
        maxX: maxX,
        gridData: FlGridData(
          drawVerticalLine: false,
          getDrawingHorizontalLine: (_) =>
              FlLine(color: colors.chartGrid, strokeWidth: 1),
        ),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(),
          rightTitles: const AxisTitles(),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 52,
              getTitlesWidget: (value, meta) {
                if (value == meta.min || value == meta.max) {
                  return const SizedBox.shrink();
                }
                final label = money.formatCompact(
                  Money(
                    Decimal.parse(value.toStringAsFixed(2)),
                    series.currencyCode,
                  ),
                );
                return SideTitleWidget(
                  meta: meta,
                  child: Text(label, style: axisStyle),
                );
              },
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 28,
              interval: maxX,
              getTitlesWidget: (value, meta) {
                final index = value.round();
                if (index < 0 || index >= points.length) {
                  return const SizedBox.shrink();
                }
                return SideTitleWidget(
                  meta: meta,
                  child: Text(
                    DateLabels.dayMonth(points[index].x, locale: locale),
                    style: axisStyle,
                  ),
                );
              },
            ),
          ),
        ),
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => colors.surfaceElevated,
            getTooltipItems: (touched) => [
              for (final spot in touched)
                LineTooltipItem(
                  '${DateLabels.date(points[spot.spotIndex].x, locale: locale)}\n'
                  '${money.format(Money(points[spot.spotIndex].y, series.currencyCode))}',
                  text.label.copyWith(color: colors.textPrimary),
                ),
            ],
          ),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: false,
            color: colors.chartSeries.first,
            barWidth: 2.5,
            dotData: FlDotData(show: spots.length == 1),
            belowBarData: BarAreaData(
              show: true,
              color: colors.chartSeries.first.withValues(alpha: 0.12),
            ),
          ),
        ],
      ),
    );
  }
}

import 'package:decimal/decimal.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../components/context_locale.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'chart_frame.dart';
import 'chart_models.dart';
import 'chart_semantics.dart';

/// Up to three scenario lines over years. The [selectedId] line is solid and thick; the others
/// are thinner, **dashed** and muted, so the emphasis does not rely on colour alone. The values are
/// backend projections and are illustrative, never promised returns.
class ForecastComparisonChart extends StatelessWidget {
  const ForecastComparisonChart({
    required this.series,
    required this.selectedId,
    this.height = 220,
    super.key,
  }) : assert(series.length <= 3, 'Compare at most three scenarios');

  final List<ForecastSeries> series;
  final String selectedId;
  final double height;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final money = context.moneyFormatter;
    final years = <int>{
      for (final s in series)
        for (final p in s.points) p.year,
    }.toList()..sort();

    String valueAt(ForecastSeries s, int year) {
      for (final p in s.points) {
        if (p.year == year) return money.format(Money(p.value, s.currencyCode));
      }
      return '–';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        ChartFrame(
          summary: ChartSemantics.forecast(l10n, series, money: money),
          height: height,
          isEmpty: series.every((s) => s.points.isEmpty),
          tableHeaders: [l10n.chartTableYear, for (final s in series) s.label],
          tableRows: [
            for (final y in years)
              ['$y', for (final s in series) valueAt(s, y)],
          ],
          chart: _Lines(series: series, selectedId: selectedId, money: money),
        ),
        _ForecastLegend(series: series, selectedId: selectedId),
      ],
    );
  }
}

class _Lines extends StatelessWidget {
  const _Lines({
    required this.series,
    required this.selectedId,
    required this.money,
  });

  final List<ForecastSeries> series;
  final String selectedId;
  final MoneyFormatter money;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final text = context.wealthText;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    final axisStyle = text.caption.copyWith(color: colors.textMuted);
    final currency = series.first.currencyCode;

    LineChartBarData bar(int i) {
      final s = series[i];
      final selected = s.id == selectedId;
      final base = colors.chartSeries[i % colors.chartSeries.length];
      return LineChartBarData(
        spots: [
          for (final p in s.points)
            FlSpot(p.year.toDouble(), p.value.toDouble()),
        ],
        color: selected ? base : base.withValues(alpha: 0.6),
        barWidth: selected ? 3.5 : 1.5,
        dashArray: selected ? null : const [6, 4],
        dotData: const FlDotData(show: false),
      );
    }

    return LineChart(
      duration: reduceMotion ? Duration.zero : AppMotion.standard,
      LineChartData(
        minX: 0,
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
                return SideTitleWidget(
                  meta: meta,
                  child: Text(
                    money.formatCompact(
                      Money(Decimal.parse(value.toStringAsFixed(2)), currency),
                    ),
                    style: axisStyle,
                  ),
                );
              },
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 28,
              getTitlesWidget: (value, meta) {
                if (value != value.roundToDouble()) {
                  return const SizedBox.shrink();
                }
                return SideTitleWidget(
                  meta: meta,
                  child: Text(l10n.yearsShort(value.round()), style: axisStyle),
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
                  '${series[spot.barIndex].label}\n'
                  '${l10n.yearsCount(spot.x.round())}: '
                  '${money.formatCompact(Money(series[spot.barIndex].points[spot.spotIndex].value, series[spot.barIndex].currencyCode))}',
                  text.label.copyWith(color: colors.textPrimary),
                ),
            ],
          ),
        ),
        lineBarsData: [for (var i = 0; i < series.length; i++) bar(i)],
      ),
    );
  }
}

class _ForecastLegend extends StatelessWidget {
  const _ForecastLegend({required this.series, required this.selectedId});

  final List<ForecastSeries> series;
  final String selectedId;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final text = context.wealthText;
    return Wrap(
      spacing: AppSpacing.m,
      runSpacing: AppSpacing.xs,
      children: [
        for (var i = 0; i < series.length; i++)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Swatch mirrors the line style: solid for the selected series, dashed otherwise.
              CustomPaint(
                size: const Size(24, 10),
                painter: _Swatch(
                  color: colors.chartSeries[i % colors.chartSeries.length],
                  dashed: series[i].id != selectedId,
                ),
              ),
              const SizedBox(width: AppSpacing.xs),
              Flexible(
                child: Text(
                  series[i].id == selectedId
                      ? l10n.seriesSelected(series[i].label)
                      : series[i].label,
                  style: series[i].id == selectedId ? text.label : text.body,
                ),
              ),
            ],
          ),
      ],
    );
  }
}

class _Swatch extends CustomPainter {
  _Swatch({required this.color, required this.dashed});

  final Color color;
  final bool dashed;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = dashed ? 2 : 4
      ..strokeCap = StrokeCap.butt;
    final y = size.height / 2;
    if (!dashed) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
      return;
    }
    for (var x = 0.0; x < size.width; x += 8) {
      canvas.drawLine(
        Offset(x, y),
        Offset((x + 5).clamp(0, size.width), y),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_Swatch old) => old.color != color || old.dashed != dashed;
}

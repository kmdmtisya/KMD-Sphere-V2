import '../../../l10n/generated/app_localizations.dart';
import '../formatting/formatting.dart';
import 'chart_models.dart';

/// Builds the text a screen reader hears instead of a picture of a chart.
///
/// These are descriptive statistics of the points the backend supplied (first, last, highest,
/// lowest), not financial calculations. Money is formatted by the shared formatter.
abstract final class ChartSemantics {
  /// "Portfolio value rose from $1,000.00 to $1,200.00 over 1 year. High ... on ..., low ...".
  static String summarize(
    AppLocalizations l10n,
    ChartSeries series, {
    required MoneyFormatter money,
    required String locale,
    String? rangeLabel,
  }) {
    if (series.isEmpty) return l10n.chartNoData;
    String fmt(ChartPoint p) => money.format(Money(p.y, series.currencyCode));
    String date(ChartPoint p) => DateLabels.date(p.x, locale: locale);

    final points = series.points;
    final first = points.first;
    final last = points.last;
    if (points.length == 1) {
      return l10n.chartSummarySingle(series.label, fmt(first), date(first));
    }

    var high = first;
    var low = first;
    for (final p in points) {
      if (p.y > high.y) high = p;
      if (p.y < low.y) low = p;
    }
    final range = rangeLabel ?? '${date(first)} – ${date(last)}';
    if (last.y > first.y) {
      return l10n.chartSummaryRose(
        series.label,
        fmt(first),
        fmt(last),
        range,
        fmt(high),
        date(high),
        fmt(low),
        date(low),
      );
    }
    if (last.y < first.y) {
      return l10n.chartSummaryFell(
        series.label,
        fmt(first),
        fmt(last),
        range,
        fmt(high),
        date(high),
        fmt(low),
        date(low),
      );
    }
    return l10n.chartSummaryFlat(
      series.label,
      fmt(first),
      range,
      fmt(high),
      date(high),
      fmt(low),
      date(low),
    );
  }

  static String allocation(
    AppLocalizations l10n,
    List<AllocationSlice> slices, {
    required PercentFormatter percent,
  }) {
    if (slices.isEmpty) return l10n.chartNoData;
    return l10n.allocationSummary(
      slices
          .map(
            (s) =>
                l10n.allocationSliceSpoken(s.label, percent.format(s.percent)),
          )
          .join(', '),
    );
  }

  static String forecast(
    AppLocalizations l10n,
    List<ForecastSeries> series, {
    required MoneyFormatter money,
  }) {
    final parts = <String>[];
    for (final s in series) {
      if (s.points.isEmpty) continue;
      final end = s.points.last;
      parts.add(
        l10n.forecastSeriesSpoken(
          s.label,
          money.formatCompact(Money(end.value, s.currencyCode)),
          l10n.yearsCount(end.year),
        ),
      );
    }
    if (parts.isEmpty) return l10n.chartNoData;
    return l10n.forecastSummary(parts.join('. '));
  }
}

import '../design_system/charts/chart_models.dart';
import '../design_system/components/evidence_source_chip.dart';
import 'wealth_models.dart';

/// Adapters from API models to the chart and component view-models. They only rename and
/// re-shape; no value is changed.
extension PerformanceSeriesChart on PerformanceSeries {
  ChartSeries toChartSeries(String label) => ChartSeries(
    id: 'performance',
    label: label,
    currencyCode: currencyCode,
    points: [for (final p in points) ChartPoint(p.date, p.value)],
  );
}

extension EvidenceSourceView on EvidenceSourceDto {
  EvidenceSource toView() =>
      EvidenceSource(label: label, provider: provider, asOf: asOf);
}

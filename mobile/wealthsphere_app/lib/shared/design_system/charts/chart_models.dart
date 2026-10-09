import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

/// One plotted value. [y] is an exact [Decimal] as supplied by the backend; it is converted to
/// `double` only inside the chart widgets, for drawing coordinates (ADR-0003).
@immutable
class ChartPoint {
  const ChartPoint(this.x, this.y);

  final DateTime x;
  final Decimal y;

  @override
  bool operator ==(Object other) =>
      other is ChartPoint && other.x == x && other.y == y;

  @override
  int get hashCode => Object.hash(x, y);
}

/// A named series of [ChartPoint]s in one currency, ordered by date.
@immutable
class ChartSeries {
  ChartSeries({
    required this.id,
    required this.label,
    required this.currencyCode,
    required List<ChartPoint> points,
  }) : points = List.unmodifiable(points),
       assert(_isAscending(points), 'Series points must be ordered by date');

  final String id;
  final String label;
  final String currencyCode;
  final List<ChartPoint> points;

  bool get isEmpty => points.isEmpty;

  static bool _isAscending(List<ChartPoint> points) {
    for (var i = 1; i < points.length; i++) {
      if (points[i].x.isBefore(points[i - 1].x)) return false;
    }
    return true;
  }
}

/// A point on a forecast: [year] years from now and the projected [value]. Forecast values are
/// computed by the backend; the client never projects anything.
@immutable
class ForecastPoint {
  const ForecastPoint(this.year, this.value);

  final int year;
  final Decimal value;
}

/// A projection scenario's line.
@immutable
class ForecastSeries {
  ForecastSeries({
    required this.id,
    required this.label,
    required this.currencyCode,
    required List<ForecastPoint> points,
  }) : points = List.unmodifiable(points);

  final String id;
  final String label;
  final String currencyCode;
  final List<ForecastPoint> points;
}

/// One slice of an allocation. [percent] is supplied by the backend (percentage points), never
/// derived from values in the app.
@immutable
class AllocationSlice {
  const AllocationSlice({
    required this.id,
    required this.label,
    required this.percent,
  });

  final String id;
  final String label;
  final Decimal percent;
}

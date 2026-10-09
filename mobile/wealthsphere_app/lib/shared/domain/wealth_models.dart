import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../core/data/json_reader.dart';
import '../design_system/components/period_selector.dart';
import '../design_system/formatting/money.dart';

// Domain models mirroring the planned API responses (snake_case JSON, money as strings).
// The app only displays these values: every figure is computed by the backend (or, in demo mode,
// comes from a fixture). Nothing here adds, converts or derives an amount.

/// A reference to a portfolio (id, name, base currency).
@immutable
class PortfolioRef {
  const PortfolioRef({
    required this.id,
    required this.name,
    required this.baseCurrency,
  });

  factory PortfolioRef.fromJson(JsonReader r) => PortfolioRef(
    id: r.string('id'),
    name: r.string('name'),
    baseCurrency: r.string('base_currency'),
  );

  /// The id used for the consolidated (all portfolios) view.
  static const String consolidatedId = 'consolidated';

  final String id;
  final String name;
  final String baseCurrency;

  Map<String, Object?> toJson() => {
    'id': id,
    'name': name,
    'base_currency': baseCurrency,
  };

  @override
  bool operator ==(Object other) =>
      other is PortfolioRef &&
      other.id == id &&
      other.name == name &&
      other.baseCurrency == baseCurrency;

  @override
  int get hashCode => Object.hash(id, name, baseCurrency);
}

@immutable
class PortfolioSummary {
  const PortfolioSummary({
    required this.portfolioId,
    required this.name,
    required this.baseCurrency,
    required this.value,
    required this.invested,
    required this.profitLoss,
    required this.returnPercent,
    required this.asOf,
  });

  factory PortfolioSummary.fromJson(JsonReader r) => PortfolioSummary(
    portfolioId: r.string('portfolio_id'),
    name: r.string('name'),
    baseCurrency: r.string('base_currency'),
    value: r.money('value'),
    invested: r.money('invested'),
    profitLoss: r.money('profit_loss'),
    returnPercent: r.decimal('return_percent'),
    asOf: r.timestamp('as_of'),
  );

  final String portfolioId;
  final String name;
  final String baseCurrency;
  final Money value;
  final Money invested;
  final Money profitLoss;

  /// Percentage points as computed by the backend (14.09 means 14.09%).
  final Decimal returnPercent;
  final DateTime asOf;

  Map<String, Object?> toJson() => {
    'portfolio_id': portfolioId,
    'name': name,
    'base_currency': baseCurrency,
    'value': value.toJson(),
    'invested': invested.toJson(),
    'profit_loss': profitLoss.toJson(),
    'return_percent': returnPercent.toString(),
    'as_of': timestampJson(asOf),
  };
}

@immutable
class PerformancePoint {
  const PerformancePoint(this.date, this.value);

  final DateTime date;
  final Decimal value;
}

/// A value-over-time series for one portfolio and one [ChartPeriod].
@immutable
class PerformanceSeries {
  PerformanceSeries({
    required this.period,
    required this.currencyCode,
    required List<PerformancePoint> points,
    required this.asOf,
  }) : points = List.unmodifiable(points);

  final ChartPeriod period;
  final String currencyCode;
  final List<PerformancePoint> points;
  final DateTime asOf;
}

/// One allocation slice. [weightPercent] is supplied by the server (percentage points).
@immutable
class AllocationShare {
  const AllocationShare({
    required this.label,
    required this.value,
    required this.weightPercent,
  });

  factory AllocationShare.fromJson(JsonReader r) => AllocationShare(
    label: r.string('label'),
    value: r.money('value'),
    weightPercent: r.decimal('weight_percent'),
  );

  final String label;
  final Money value;
  final Decimal weightPercent;

  Map<String, Object?> toJson() => {
    'label': label,
    'value': value.toJson(),
    'weight_percent': weightPercent.toString(),
  };
}

@immutable
class PerformanceMetrics {
  const PerformanceMetrics({
    required this.totalReturnPercent,
    required this.cagrPercent,
    required this.dividendYieldPercent,
    required this.volatilityPercent,
    required this.asOf,
  });

  factory PerformanceMetrics.fromJson(JsonReader r, DateTime asOf) =>
      PerformanceMetrics(
        totalReturnPercent: r.decimal('total_return_percent'),
        cagrPercent: r.decimal('cagr_percent'),
        dividendYieldPercent: r.decimal('dividend_yield_percent'),
        volatilityPercent: r.decimal('volatility_percent'),
        asOf: asOf,
      );

  final Decimal totalReturnPercent;
  final Decimal cagrPercent;
  final Decimal dividendYieldPercent;
  final Decimal volatilityPercent;
  final DateTime asOf;
}

@immutable
class HoldingSummary {
  const HoldingSummary({
    required this.symbol,
    required this.name,
    required this.assetClass,
    required this.value,
    required this.nativeValue,
    required this.changePercent,
    required this.asOf,
  });

  factory HoldingSummary.fromJson(JsonReader r) => HoldingSummary(
    symbol: r.string('symbol'),
    name: r.string('name'),
    assetClass: r.string('asset_class'),
    value: r.money('value'),
    nativeValue: r.money('native_value'),
    changePercent: r.decimal('change_percent'),
    asOf: r.timestamp('as_of'),
  );

  final String symbol;
  final String name;
  final String assetClass;

  /// In the portfolio's base currency, converted by the backend.
  final Money value;

  /// In the asset's own currency. Equal in currency to [value] when the asset is in base currency.
  final Money nativeValue;
  final Decimal changePercent;
  final DateTime asOf;
}

@immutable
class NetWorthSummary {
  const NetWorthSummary({
    required this.assets,
    required this.liabilities,
    required this.netWorth,
    required this.asOf,
  });

  factory NetWorthSummary.fromJson(JsonReader r) => NetWorthSummary(
    assets: r.money('assets'),
    liabilities: r.money('liabilities'),
    netWorth: r.money('net_worth'),
    asOf: r.timestamp('as_of'),
  );

  final Money assets;
  final Money liabilities;
  final Money netWorth;
  final DateTime asOf;
}

@immutable
class IncomeSummary {
  const IncomeSummary({
    required this.monthly,
    required this.yearly,
    required this.asOf,
  });

  factory IncomeSummary.fromJson(JsonReader r) => IncomeSummary(
    monthly: r.money('monthly'),
    yearly: r.money('yearly'),
    asOf: r.timestamp('as_of'),
  );

  final Money monthly;
  final Money yearly;
  final DateTime asOf;
}

enum GoalStatus { onTrack, behind }

@immutable
class GoalProgress {
  const GoalProgress({
    required this.id,
    required this.name,
    required this.progressPercent,
    required this.status,
  });

  factory GoalProgress.fromJson(JsonReader r) => GoalProgress(
    id: r.string('id'),
    name: r.string('name'),
    progressPercent: r.decimal('progress_percent'),
    status: switch (r.string('status')) {
      'on_track' => GoalStatus.onTrack,
      'behind' => GoalStatus.behind,
      final other => throw FormatException(
        'Unknown goal status "$other" at ${r.path}.status',
      ),
    },
  );

  final String id;
  final String name;
  final Decimal progressPercent;
  final GoalStatus status;
}

@immutable
class GoalsSummary {
  GoalsSummary({
    required this.onTrack,
    required this.total,
    required List<GoalProgress> items,
    required this.asOf,
  }) : items = List.unmodifiable(items);

  factory GoalsSummary.fromJson(JsonReader r) => GoalsSummary(
    onTrack: r.integer('on_track'),
    total: r.integer('total'),
    items: r.list('items', GoalProgress.fromJson),
    asOf: r.timestamp('as_of'),
  );

  final int onTrack;
  final int total;
  final List<GoalProgress> items;
  final DateTime asOf;
}

/// Where an AI statement or figure came from. Plain text from the backend; never a link.
@immutable
class EvidenceSourceDto {
  const EvidenceSourceDto({
    required this.label,
    required this.provider,
    required this.asOf,
  });

  factory EvidenceSourceDto.fromJson(JsonReader r) => EvidenceSourceDto(
    label: r.string('label'),
    provider: r.string('provider'),
    asOf: r.timestamp('as_of'),
  );

  final String label;
  final String provider;
  final DateTime asOf;
}

@immutable
class InsightSummary {
  InsightSummary({
    required this.text,
    required this.asOf,
    required List<EvidenceSourceDto> sources,
  }) : sources = List.unmodifiable(sources);

  factory InsightSummary.fromJson(JsonReader r) => InsightSummary(
    text: r.string('text'),
    asOf: r.timestamp('as_of'),
    sources: r.list('sources', EvidenceSourceDto.fromJson),
  );

  final String text;
  final DateTime asOf;
  final List<EvidenceSourceDto> sources;
}

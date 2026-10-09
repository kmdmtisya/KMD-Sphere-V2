import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';
import '../../../shared/design_system/formatting/money.dart';

enum Frequency {
  monthly,
  quarterly,
  yearly;

  static Frequency parse(String text, String path) => switch (text) {
    'monthly' => monthly,
    'quarterly' => quarterly,
    'yearly' => yearly,
    _ => throw FormatException('Unknown frequency "$text" at $path'),
  };
}

/// The inputs of a compound-growth forecast, as sent to the backend (money and rates as strings).
@immutable
class CompoundForecastRequest {
  const CompoundForecastRequest({
    required this.initialInvestment,
    required this.monthlyContribution,
    required this.annualReturnPercent,
    required this.years,
    required this.contributionGrowthPercent,
    required this.inflationPercent,
    required this.annualFeePercent,
    required this.compoundingFrequency,
    required this.contributionFrequency,
    required this.conservativeReturnPercent,
    required this.growthReturnPercent,
  });

  factory CompoundForecastRequest.fromJson(JsonReader r) =>
      CompoundForecastRequest(
        initialInvestment: r.money('initial_investment'),
        monthlyContribution: r.money('monthly_contribution'),
        annualReturnPercent: r.decimal('annual_return_percent'),
        years: r.integer('years'),
        contributionGrowthPercent: r.decimal('contribution_growth_percent'),
        inflationPercent: r.decimal('inflation_percent'),
        annualFeePercent: r.decimal('annual_fee_percent'),
        compoundingFrequency: Frequency.parse(
          r.string('compounding_frequency'),
          r.path,
        ),
        contributionFrequency: Frequency.parse(
          r.string('contribution_frequency'),
          r.path,
        ),
        conservativeReturnPercent: r.decimal('conservative_return_percent'),
        growthReturnPercent: r.decimal('growth_return_percent'),
      );

  final Money initialInvestment;
  final Money monthlyContribution;

  /// Base-scenario annual return in percentage points (8 means 8%).
  final Decimal annualReturnPercent;
  final int years;
  final Decimal contributionGrowthPercent;
  final Decimal inflationPercent;
  final Decimal annualFeePercent;
  final Frequency compoundingFrequency;
  final Frequency contributionFrequency;
  final Decimal conservativeReturnPercent;
  final Decimal growthReturnPercent;

  Map<String, Object?> toJson() => {
    'initial_investment': initialInvestment.toJson(),
    'monthly_contribution': monthlyContribution.toJson(),
    'annual_return_percent': annualReturnPercent.toString(),
    'years': years,
    'contribution_growth_percent': contributionGrowthPercent.toString(),
    'inflation_percent': inflationPercent.toString(),
    'annual_fee_percent': annualFeePercent.toString(),
    'compounding_frequency': compoundingFrequency.name,
    'contribution_frequency': contributionFrequency.name,
    'conservative_return_percent': conservativeReturnPercent.toString(),
    'growth_return_percent': growthReturnPercent.toString(),
  };

  /// Value equality by exact decimal value (so `8.0` and `8.00` are the same input).
  @override
  bool operator ==(Object other) =>
      other is CompoundForecastRequest &&
      other.initialInvestment == initialInvestment &&
      other.monthlyContribution == monthlyContribution &&
      other.annualReturnPercent == annualReturnPercent &&
      other.years == years &&
      other.contributionGrowthPercent == contributionGrowthPercent &&
      other.inflationPercent == inflationPercent &&
      other.annualFeePercent == annualFeePercent &&
      other.compoundingFrequency == compoundingFrequency &&
      other.contributionFrequency == contributionFrequency &&
      other.conservativeReturnPercent == conservativeReturnPercent &&
      other.growthReturnPercent == growthReturnPercent;

  @override
  int get hashCode => Object.hash(
    initialInvestment,
    monthlyContribution,
    annualReturnPercent,
    years,
    contributionGrowthPercent,
    inflationPercent,
    annualFeePercent,
    compoundingFrequency,
    contributionFrequency,
    conservativeReturnPercent,
    growthReturnPercent,
  );
}

enum ForecastScenarioKind { conservative, base, growth }

@immutable
class YearValue {
  const YearValue(this.year, this.value);

  final int year;
  final Decimal value;
}

/// One scenario's backend-computed projection (nominal and inflation-adjusted yearly series).
@immutable
class ScenarioResult {
  ScenarioResult({
    required this.kind,
    required this.annualReturnPercent,
    required List<YearValue> nominal,
    required List<YearValue> real,
    required this.finalNominal,
    required this.finalReal,
    required this.totalContributions,
    required this.totalGrowth,
  }) : nominal = List.unmodifiable(nominal),
       real = List.unmodifiable(real);

  factory ScenarioResult.fromJson(ForecastScenarioKind kind, JsonReader r) {
    List<YearValue> series(String key) => r.list(key, (p) {
      return YearValue(p.integer('year'), p.decimal('value'));
    });
    return ScenarioResult(
      kind: kind,
      annualReturnPercent: r.decimal('annual_return_percent'),
      nominal: series('nominal'),
      real: series('real'),
      finalNominal: r.money('final_nominal'),
      finalReal: r.money('final_real'),
      totalContributions: r.money('total_contributions'),
      totalGrowth: r.money('total_growth'),
    );
  }

  final ForecastScenarioKind kind;
  final Decimal annualReturnPercent;
  final List<YearValue> nominal;
  final List<YearValue> real;
  final Money finalNominal;
  final Money finalReal;
  final Money totalContributions;
  final Money totalGrowth;
}

@immutable
class CompoundForecastResponse {
  const CompoundForecastResponse({
    required this.currencyCode,
    required this.scenarios,
    required this.assumptions,
    required this.asOf,
    required this.notice,
  });

  factory CompoundForecastResponse.fromJson(JsonReader r) {
    final scenarios = r.object('scenarios');
    return CompoundForecastResponse(
      currencyCode: r.string('currency'),
      scenarios: {
        for (final kind in ForecastScenarioKind.values)
          kind: ScenarioResult.fromJson(kind, scenarios.object(kind.name)),
      },
      assumptions: CompoundForecastRequest.fromJson(r.object('assumptions')),
      asOf: r.timestamp('as_of'),
      notice: r.string('notice'),
    );
  }

  final String currencyCode;
  final Map<ForecastScenarioKind, ScenarioResult> scenarios;

  /// The inputs these results were computed from (echoed by the backend).
  final CompoundForecastRequest assumptions;
  final DateTime asOf;

  /// "Projections are illustrative ... not guaranteed" wording supplied with the response.
  final String notice;

  /// True when the results were computed for [request]. In demo mode the canned response only
  /// matches the default inputs, and the screen shows a notice otherwise.
  bool matches(CompoundForecastRequest request) => assumptions == request;
}

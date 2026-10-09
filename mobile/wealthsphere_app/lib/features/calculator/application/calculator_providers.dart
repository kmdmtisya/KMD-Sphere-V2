import 'package:decimal/decimal.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/input/decimal_input.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../forecast/domain/forecast_models.dart';
import '../domain/forecast_input_limits.dart';

/// What the user has typed so far, kept as text so that returning to the calculator shows exactly
/// what was there. Parsing and validation happen when the form is submitted.
class CalculatorInputs {
  const CalculatorInputs({
    required this.texts,
    this.compounding = Frequency.monthly,
    this.contribution = Frequency.monthly,
  });

  /// Opens with [ForecastInputLimits.defaults], written in the user's [locale].
  factory CalculatorInputs.defaults(String locale) {
    final input = DecimalInput(locale);
    final d = ForecastInputLimits.defaults;
    String t(Decimal v) => input.format(v);
    return CalculatorInputs(
      texts: {
        CalculatorField.initialInvestment: t(d.initialInvestment.amount),
        CalculatorField.monthlyContribution: t(d.monthlyContribution.amount),
        CalculatorField.annualReturn: t(d.annualReturnPercent),
        CalculatorField.years: d.years.toString(),
        CalculatorField.contributionGrowth: t(d.contributionGrowthPercent),
        CalculatorField.inflation: t(d.inflationPercent),
        CalculatorField.annualFee: t(d.annualFeePercent),
        CalculatorField.conservativeReturn: t(d.conservativeReturnPercent),
        CalculatorField.growthReturn: t(d.growthReturnPercent),
      },
      compounding: d.compoundingFrequency,
      contribution: d.contributionFrequency,
    );
  }

  final Map<CalculatorField, String> texts;
  final Frequency compounding;
  final Frequency contribution;

  String text(CalculatorField f) => texts[f] ?? '';

  CalculatorInputs copyWith({
    Map<CalculatorField, String>? texts,
    Frequency? compounding,
    Frequency? contribution,
  }) => CalculatorInputs(
    texts: texts ?? this.texts,
    compounding: compounding ?? this.compounding,
    contribution: contribution ?? this.contribution,
  );

  /// The request for these inputs, or null if any field does not parse. The caller validates
  /// first; this only converts text to exact decimals and money (no arithmetic).
  CompoundForecastRequest? toRequest(DecimalInput input) {
    Decimal? v(CalculatorField f) => input.parse(text(f));
    final initial = v(CalculatorField.initialInvestment);
    final monthly = v(CalculatorField.monthlyContribution);
    final rate = v(CalculatorField.annualReturn);
    final years = v(CalculatorField.years);
    final growth = v(CalculatorField.contributionGrowth);
    final inflation = v(CalculatorField.inflation);
    final fee = v(CalculatorField.annualFee);
    final low = v(CalculatorField.conservativeReturn);
    final high = v(CalculatorField.growthReturn);
    if ([
      initial,
      monthly,
      rate,
      years,
      growth,
      inflation,
      fee,
      low,
      high,
    ].contains(null)) {
      return null;
    }
    return CompoundForecastRequest(
      initialInvestment: Money(initial!, ForecastInputLimits.currency),
      monthlyContribution: Money(monthly!, ForecastInputLimits.currency),
      annualReturnPercent: rate!,
      years: years!.toBigInt().toInt(),
      contributionGrowthPercent: growth!,
      inflationPercent: inflation!,
      annualFeePercent: fee!,
      compoundingFrequency: compounding,
      contributionFrequency: contribution,
      conservativeReturnPercent: low!,
      growthReturnPercent: high!,
    );
  }
}

/// Holds the user's edits. It is empty until the first edit; until then the screen shows the
/// defaults for the locale, so nothing is written while a widget is building.
class CalculatorInputsNotifier extends Notifier<CalculatorInputs?> {
  @override
  CalculatorInputs? build() => null;

  void setText(
    CalculatorField field,
    String text, {
    required CalculatorInputs base,
  }) {
    final current = state ?? base;
    state = current.copyWith(texts: {...current.texts, field: text});
  }

  void setCompounding(Frequency f, {required CalculatorInputs base}) =>
      state = (state ?? base).copyWith(compounding: f);

  void setContribution(Frequency f, {required CalculatorInputs base}) =>
      state = (state ?? base).copyWith(contribution: f);

  void reset() => state = null;
}

final calculatorInputsProvider =
    NotifierProvider<CalculatorInputsNotifier, CalculatorInputs?>(
      CalculatorInputsNotifier.new,
    );

/// The last forecast the backend returned, with the request it answers (for the Forecast screen).
class ForecastResult {
  const ForecastResult({required this.request, required this.response});

  final CompoundForecastRequest request;
  final CompoundForecastResponse response;
}

class ForecastResultNotifier extends Notifier<ForecastResult?> {
  @override
  ForecastResult? build() => null;

  void set(ForecastResult result) => state = result;
}

final forecastResultProvider =
    NotifierProvider<ForecastResultNotifier, ForecastResult?>(
      ForecastResultNotifier.new,
    );

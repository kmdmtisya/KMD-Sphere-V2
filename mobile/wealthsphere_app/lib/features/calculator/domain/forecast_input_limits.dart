import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/input/decimal_input.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../forecast/domain/forecast_models.dart';

/// The fields of the calculator form.
enum CalculatorField {
  initialInvestment,
  monthlyContribution,
  annualReturn,
  years,
  contributionGrowth,
  inflation,
  annualFee,
  conservativeReturn,
  growthReturn,
}

/// Allowed range and precision of one numeric input.
@immutable
class NumericLimit {
  const NumericLimit({
    required this.min,
    required this.max,
    this.fractionDigits = 2,
    this.wholeOnly = false,
  });

  final Decimal min;
  final Decimal max;

  /// Most decimal places accepted (0 for whole numbers).
  final int fractionDigits;
  final bool wholeOnly;

  bool get allowsNegative => min < Decimal.zero;
}

enum IssueKind {
  required,
  invalid,
  notWhole,
  tooLow,
  tooHigh,
  tooManyDecimals,
  conservativeAboveBase,
  growthBelowBase,
}

/// Why a value was rejected. [bound] is the limit involved for `tooLow` / `tooHigh`, and the
/// number of decimals for `tooManyDecimals` (as a [Decimal]).
@immutable
class InputIssue {
  const InputIssue(this.kind, [this.bound]);

  final IssueKind kind;
  final Decimal? bound;

  @override
  bool operator ==(Object other) =>
      other is InputIssue && other.kind == kind && other.bound == bound;

  @override
  int get hashCode => Object.hash(kind, bound);
}

/// The single definition of what the calculator accepts. It mirrors the schema the backend will
/// publish (P06), so the app rejects exactly what the API would, before sending it.
abstract final class ForecastInputLimits {
  static final NumericLimit initialInvestment = NumericLimit(
    min: Decimal.zero,
    max: Decimal.fromInt(1000000000),
  );
  static final NumericLimit monthlyContribution = NumericLimit(
    min: Decimal.zero,
    max: Decimal.fromInt(10000000),
  );

  /// Return rates may be negative (to model losses), within limits.
  static final NumericLimit returnRate = NumericLimit(
    min: Decimal.fromInt(-20),
    max: Decimal.fromInt(50),
  );
  static final NumericLimit years = NumericLimit(
    min: Decimal.one,
    max: Decimal.fromInt(60),
    fractionDigits: 0,
    wholeOnly: true,
  );
  static final NumericLimit contributionGrowth = NumericLimit(
    min: Decimal.zero,
    max: Decimal.fromInt(20),
  );
  static final NumericLimit inflation = NumericLimit(
    min: Decimal.zero,
    max: Decimal.fromInt(30),
  );
  static final NumericLimit annualFee = NumericLimit(
    min: Decimal.zero,
    max: Decimal.fromInt(5),
  );

  static NumericLimit of(CalculatorField field) => switch (field) {
    CalculatorField.initialInvestment => initialInvestment,
    CalculatorField.monthlyContribution => monthlyContribution,
    CalculatorField.annualReturn ||
    CalculatorField.conservativeReturn ||
    CalculatorField.growthReturn => returnRate,
    CalculatorField.years => years,
    CalculatorField.contributionGrowth => contributionGrowth,
    CalculatorField.inflation => inflation,
    CalculatorField.annualFee => annualFee,
  };

  /// The currency of the amounts (the app's base currency).
  static const String currency = 'USD';

  /// The inputs the calculator opens with. The demo forecast fixture is computed for exactly
  /// these inputs (a test keeps them identical).
  static CompoundForecastRequest get defaults => CompoundForecastRequest(
    initialInvestment: _money('10000.00'),
    monthlyContribution: _money('500.00'),
    annualReturnPercent: Decimal.parse('8.00'),
    years: 20,
    contributionGrowthPercent: Decimal.parse('0.00'),
    inflationPercent: Decimal.parse('2.50'),
    annualFeePercent: Decimal.parse('0.50'),
    compoundingFrequency: Frequency.monthly,
    contributionFrequency: Frequency.monthly,
    conservativeReturnPercent: Decimal.parse('5.00'),
    growthReturnPercent: Decimal.parse('12.00'),
  );

  static Money _money(String amount) => Money.parse(amount, currency);

  /// Validates [text] for [field]. Null means valid.
  static InputIssue? validate(
    CalculatorField field,
    String text,
    DecimalInput input, {
    bool required = true,
  }) {
    final limit = of(field);
    if (text.trim().isEmpty) {
      return required ? const InputIssue(IssueKind.required) : null;
    }
    final value = input.parse(text);
    if (value == null) return const InputIssue(IssueKind.invalid);
    if (limit.wholeOnly && input.fractionDigits(text) > 0) {
      return const InputIssue(IssueKind.notWhole);
    }
    if (input.fractionDigits(text) > limit.fractionDigits) {
      return InputIssue(
        IssueKind.tooManyDecimals,
        Decimal.fromInt(limit.fractionDigits),
      );
    }
    if (value < limit.min) return InputIssue(IssueKind.tooLow, limit.min);
    if (value > limit.max) return InputIssue(IssueKind.tooHigh, limit.max);
    return null;
  }

  /// Cross-field rule: conservative <= base <= growth. Null means fine (or not comparable yet).
  static InputIssue? validateOrdering(
    CalculatorField field,
    Decimal? conservative,
    Decimal? base,
    Decimal? growth,
  ) {
    if (field == CalculatorField.conservativeReturn &&
        conservative != null &&
        base != null &&
        conservative > base) {
      return const InputIssue(IssueKind.conservativeAboveBase);
    }
    if (field == CalculatorField.growthReturn &&
        growth != null &&
        base != null &&
        growth < base) {
      return const InputIssue(IssueKind.growthBelowBase);
    }
    return null;
  }
}

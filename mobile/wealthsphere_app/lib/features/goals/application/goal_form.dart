import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/input/decimal_input.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../calculator/domain/forecast_input_limits.dart';
import '../../forecast/domain/forecast_models.dart';
import '../domain/goal_models.dart';

/// The fields of the goal form.
enum GoalField {
  name,
  target,
  targetDate,
  contribution,
  baseReturn,
  conservativeReturn,
  growthReturn,
  contributionGrowth,
  inflation,
  annualFee,
}

/// Limits that apply to goals only (the rest are the forecast limits, shared with the
/// calculator and the backend: docs/design/goals.md).
abstract final class GoalLimits {
  static const int maxNameLength = 100;
  static const int maxYearsAhead = 60;
  static final NumericLimit target = NumericLimit(
    min: Decimal.parse('0.01'),
    max: Decimal.fromInt(10000000000),
  );

  static NumericLimit of(GoalField field) => switch (field) {
    GoalField.target => target,
    GoalField.contribution => ForecastInputLimits.monthlyContribution,
    GoalField.baseReturn ||
    GoalField.conservativeReturn ||
    GoalField.growthReturn => ForecastInputLimits.returnRate,
    GoalField.contributionGrowth => ForecastInputLimits.contributionGrowth,
    GoalField.inflation => ForecastInputLimits.inflation,
    GoalField.annualFee => ForecastInputLimits.annualFee,
    GoalField.name || GoalField.targetDate => throw ArgumentError.value(
      field,
      'field',
      'has no numeric limit',
    ),
  };
}

enum GoalIssueKind {
  /// A number problem; see [GoalIssue.input].
  input,
  nameRequired,
  nameTooLong,
  nameTaken,
  dateRequired,
  datePast,
  dateTooFar,
}

@immutable
class GoalIssue {
  const GoalIssue(this.kind, [this.input]);

  final GoalIssueKind kind;
  final InputIssue? input;

  @override
  bool operator ==(Object other) =>
      other is GoalIssue && other.kind == kind && other.input == input;

  @override
  int get hashCode => Object.hash(kind, input);

  @override
  String toString() =>
      'GoalIssue($kind${input == null ? '' : ', ${input!.kind}'})';
}

/// What the form holds: the raw text, before any checking.
@immutable
class GoalDraft {
  const GoalDraft({
    this.name = '',
    this.type = GoalType.wealth,
    this.target = '',
    this.targetDate,
    this.targetInTodaysMoney = false,
    this.portfolioId,
    this.contribution = '',
    this.frequency = Frequency.monthly,
    this.baseReturn = '',
    this.conservativeReturn = '',
    this.growthReturn = '',
    this.contributionGrowth = '',
    this.inflation = '',
    this.annualFee = '',
  });

  /// A draft that shows [goal]'s current values (for editing).
  factory GoalDraft.from(Goal goal, DecimalInput input) {
    String text(Decimal? v) => v == null ? '' : input.format(v);
    final a = goal.assumptions;
    return GoalDraft(
      name: goal.name,
      type: goal.type,
      target: input.format(goal.target.amount),
      targetDate: goal.targetDate,
      targetInTodaysMoney: goal.targetInTodaysMoney,
      portfolioId: goal.portfolioId,
      contribution: input.format(a.contribution.amount),
      frequency: a.contributionFrequency,
      baseReturn: text(a.baseReturnPercent),
      conservativeReturn: text(a.conservativeReturnPercent),
      growthReturn: text(a.growthReturnPercent),
      contributionGrowth: text(a.contributionGrowthPercent),
      inflation: text(a.inflationPercent),
      annualFee: text(a.annualFeePercent),
    );
  }

  final String name;
  final GoalType type;
  final String target;
  final DateTime? targetDate;
  final bool targetInTodaysMoney;
  final String? portfolioId;
  final String contribution;
  final Frequency frequency;
  final String baseReturn;
  final String conservativeReturn;
  final String growthReturn;
  final String contributionGrowth;
  final String inflation;
  final String annualFee;
}

/// A goal that passed every check, with exact decimals, ready to send.
@immutable
class GoalInput {
  const GoalInput({
    required this.name,
    required this.type,
    required this.target,
    required this.targetDate,
    required this.targetInTodaysMoney,
    required this.assumptions,
    this.portfolioId,
  });

  final String name;
  final GoalType type;
  final Money target;
  final DateTime targetDate;
  final bool targetInTodaysMoney;
  final String? portfolioId;
  final GoalAssumptions assumptions;
}

@immutable
class GoalValidation {
  const GoalValidation(this.issues, this.value);

  final Map<GoalField, GoalIssue> issues;
  final GoalInput? value;

  bool get isValid => issues.isEmpty;
}

/// Checks a goal draft with the same limits the backend enforces, so the person gets an instant,
/// readable answer. The server checks again and is the authority.
///
/// [today] is the current calendar day. [otherNames] are the names of the user's other goals
/// (names are unique, ignoring case).
GoalValidation validateGoal(
  GoalDraft draft, {
  required DateTime today,
  required DecimalInput input,
  Iterable<String> otherNames = const [],
}) {
  final issues = <GoalField, GoalIssue>{};

  final name = draft.name.trim();
  if (name.isEmpty) {
    issues[GoalField.name] = const GoalIssue(GoalIssueKind.nameRequired);
  } else if (name.length > GoalLimits.maxNameLength) {
    issues[GoalField.name] = const GoalIssue(GoalIssueKind.nameTooLong);
  } else if (otherNames.any(
    (n) => n.trim().toLowerCase() == name.toLowerCase(),
  )) {
    issues[GoalField.name] = const GoalIssue(GoalIssueKind.nameTaken);
  }

  Decimal? number(
    GoalField field,
    String text, {
    bool required = true,
    Decimal? whenBlank,
  }) {
    final issue = ForecastInputLimits.validateLimit(
      GoalLimits.of(field),
      text,
      input,
      required: required,
    );
    if (issue != null) {
      issues[field] = GoalIssue(GoalIssueKind.input, issue);
      return null;
    }
    return text.trim().isEmpty ? whenBlank : input.parse(text);
  }

  final target = number(GoalField.target, draft.target);
  final contribution = number(GoalField.contribution, draft.contribution);
  final base = number(GoalField.baseReturn, draft.baseReturn);
  final conservative = number(
    GoalField.conservativeReturn,
    draft.conservativeReturn,
    required: false,
  );
  final growth = number(
    GoalField.growthReturn,
    draft.growthReturn,
    required: false,
  );
  final contributionGrowth = number(
    GoalField.contributionGrowth,
    draft.contributionGrowth,
    required: false,
    whenBlank: Decimal.zero,
  );
  final inflation = number(
    GoalField.inflation,
    draft.inflation,
    required: false,
    whenBlank: Decimal.zero,
  );
  final fee = number(
    GoalField.annualFee,
    draft.annualFee,
    required: false,
    whenBlank: Decimal.zero,
  );

  // conservative <= base <= growth, only when both sides are valid numbers.
  for (final (field, calc) in [
    (GoalField.conservativeReturn, CalculatorField.conservativeReturn),
    (GoalField.growthReturn, CalculatorField.growthReturn),
  ]) {
    if (issues.containsKey(field)) continue;
    final ordering = ForecastInputLimits.validateOrdering(
      calc,
      conservative,
      base,
      growth,
    );
    if (ordering != null) {
      issues[field] = GoalIssue(GoalIssueKind.input, ordering);
    }
  }

  final date = draft.targetDate;
  if (date == null) {
    issues[GoalField.targetDate] = const GoalIssue(GoalIssueKind.dateRequired);
  } else {
    final day = DateTime(date.year, date.month, date.day);
    final now = DateTime(today.year, today.month, today.day);
    final furthest = DateTime(
      now.year + GoalLimits.maxYearsAhead,
      now.month,
      now.day,
    );
    if (!day.isAfter(now)) {
      issues[GoalField.targetDate] = const GoalIssue(GoalIssueKind.datePast);
    } else if (day.isAfter(furthest)) {
      issues[GoalField.targetDate] = const GoalIssue(GoalIssueKind.dateTooFar);
    }
  }

  if (issues.isNotEmpty) return GoalValidation(issues, null);
  const currency = ForecastInputLimits.currency;
  return GoalValidation(
    const {},
    GoalInput(
      name: name,
      type: draft.type,
      target: Money(target!, currency),
      targetDate: DateTime(date!.year, date.month, date.day),
      targetInTodaysMoney: draft.targetInTodaysMoney,
      portfolioId: draft.portfolioId,
      assumptions: GoalAssumptions(
        contribution: Money(contribution!, currency),
        contributionFrequency: draft.frequency,
        contributionGrowthPercent: contributionGrowth!,
        inflationPercent: inflation!,
        annualFeePercent: fee!,
        baseReturnPercent: base!,
        conservativeReturnPercent: conservative,
        growthReturnPercent: growth,
      ),
    ),
  );
}

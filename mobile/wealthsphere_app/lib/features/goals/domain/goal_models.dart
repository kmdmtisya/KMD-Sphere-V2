import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';
import '../../../shared/design_system/components/goal_progress_card.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../forecast/domain/forecast_models.dart';

/// What a goal is for. A label only: it changes no calculation (docs/design/goals.md).
enum GoalType {
  wealth('wealth'),
  retirement('retirement'),
  education('education'),
  houseDeposit('house_deposit'),
  businessCapital('business_capital'),
  custom('custom');

  const GoalType(this.apiName);

  final String apiName;

  static GoalType parse(String apiName) => values.firstWhere(
    (t) => t.apiName == apiName,
    orElse: () => throw FormatException('Unknown goal type "$apiName"'),
  );
}

DateTime _day(DateTime utcMidnight) =>
    DateTime(utcMidnight.year, utcMidnight.month, utcMidnight.day);

/// The assumptions a goal's estimates rest on. The user chooses every rate; nothing is suggested.
@immutable
class GoalAssumptions {
  const GoalAssumptions({
    required this.contribution,
    required this.contributionFrequency,
    required this.contributionGrowthPercent,
    required this.inflationPercent,
    required this.annualFeePercent,
    required this.baseReturnPercent,
    this.conservativeReturnPercent,
    this.growthReturnPercent,
  });

  factory GoalAssumptions.fromJson(JsonReader r) {
    final returns = r.object('returns');
    return GoalAssumptions(
      contribution: r.money('contribution'),
      contributionFrequency: Frequency.parse(
        r.string('contribution_frequency'),
        '${r.path}.contribution_frequency',
      ),
      contributionGrowthPercent: r.decimal('contribution_growth_percent'),
      inflationPercent: r.decimal('inflation_percent'),
      annualFeePercent: r.decimal('annual_fee_percent'),
      baseReturnPercent: returns.decimal('base'),
      conservativeReturnPercent: returns.has('conservative')
          ? returns.decimal('conservative')
          : null,
      growthReturnPercent: returns.has('growth')
          ? returns.decimal('growth')
          : null,
    );
  }

  /// Paid at the end of each period in the first year.
  final Money contribution;
  final Frequency contributionFrequency;
  final Decimal contributionGrowthPercent;
  final Decimal inflationPercent;
  final Decimal annualFeePercent;
  final Decimal baseReturnPercent;
  final Decimal? conservativeReturnPercent;
  final Decimal? growthReturnPercent;
}

@immutable
class Goal {
  const Goal({
    required this.id,
    required this.name,
    required this.type,
    required this.target,
    required this.targetDate,
    required this.targetInTodaysMoney,
    required this.assumptions,
    this.portfolioId,
  });

  factory Goal.fromJson(JsonReader r) => Goal(
    id: r.string('id'),
    name: r.string('name'),
    type: GoalType.parse(r.string('goal_type')),
    target: r.money('target'),
    targetDate: _day(r.date('target_date')),
    targetInTodaysMoney: r.boolean('target_in_todays_money'),
    portfolioId: r.stringOrNull('portfolio_id'),
    assumptions: GoalAssumptions.fromJson(r.object('assumptions')),
  );

  final String id;
  final String name;
  final GoalType type;
  final Money target;
  final DateTime targetDate;
  final bool targetInTodaysMoney;

  /// The portfolio that funds the goal, or null for all portfolios.
  final String? portfolioId;
  final GoalAssumptions assumptions;
}

@immutable
class ScenarioOutcome {
  const ScenarioOutcome({
    required this.kind,
    required this.annualReturnPercent,
    required this.projectedValue,
    required this.reachesTarget,
  });

  factory ScenarioOutcome.fromJson(JsonReader r) => ScenarioOutcome(
    kind: r.string('kind'),
    annualReturnPercent: r.decimal('annual_return_percent'),
    projectedValue: r.money('projected_value'),
    reachesTarget: r.boolean('reaches_target'),
  );

  /// `conservative`, `base` or `growth`.
  final String kind;
  final Decimal annualReturnPercent;
  final Money projectedValue;
  final bool reachesTarget;
}

/// The backend's figures for a goal (progress, gap, status, required contribution). Every one is
/// an estimate under the goal's assumptions.
@immutable
class GoalFigures {
  const GoalFigures({
    required this.status,
    required this.overdue,
    required this.progressPercent,
    required this.currentValue,
    required this.gap,
    required this.monthsLeft,
    required this.scenarios,
    required this.valueComplete,
    required this.valueAsOf,
    required this.notice,
    this.requiredContribution,
    this.estimatedCompletion,
  });

  factory GoalFigures.fromJson(JsonReader r) {
    final status = switch (r.string('status')) {
      'on_track' => GoalProgressStatus.onTrack,
      'behind' => GoalProgressStatus.behind,
      final other => throw FormatException(
        'Unknown goal status "$other" at ${r.path}.status',
      ),
    };
    final reached = r.has('reached') && r.boolean('reached');
    return GoalFigures(
      status: reached ? GoalProgressStatus.reached : status,
      overdue: r.boolean('overdue'),
      progressPercent: r.decimal('progress_percent'),
      currentValue: r.money('current_value'),
      gap: r.money('gap'),
      monthsLeft: r.integer('months_left'),
      scenarios: r.list('scenarios', ScenarioOutcome.fromJson),
      requiredContribution: r.has('required_contribution')
          ? r.money('required_contribution')
          : null,
      estimatedCompletion: r.has('estimated_completion')
          ? _day(r.date('estimated_completion'))
          : null,
      valueComplete: r.boolean('value_complete'),
      valueAsOf: r.timestamp('value_as_of'),
      notice: r.string('notice'),
    );
  }

  final GoalProgressStatus status;
  final bool overdue;
  final Decimal progressPercent;
  final Money currentValue;
  final Money gap;

  /// Whole months to the target date; negative after it.
  final int monthsLeft;
  final List<ScenarioOutcome> scenarios;

  /// Per contribution period, to reach the target by the date under the base scenario. Null when
  /// reached, overdue, or when no contribution falls before the date.
  final Money? requiredContribution;

  /// When the base scenario reaches the target with the current contribution, if within 100 years.
  final DateTime? estimatedCompletion;

  /// False when some assets are unpriced or unconverted, so the current value is understated.
  final bool valueComplete;
  final DateTime valueAsOf;

  /// The backend's own wording: these are estimates, not guarantees.
  final String notice;
}

/// A goal with its figures. [figures] is null when the backend has not (yet) calculated them
/// (in the demo, for a goal that was just added or changed).
@immutable
class GoalEntry {
  const GoalEntry({required this.goal, this.figures});

  factory GoalEntry.fromJson(JsonReader r) => GoalEntry(
    goal: Goal.fromJson(r.object('goal')),
    figures: r.has('figures')
        ? GoalFigures.fromJson(r.object('figures'))
        : null,
  );

  final Goal goal;
  final GoalFigures? figures;
}

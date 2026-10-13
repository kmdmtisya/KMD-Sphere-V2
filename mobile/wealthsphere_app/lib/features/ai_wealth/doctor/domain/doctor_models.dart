import 'package:flutter/foundation.dart';

import '../../../../core/data/json_reader.dart';
import '../../../../shared/design_system/components/portfolio_health_card.dart';
import '../../../../shared/design_system/components/risk_label.dart';

@immutable
class DoctorFact {
  const DoctorFact(this.label, this.value);

  factory DoctorFact.fromJson(JsonReader r) =>
      DoctorFact(r.string('label'), r.string('value'));

  final String label;
  final String value;
}

/// One observation from the Portfolio Doctor's deterministic checks, with the figures behind it
/// and the what-if scenarios that illustrate it. Never a recommendation to trade.
@immutable
class DoctorFinding {
  const DoctorFinding({
    required this.id,
    required this.kind,
    required this.severity,
    required this.title,
    required this.explanation,
    required this.facts,
    required this.scenarioIds,
  });

  factory DoctorFinding.fromJson(JsonReader r) => DoctorFinding(
    id: r.string('id'),
    kind: r.enumByName('kind', HealthFindingKind.values),
    severity: r.enumByName('severity', RiskLevel.values),
    title: r.string('title'),
    explanation: r.string('explanation'),
    facts: r.list('facts', DoctorFact.fromJson),
    scenarioIds: r.strings('scenario_ids'),
  );

  final String id;
  final HealthFindingKind kind;
  final RiskLevel severity;
  final String title;
  final String explanation;
  final List<DoctorFact> facts;
  final List<String> scenarioIds;

  HealthFinding toView() => HealthFinding(
    kind: kind,
    severity: severity,
    title: title,
    explanation: explanation,
  );
}

/// A what-if illustration: its assumptions and what it would mean. It is not a forecast.
@immutable
class DoctorScenario {
  const DoctorScenario({
    required this.id,
    required this.title,
    required this.description,
    required this.assumptions,
    required this.effect,
  });

  factory DoctorScenario.fromJson(JsonReader r) => DoctorScenario(
    id: r.string('id'),
    title: r.string('title'),
    description: r.string('description'),
    assumptions: r.strings('assumptions'),
    effect: r.string('effect'),
  );

  final String id;
  final String title;
  final String description;
  final List<String> assumptions;
  final String effect;
}

@immutable
class DoctorReport {
  const DoctorReport({
    required this.asOf,
    required this.findings,
    required this.scenarios,
    this.portfolioRequired = false,
  });

  /// The checks run on one portfolio at a time: with all portfolios selected (live mode) there is
  /// no report, and the screen asks for a portfolio.
  const DoctorReport.portfolioRequired(this.asOf)
    : findings = const [],
      scenarios = const [],
      portfolioRequired = true;

  factory DoctorReport.fromJson(JsonReader r) => DoctorReport(
    asOf: r.timestamp('as_of'),
    findings: r.list('findings', DoctorFinding.fromJson),
    scenarios: r.list('scenarios', DoctorScenario.fromJson),
  );

  final DateTime asOf;
  final List<DoctorFinding> findings;
  final List<DoctorScenario> scenarios;
  final bool portfolioRequired;

  DoctorScenario? scenario(String id) =>
      scenarios.where((s) => s.id == id).firstOrNull;

  /// The finding kinds present, in the order of [HealthFindingKind].
  List<HealthFindingKind> get kinds => [
    for (final k in HealthFindingKind.values)
      if (findings.any((f) => f.kind == k)) k,
  ];
}

import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../../core/data/json_reader.dart';
import '../../../../shared/design_system/components/evidence_source_chip.dart';
import '../../../../shared/design_system/components/risk_label.dart';

@immutable
class OpportunityCategory {
  const OpportunityCategory(this.id, this.label);

  factory OpportunityCategory.fromJson(JsonReader r) =>
      OpportunityCategory(r.string('id'), r.string('label'));

  final String id;
  final String label;
}

/// One factor of the transparent research score: what it measures and the points it earned.
@immutable
class ScoreFactor {
  const ScoreFactor({
    required this.label,
    required this.points,
    required this.max,
    required this.note,
  });

  factory ScoreFactor.fromJson(JsonReader r) => ScoreFactor(
    label: r.string('label'),
    points: r.integer('points'),
    max: r.integer('max'),
    note: r.string('note'),
  );

  final String label;
  final int points;
  final int max;
  final String note;
}

@immutable
class OpportunityAttribute {
  const OpportunityAttribute(this.label, this.value);

  factory OpportunityAttribute.fromJson(JsonReader r) =>
      OpportunityAttribute(r.string('label'), r.string('value'));

  final String label;
  final String value;
}

@immutable
class ResearchSection {
  const ResearchSection(this.heading, this.text);

  factory ResearchSection.fromJson(JsonReader r) =>
      ResearchSection(r.string('heading'), r.string('text'));

  final String heading;
  final String text;
}

/// Example assumptions for the calculator hand-off. They are illustrations chosen for this idea,
/// never a prediction of what it will return.
@immutable
class SimulationAssumptions {
  const SimulationAssumptions({
    required this.initialInvestment,
    required this.monthlyContribution,
    required this.annualReturn,
    required this.conservativeReturn,
    required this.growthReturn,
    required this.years,
    required this.inflation,
    required this.annualFee,
  });

  factory SimulationAssumptions.fromJson(JsonReader r) => SimulationAssumptions(
    initialInvestment: r.decimal('initial_investment'),
    monthlyContribution: r.decimal('monthly_contribution'),
    annualReturn: r.decimal('annual_return'),
    conservativeReturn: r.decimal('conservative_return'),
    growthReturn: r.decimal('growth_return'),
    years: r.integer('years'),
    inflation: r.decimal('inflation'),
    annualFee: r.decimal('annual_fee'),
  );

  final Decimal initialInvestment;
  final Decimal monthlyContribution;
  final Decimal annualReturn;
  final Decimal conservativeReturn;
  final Decimal growthReturn;
  final int years;
  final Decimal inflation;
  final Decimal annualFee;
}

/// A research candidate: a place to start looking, never a recommendation.
@immutable
class OpportunityCandidate {
  const OpportunityCandidate({
    required this.id,
    required this.categoryId,
    required this.name,
    required this.symbol,
    required this.assetClass,
    required this.summary,
    required this.risk,
    required this.risks,
    required this.evidence,
    required this.asOf,
    required this.attributes,
    required this.research,
    this.score,
    this.scoreFactors = const [],
    this.simulation,
  });

  factory OpportunityCandidate.fromJson(JsonReader r) {
    final asOf = r.timestamp('as_of');
    final score = r.has('score') ? r.integer('score') : null;
    final factors = r.has('score_factors')
        ? r.list('score_factors', ScoreFactor.fromJson)
        : const <ScoreFactor>[];
    if (score != null && factors.isEmpty) {
      throw FormatException('${r.path}.score has no score_factors');
    }
    return OpportunityCandidate(
      id: r.string('id'),
      categoryId: r.string('category'),
      name: r.string('name'),
      symbol: r.string('symbol'),
      assetClass: r.string('asset_class'),
      summary: r.string('summary'),
      risk: r.enumByName('risk', RiskLevel.values),
      score: score,
      scoreFactors: factors,
      risks: r.strings('risks'),
      evidence: r.list(
        'evidence',
        (e) => EvidenceSource(
          label: e.string('label'),
          provider: e.string('provider'),
          asOf: e.timestamp('as_of'),
        ),
      ),
      asOf: asOf,
      attributes: r.list('attributes', OpportunityAttribute.fromJson),
      research: r.list('research', ResearchSection.fromJson),
      simulation: r.has('simulate')
          ? SimulationAssumptions.fromJson(r.object('simulate'))
          : null,
    );
  }

  final String id;
  final String categoryId;
  final String name;
  final String symbol;
  final String assetClass;
  final String summary;
  final RiskLevel risk;
  final List<String> risks;
  final List<EvidenceSource> evidence;
  final DateTime asOf;
  final List<OpportunityAttribute> attributes;
  final List<ResearchSection> research;

  /// A whole-number research score, or null when there is not enough evidence to score.
  final int? score;
  final List<ScoreFactor> scoreFactors;

  /// Example assumptions for the calculator; null when the idea has no evidence to base them on.
  final SimulationAssumptions? simulation;

  String? attribute(String label) =>
      attributes.where((a) => a.label == label).map((a) => a.value).firstOrNull;
}

@immutable
class OpportunityList {
  const OpportunityList({
    required this.asOf,
    required this.notice,
    required this.categories,
    required this.candidates,
  });

  factory OpportunityList.fromJson(JsonReader r) => OpportunityList(
    asOf: r.timestamp('as_of'),
    notice: r.string('notice'),
    categories: r.list('categories', OpportunityCategory.fromJson),
    candidates: r.list('candidates', OpportunityCandidate.fromJson),
  );

  final DateTime asOf;

  /// The backend's statement of what these ideas are (in the demo: mock, not live).
  final String notice;
  final List<OpportunityCategory> categories;
  final List<OpportunityCandidate> candidates;

  OpportunityCandidate? byId(String id) =>
      candidates.where((c) => c.id == id).firstOrNull;
}

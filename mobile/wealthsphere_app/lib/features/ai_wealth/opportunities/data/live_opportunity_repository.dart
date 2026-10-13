import '../../../../core/data/json_reader.dart';
import '../../../../core/network/live_repository.dart';
import '../../../../l10n/generated/app_localizations.dart';
import '../../../../shared/design_system/components/evidence_source_chip.dart';
import '../../../../shared/design_system/components/risk_label.dart';
import '../domain/opportunity_models.dart';
import 'opportunity_repository.dart';

/// AI Investment Intelligence over the API (P12-T06/T07). The ideas are a stored run of the
/// server's pipeline: deterministic selection, scores and evidence, explained by the model from
/// those facts only. A run from the last 24 hours is shown again (runs are limited per day); a
/// new run is made only when there is none. Compare asks the server for the side-by-side facts.
/// There are no example returns: Simulate takes the user's own assumptions.
///
/// Labels come from the app's strings; asset class names and all text about an idea come from
/// the server.
class LiveOpportunityRepository extends LiveRepository
    implements OpportunityRepository {
  const LiveOpportunityRepository(
    super.dio,
    this.l10n, {
    DateTime Function()? clock,
  }) : _clock = clock; // ignore: prefer_initializing_formals (a private field)

  final AppLocalizations l10n;
  final DateTime Function()? _clock;

  static const _base = '/api/v1/ai/opportunities';
  static const reuseFor = Duration(hours: 24);

  DateTime _now() => (_clock ?? DateTime.now)().toUtc();

  Future<Map<String, String>> _classNames() async => {
    for (final c in await getList(
      '/api/v1/asset-classes',
      (r) => (code: r.string('code'), name: r.string('name')),
    ))
      c.code: c.name,
  };

  @override
  Future<OpportunityList> opportunities() async {
    final mapper = OpportunityMapper(l10n, await _classNames());
    final recent = await getList(
      '$_base/runs',
      (r) => (id: r.string('id'), at: r.timestamp('created_at')),
      query: {'limit': 1},
    );
    final latest = recent.firstOrNull;
    if (latest != null && _now().difference(latest.at) < reuseFor) {
      return getObject('$_base/runs/${latest.id}', mapper.list);
    }
    return send('POST', _base, mapper.list, body: const <String, Object?>{});
  }

  @override
  Future<Map<String, List<OpportunityAttribute>>> compare(
    List<String> ids,
  ) async {
    final mapper = OpportunityMapper(l10n, await _classNames());
    return send(
      'POST',
      '/api/v1/ai/compare',
      (r) => {
        for (final item in r.list('items', (i) => i))
          item.string('asset_id'): mapper.compared(item),
      },
      body: {'asset_ids': ids},
    );
  }
}

RiskLevel riskFromLevel(int level) => switch (level) {
  <= 2 => RiskLevel.low,
  3 => RiskLevel.medium,
  _ => RiskLevel.high,
};

/// Maps the server's opportunity and compare answers to the screens' models.
class OpportunityMapper {
  const OpportunityMapper(this.l10n, this.classNames);

  final AppLocalizations l10n;
  final Map<String, String> classNames;

  String className(String code) => classNames[code] ?? code;

  String factor(String code) => switch (code) {
    'stability' => l10n.oppFactorStability,
    'resilience' => l10n.oppFactorResilience,
    'momentum' => l10n.oppFactorMomentum,
    'cost' => l10n.oppFactorCost,
    'liquidity' => l10n.oppFactorLiquidity,
    'risk_class' => l10n.oppFactorRiskClass,
    _ => code,
  };

  String liquidity(String code) => switch (code) {
    'immediate' => l10n.liquidityImmediate,
    'market' => l10n.liquidityMarket,
    'term' => l10n.liquidityTerm,
    'illiquid' => l10n.liquidityIlliquid,
    _ => l10n.liquidityUnknown,
  };

  String confidence(String code) => switch (code) {
    'high' => l10n.confidenceHigh,
    'medium' => l10n.confidenceMedium,
    'low' => l10n.confidenceLow,
    _ => l10n.confidenceNone,
  };

  String verdict(String code) => switch (code) {
    'fits' => l10n.oppFitFits,
    'caution' => l10n.oppFitCaution,
    _ => l10n.oppFitNotSuitable,
  };

  String horizon(JsonReader h) =>
      l10n.oppAttrHorizonValue('${h.integer('minimum_years')}');

  int? _whole(JsonReader r, String key) =>
      r.has(key) ? r.decimal(key).round().toBigInt().toInt() : null;

  OpportunityList list(JsonReader run) {
    final created = run.timestamp('created_at');
    final candidates = run.list('opportunities', (o) {
      final facts = o.object('facts');
      final score = facts.object('score');
      final explanation = o.object('explanation');
      final compat = facts.has('compatibility')
          ? facts.object('compatibility')
          : null;
      final assetClass = o.string('asset_class');
      return OpportunityCandidate(
        id: o.string('asset_id'),
        categoryId: assetClass,
        name: o.string('name'),
        symbol: o.stringOrNull('symbol') ?? '',
        assetClass: className(assetClass),
        summary: explanation.string('thesis'),
        risk: riskFromLevel(o.integer('risk_level')),
        score: _whole(score, 'score'),
        scoreFactors: [
          for (final f in score.list('factors', (f) => f))
            if (f.string('status') == 'used')
              ScoreFactor(
                label: factor(f.string('factor')),
                points: _whole(f, 'points') ?? 0,
                max: 100,
                note: f.string('explanation'),
              ),
        ],
        risks: explanation.strings('key_risks'),
        evidence: facts.list(
          'evidence',
          (e) => EvidenceSource(
            label: e.string('title'),
            provider: e.string('source'),
            asOf: e.timestamp('published_at'),
          ),
        ),
        asOf: created,
        attributes: [
          OpportunityAttribute(
            l10n.oppAttrRiskLevel,
            l10n.oppAttrRiskLevelValue('${o.integer('risk_level')}'),
          ),
          OpportunityAttribute(
            l10n.oppAttrLiquidity,
            liquidity(facts.string('liquidity')),
          ),
          OpportunityAttribute(l10n.oppAttrCurrency, facts.string('currency')),
          OpportunityAttribute(
            l10n.oppAttrConfidence,
            confidence(score.string('confidence')),
          ),
          OpportunityAttribute(
            l10n.oppAttrHorizon,
            horizon(facts.object('research_horizon')),
          ),
          if (compat != null)
            OpportunityAttribute(
              l10n.oppAttrFit,
              verdict(compat.string('verdict')),
            ),
        ],
        research: [
          ResearchSection(
            l10n.oppResearchWhy,
            explanation.string('why_surfaced'),
          ),
          ResearchSection(
            l10n.oppResearchAssumptions,
            explanation.strings('assumptions').join(' '),
          ),
        ],
        ownReturns: true,
      );
    });
    final classes = <String>[];
    for (final c in candidates) {
      if (!classes.contains(c.categoryId)) classes.add(c.categoryId);
    }
    return OpportunityList(
      asOf: created,
      notice: run.string('notice'),
      categories: [
        for (final code in classes) OpportunityCategory(code, className(code)),
      ],
      candidates: candidates,
    );
  }

  String _percent(JsonReader r, String key) =>
      r.has(key) ? l10n.cmpPercent('${r.decimal(key)}') : l10n.cmpNotMeasured;

  List<OpportunityAttribute> compared(JsonReader item) {
    final past = item.object('past');
    final minimum = item.has('minimum_investment')
        ? item.object('minimum_investment')
        : null;
    return [
      OpportunityAttribute(
        l10n.cmpAssetClass,
        className(item.string('asset_class')),
      ),
      OpportunityAttribute(l10n.oppAttrCurrency, item.string('currency')),
      OpportunityAttribute(
        l10n.oppAttrLiquidity,
        liquidity(item.string('liquidity')),
      ),
      OpportunityAttribute(
        l10n.cmpMinimum,
        minimum == null
            ? l10n.cmpMinimumNone
            : '${minimum.decimal('amount')} ${minimum.string('currency')}',
      ),
      OpportunityAttribute(
        l10n.cmpExpense,
        item.has('expense_ratio_percent')
            ? l10n.cmpExpenseValue('${item.decimal('expense_ratio_percent')}')
            : l10n.cmpNotApplicable,
      ),
      OpportunityAttribute(l10n.cmpIncomeYield, l10n.cmpNotAvailable),
      OpportunityAttribute(
        l10n.cmpPastChange,
        _percent(past, 'price_change_percent'),
      ),
      OpportunityAttribute(
        l10n.cmpPastVolatility,
        _percent(past, 'volatility_percent'),
      ),
      OpportunityAttribute(
        l10n.cmpPastFall,
        _percent(past, 'max_drawdown_percent'),
      ),
      OpportunityAttribute(
        l10n.oppAttrHorizon,
        horizon(item.object('research_horizon')),
      ),
      OpportunityAttribute(
        l10n.cmpEligible,
        item.boolean('eligible') ? l10n.cmpYes : l10n.cmpNo,
      ),
    ];
  }
}

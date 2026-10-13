import '../../../../core/data/json_reader.dart';
import '../../../../core/network/live_repository.dart';
import '../../../../l10n/generated/app_localizations.dart';
import '../../../../shared/design_system/components/portfolio_health_card.dart';
import '../../../../shared/design_system/components/risk_label.dart';
import '../../../../shared/domain/wealth_models.dart';
import '../domain/doctor_models.dart';
import 'doctor_repository.dart';

/// The Portfolio Doctor over the API (P12-T01): `POST /api/v1/ai/portfolio-doctor`. The findings
/// are the server's deterministic checks; this maps them for the screen and adds nothing. Only
/// flagged findings are listed (checks within their thresholds are not findings). The server's
/// sentences are shown as they are: they are data, like the demo file's.
class LiveDoctorRepository extends LiveRepository implements DoctorRepository {
  const LiveDoctorRepository(super.dio, this.l10n);

  final AppLocalizations l10n;

  @override
  Future<DoctorReport> report(String portfolioId) async {
    if (portfolioId == PortfolioRef.consolidatedId) {
      return DoctorReport.portfolioRequired(DateTime.now().toUtc());
    }
    return send(
      'POST',
      '/api/v1/ai/portfolio-doctor',
      (r) => doctorReportFromApi(r, l10n),
      body: {'portfolio_id': portfolioId},
    );
  }
}

/// Server check -> the screen's finding type.
const Map<String, HealthFindingKind> checkKinds = {
  'position_concentration': HealthFindingKind.concentration,
  'asset_class_concentration': HealthFindingKind.concentration,
  'sector_concentration': HealthFindingKind.concentration,
  'geographic_concentration': HealthFindingKind.concentration,
  'currency_exposure': HealthFindingKind.currency,
  'liquidity': HealthFindingKind.liquidity,
  'volatility': HealthFindingKind.volatility,
  'drawdown': HealthFindingKind.volatility,
  'income_dependence': HealthFindingKind.income,
  'goal_alignment': HealthFindingKind.goals,
  'data_completeness': HealthFindingKind.data,
};

String _figure(JsonReader f, String field) {
  final value = f.decimal(field).toString();
  return f.stringOrNull('unit') == 'percent' ? '$value%' : value;
}

DoctorReport doctorReportFromApi(JsonReader r, AppLocalizations l10n) {
  final scenarios = r.list('scenarios', (s) {
    final check = s.string('check');
    final changes = s.list(
      'changes',
      (c) =>
          '${c.string('subject')}: ${c.decimal('before')}% → ${c.decimal('after')}%',
    );
    final measure = s.string('measure');
    final before = s.has('before') ? s.decimal('before').toString() : '-';
    final after = s.has('after') ? s.decimal('after').toString() : '-';
    return DoctorScenario(
      id: 's-$check',
      title: s.string('description'),
      description: changes.join('\n'),
      assumptions: s.strings('assumptions'),
      effect: '$measure: $before → $after',
    );
  });
  final ids = {for (final s in scenarios) s.id};
  final findings = <DoctorFinding>[];
  for (final f in r.list('findings', (f) => f)) {
    if (f.string('status') != 'flagged') continue;
    final check = f.string('check');
    final kind = checkKinds[check];
    if (kind == null) continue; // a check this app version does not know yet
    findings.add(
      DoctorFinding(
        id: 'f-$check',
        kind: kind,
        severity: switch (f.string('severity')) {
          'high' => RiskLevel.high,
          'medium' => RiskLevel.medium,
          _ => RiskLevel.low, // low and info
        },
        title: f.string('message'),
        explanation: f.strings('assumptions').join(' '),
        facts: [
          if (f.has('value'))
            DoctorFact(l10n.doctorFactMeasured, _figure(f, 'value')),
          if (f.has('threshold'))
            DoctorFact(l10n.doctorFactThreshold, _figure(f, 'threshold')),
        ],
        scenarioIds: [if (ids.contains('s-$check')) 's-$check'],
      ),
    );
  }
  return DoctorReport(
    asOf: r.timestamp('as_of'),
    findings: findings,
    scenarios: scenarios,
  );
}

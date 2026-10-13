// P12-T09: the Doctor, Opportunities, Compare and Simulate wired to the live services. The
// repositories map the server's deterministic answers; nothing is computed, ranked or suggested
// on the device, and there is never a trade button or a suggested return.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/features/ai_wealth/doctor/data/doctor_repository.dart';
import 'package:wealthsphere_app/features/ai_wealth/doctor/data/live_doctor_repository.dart';
import 'package:wealthsphere_app/features/ai_wealth/doctor/presentation/doctor_screen.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/application/opportunity_providers.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/data/live_opportunity_repository.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/data/opportunity_repository.dart';
import 'package:wealthsphere_app/features/calculator/application/calculator_providers.dart';
import 'package:wealthsphere_app/features/calculator/domain/forecast_input_limits.dart';
import 'package:wealthsphere_app/l10n/generated/app_localizations.dart';
import 'package:wealthsphere_app/shared/design_system/components/portfolio_health_card.dart';
import 'package:wealthsphere_app/shared/design_system/components/risk_label.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/fake_api.dart';
import '../../helpers/pump_app.dart';

final l10n = lookupAppLocalizations(const Locale('en'));
const pid = '11111111-1111-1111-1111-111111111111';
const geq = '22222222-2222-2222-2222-222222222222';
const gbd = '33333333-3333-3333-3333-333333333333';

Map<String, Object?> finding(
  String check,
  String status,
  String severity, {
  String? value,
  String? threshold,
  String unit = 'percent',
}) => {
  'check': check,
  'status': status,
  'severity': severity,
  'message': 'Message about $check.',
  'metric': 'share',
  'unit': value == null ? null : unit,
  'value': value,
  'threshold': threshold,
  'subject': null,
  'assumptions': ['Assumption for $check.'],
};

final doctorJson = {
  'portfolio_id': pid,
  'as_of': '2026-10-13T09:00:00Z',
  'currency': 'USD',
  'total_value': usd('10000.00'),
  'overall': 'high',
  'counts': {'high': 1, 'medium': 1, 'low': 0, 'info': 1},
  'complete': false,
  'findings': [
    finding(
      'position_concentration',
      'flagged',
      'high',
      value: '90',
      threshold: '35',
    ),
    finding('currency_exposure', 'ok', 'ok', value: '0'),
    finding('goal_alignment', 'flagged', 'medium', value: '1', unit: 'count'),
    finding('data_completeness', 'flagged', 'info', value: '2', unit: 'count'),
    finding('volatility', 'not_assessed', 'info'),
  ],
  'scenarios': [
    {
      'check': 'position_concentration',
      'description':
          'If the largest holding were 20% of the portfolio instead of 90%.',
      'is_trade': false,
      'changes': [
        {'subject': 'asset-1', 'before': '90', 'after': '20'},
      ],
      'measure': 'effective_positions',
      'before': '1.22',
      'after': '2.5',
      'assumptions': ['Hypothetical. Not an order.'],
    },
  ],
  'notice': 'Not investment advice.',
};

Map<String, Object?> runJson({String created = '2026-10-13T08:00:00Z'}) => {
  'id': 'run-1',
  'created_at': created,
  'portfolio_id': null,
  'asset_class': null,
  'explanation_source': 'model',
  'amount': null,
  'provider': 'fake',
  'model': 'fake-1',
  'weights': <String, String>{},
  'investor': <String, Object?>{},
  'excluded': <Object?>[],
  'notice': 'Research candidates. Not advice.',
  'opportunities': [
    {
      'rank': 1,
      'asset_id': gbd,
      'symbol': 'DEMO-GBD',
      'name': 'Demo Global Bond ETF (DEMO)',
      'asset_class': 'etf',
      'is_demo': true,
      'risk_level': 2,
      'facts': {
        'liquidity': 'market',
        'currency': 'USD',
        'score': {
          'score': '74.6',
          'confidence': 'high',
          'coverage_percent': '100',
          'reasons': <String>[],
          'factors': [
            {
              'factor': 'stability',
              'status': 'used',
              'points': '80.4',
              'explanation':
                  'Volatility of 11.8% a year over the last year: 80.4/100.',
            },
            {
              'factor': 'momentum',
              'status': 'missing',
              'points': null,
              'explanation': 'Less than 10 months of prices in the last year.',
            },
          ],
        },
        'research_horizon': {'minimum_years': 1, 'basis': 'Assumed.'},
        'compatibility': {'verdict': 'caution'},
        'evidence': [
          {
            'id': 'e-1',
            'title': 'DEMO note: rates',
            'summary': 'Rates move prices.',
            'source': 'demo',
            'licence_status': 'demo',
            'published_at': '2026-09-25T08:00:00Z',
          },
        ],
      },
      'explanation': {
        'thesis': 'A bond fund that passed the rules.',
        'why_surfaced': 'Its stability scored well.',
        'key_risks': ['Prices fall when rates rise.'],
        'assumptions': ['Scores describe the past.'],
        'evidence_ids': ['e-1'],
      },
      'explanation_source': 'model',
      'actions': ['research', 'compare', 'simulate'],
      'is_trade': false,
    },
  ],
};

const classesJson = [
  {
    'code': 'etf',
    'name': 'ETFs',
    'valuation_mode': 'market',
    'metadata_fields': <String, Object?>{},
  },
  {
    'code': 'bond',
    'name': 'Bonds',
    'valuation_mode': 'manual',
    'metadata_fields': <String, Object?>{},
  },
];

void main() {
  group('Doctor', () {
    test(
      'only flagged findings are listed, with their figures and scenarios',
      () async {
        final api = FakeApi()
          ..json('POST /api/v1/ai/portfolio-doctor', doctorJson);
        final report = await LiveDoctorRepository(api.dio(), l10n).report(pid);
        expect(api.callsTo('POST', '/api/v1/ai/portfolio-doctor').single.body, {
          'portfolio_id': pid,
        });
        expect(
          [for (final f in report.findings) f.kind],
          [
            HealthFindingKind.concentration,
            HealthFindingKind.goals,
            HealthFindingKind.data,
          ],
        );
        final top = report.findings.first;
        expect(top.severity, RiskLevel.high);
        expect(top.title, 'Message about position_concentration.');
        expect(
          [for (final f in top.facts) '${f.label}: ${f.value}'],
          ['Measured: 90%', 'Threshold reached: 35%'],
        );
        expect(top.scenarioIds, ['s-position_concentration']);
        final scenario = report.scenario('s-position_concentration')!;
        expect(scenario.description, 'asset-1: 90% → 20%');
        expect(scenario.assumptions, ['Hypothetical. Not an order.']);
        expect(report.findings[1].facts.single.value, '1', reason: 'a count');
        expect(
          report.findings[2].severity,
          RiskLevel.low,
          reason: 'info is shown as low',
        );
      },
    );

    test(
      'all portfolios together asks for one portfolio and calls nothing',
      () async {
        final api = FakeApi();
        final report = await LiveDoctorRepository(
          api.dio(),
          l10n,
        ).report(PortfolioRef.consolidatedId);
        expect(report.portfolioRequired, isTrue);
        expect(api.calls, isEmpty);
      },
    );

    testWidgets('the screen says to choose a portfolio', (tester) async {
      final api = FakeApi()..json('GET /api/v1/portfolios', <Object?>[]);
      await tester.pumpApp(
        const DoctorScreen(),
        overrides: demoOverrides(
          extra: [
            liveModeOverride(),
            doctorRepositoryProvider.overrideWithValue(
              LiveDoctorRepository(api.dio(), l10n),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(l10n.doctorChoosePortfolio), findsOneWidget);
      expect(
        find.text('DEMO'),
        findsNothing,
        reason: 'live data is not labelled DEMO',
      );
    });
  });

  group('Opportunities', () {
    FakeApi api0() => FakeApi()..json('GET /api/v1/asset-classes', classesJson);

    test('a recent run is shown again without a new run', () async {
      final api = api0()
        ..json('GET /api/v1/ai/opportunities/runs', [
          {'id': 'run-1', 'created_at': '2026-10-13T08:00:00Z'},
        ])
        ..json('GET /api/v1/ai/opportunities/runs/run-1', runJson());
      final repo = LiveOpportunityRepository(
        api.dio(),
        l10n,
        clock: () => DateTime.utc(2026, 10, 13, 12),
      );
      final list = await repo.opportunities();
      expect(api.callsTo('POST', '/api/v1/ai/opportunities'), isEmpty);
      final c = list.candidates.single;
      expect(
        (c.id, c.name, c.assetClass, c.risk),
        (gbd, 'Demo Global Bond ETF (DEMO)', 'ETFs', RiskLevel.low),
      );
      expect(c.score, 75, reason: 'the server score, rounded for display');
      expect(
        [for (final f in c.scoreFactors) f.label],
        ['Stability'],
        reason: 'only measured factors',
      );
      expect(c.summary, 'A bond fund that passed the rules.');
      expect(c.risks, ['Prices fall when rates rise.']);
      expect(c.evidence.single.label, 'DEMO note: rates');
      expect(c.attribute('Portfolio fit'), 'Caution');
      expect(c.attribute('Research horizon'), 'At least 1 years (assumed)');
      expect(c.attribute('Liquidity'), 'Within days');
      expect(c.simulation, isNull, reason: 'no example returns');
      expect(c.ownReturns, isTrue);
      expect(list.notice, 'Research candidates. Not advice.');
      expect([for (final k in list.categories) k.label], ['ETFs']);
    });

    test('without a recent run a new one is made', () async {
      final api = api0()
        ..json('GET /api/v1/ai/opportunities/runs', [
          {'id': 'old', 'created_at': '2026-10-11T08:00:00Z'},
        ])
        ..json('POST /api/v1/ai/opportunities', runJson(), status: 201);
      final repo = LiveOpportunityRepository(
        api.dio(),
        l10n,
        clock: () => DateTime.utc(2026, 10, 13, 12),
      );
      await repo.opportunities();
      expect(api.callsTo('POST', '/api/v1/ai/opportunities'), hasLength(1));
    });

    test(
      'compare lays out the server facts, past figures labelled past',
      () async {
        final item = {
          'asset_id': geq,
          'asset_class': 'etf',
          'currency': 'USD',
          'liquidity': 'market',
          'minimum_investment': null,
          'expense_ratio_percent': '0.2',
          'eligible': false,
          'past': {
            'price_change_percent': '8.4',
            'volatility_percent': '12.1',
            'max_drawdown_percent': null,
            'last_close': '2026-10-12',
            'weeks_of_prices': 52,
          },
          'research_horizon': {'minimum_years': 5, 'basis': 'Assumed.'},
        };
        final api = api0()
          ..json('POST /api/v1/ai/compare', {
            'items': [item],
            'notice': 'n',
          });
        final repo = LiveOpportunityRepository(api.dio(), l10n);
        final facts = (await repo.compare([geq, gbd]))[geq]!;
        String v(String label) =>
            facts.firstWhere((a) => a.label == label).value;
        expect(api.callsTo('POST', '/api/v1/ai/compare').single.body, {
          'asset_ids': [geq, gbd],
        });
        expect(v('Price change, last year (past)'), '8.4%');
        expect(v('Largest fall, last year (past)'), 'Not measured');
        expect(v('Expense ratio'), '0.2% a year');
        expect(v('Income yield'), 'Not available');
        expect(v('Minimum investment'), 'None stated');
        expect(v('Eligible for you'), 'No');
        expect(v('Asset class'), 'ETFs');
      },
    );

    testWidgets(
      'Simulate opens the calculator with the returns left for the user',
      (tester) async {
        final api = api0()
          ..json('GET /api/v1/ai/opportunities/runs', <Object?>[])
          ..json('POST /api/v1/ai/opportunities', runJson(), status: 201);
        final container = ProviderContainer(
          overrides: demoOverrides(
            extra: [
              liveModeOverride(),
              opportunityRepositoryProvider.overrideWithValue(
                LiveOpportunityRepository(api.dio(), l10n),
              ),
            ],
          ),
        );
        addTearDown(container.dispose);
        late WidgetRef ref;
        await tester.pumpWidget(
          UncontrolledProviderScope(
            container: container,
            child: Consumer(
              builder: (context, r, _) {
                ref = r;
                return const SizedBox();
              },
            ),
          ),
        );
        final list = (await tester.runAsync(
          () => container.read(opportunitiesProvider.future),
        ))!;
        expect(simulateInCalculator(ref, list.candidates.single, 'en'), isTrue);
        final inputs = container.read(calculatorInputsProvider)!;
        for (final f in [
          CalculatorField.annualReturn,
          CalculatorField.conservativeReturn,
          CalculatorField.growthReturn,
        ]) {
          expect(
            inputs.text(f),
            isEmpty,
            reason: 'WealthSphere never suggests a return',
          );
        }
        expect(container.read(calculatorPrefillProvider), isNull);
      },
    );
  });
}

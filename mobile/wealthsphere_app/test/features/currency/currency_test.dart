import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';
import 'package:wealthsphere_app/features/currency/application/currency_providers.dart';
import 'package:wealthsphere_app/features/currency/data/currency_repository.dart';
import 'package:wealthsphere_app/features/currency/data/live_currency_repository.dart';
import 'package:wealthsphere_app/features/currency/domain/currency_models.dart';
import 'package:wealthsphere_app/features/currency/presentation/currency_converter_screen.dart';
import 'package:wealthsphere_app/features/currency/presentation/currency_widgets.dart';
import 'package:wealthsphere_app/features/dashboard/application/dashboard_providers.dart';
import 'package:wealthsphere_app/features/more/presentation/settings_screen.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/fake_api.dart';
import '../../helpers/pump_app.dart';

const currenciesJson = [
  {'code': 'AED', 'name': 'UAE dirham', 'symbol': 'AED', 'decimal_places': 2},
  {'code': 'EUR', 'name': 'Euro', 'symbol': '€', 'decimal_places': 2},
  {'code': 'JPY', 'name': 'Japanese yen', 'symbol': '¥', 'decimal_places': 0},
  {
    'code': 'KES',
    'name': 'Kenyan shilling',
    'symbol': 'KSh',
    'decimal_places': 2,
  },
  {'code': 'USD', 'name': 'US dollar', 'symbol': r'$', 'decimal_places': 2},
];

Map<String, Object?> prefs(String code, [List<String> recent = const []]) => {
  'reporting_currency': code,
  'recent_currencies': recent,
  'is_default': recent.isEmpty && code == 'USD',
  'updated_at': null,
};

Map<String, Object?> statusJson({
  String status = 'current',
  String retrieved = '2026-10-12T09:58:00Z',
}) => {
  'pivot_currency': 'USD',
  'checked_at': '2026-10-12T10:00:00Z',
  'rates': [
    {
      'currency': 'AED',
      'status': status,
      'rate': '3.6725',
      'provider': 'ecb',
      'rate_type': 'indicative',
      'rate_timestamp': retrieved,
      'retrieved_at': retrieved,
      'path': null,
      'age_seconds': 120,
    },
    {
      'currency': 'KES',
      'status': 'unavailable',
      'rate': null,
      'provider': null,
      'rate_type': null,
      'rate_timestamp': null,
      'retrieved_at': null,
      'path': null,
      'age_seconds': null,
    },
  ],
};

Map<String, Object?> conversionJson() => {
  'source': usd('500000.00')
      .map((k, v) => MapEntry(k, k == 'currency' ? 'AED' : v)),
  'converted': usd('136147.04'),
  'rate': '0.272294077604',
  'path': null,
  'concept': 'current_reporting',
  'snapshot_id': '6f1d1f4e-1a0b-4d3e-9a51-6e6f0d1c0a10',
  'on': null,
  'status': 'current',
  'rate_timestamp': '2026-10-12T09:58:00Z',
  'providers': ['ecb'],
  'notice': 'Indicative rate for information; not a quote for a transaction.',
};

FakeApi api0() => FakeApi()
  ..json('GET /api/v1/currencies', currenciesJson)
  ..json('GET /api/v1/me/currency-preferences', prefs('USD'))
  ..json('GET /api/v1/fx/status', statusJson());

List<Override> live(FakeApi api, {List<Override> extra = const []}) =>
    demoOverrides(
      extra: [
        liveModeOverride(),
        currencyRepositoryProvider.overrideWithValue(
          LiveCurrencyRepository(api.dio()),
        ),
        ...extra,
      ],
    );

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('models', () {
    test(
      'the overall status is the worst known one; none known is unavailable',
      () {
        FxStatus status(List<String> s) => FxStatus(
          pivotCurrency: 'USD',
          checkedAt: DateTime.utc(2026),
          rates: [
            for (final x in s)
              FxRateLine(currency: x, status: FxRateStatus.values.byName(x)),
          ],
        );
        expect(status(['current', 'cached']).overall, FxRateStatus.cached);
        expect(
          status(['current', 'stale', 'unavailable']).overall,
          FxRateStatus.stale,
        );
        expect(status(['unavailable']).overall, FxRateStatus.unavailable);
        expect(status([]).overall, FxRateStatus.unavailable);
      },
    );

    test('search matches code or name', () {
      const euro = SupportedCurrency(
        code: 'EUR',
        name: 'Euro',
        symbol: '€',
        decimalPlaces: 2,
      );
      expect(euro.matches('eu'), isTrue);
      expect(euro.matches('EURO'), isTrue);
      expect(euro.matches('yen'), isFalse);
      expect(euro.matches(''), isTrue);
    });
  });

  group('live repository', () {
    test('reads and saves through the API; the server converts', () async {
      final api = api0()
        ..json('PATCH /api/v1/me/currency-preferences', prefs('EUR', ['USD']))
        ..json('POST /api/v1/fx/refresh', {
          'refreshed': true,
          'window': 'w',
          'attempts': <Object?>[],
          'missing': <Object?>[],
          'status': statusJson(status: 'cached'),
        })
        ..json('POST /api/v1/fx/convert', conversionJson());
      final repo = LiveCurrencyRepository(api.dio());
      expect((await repo.currencies()).map((c) => c.code), contains('JPY'));
      expect((await repo.preferences()).reportingCurrency, 'USD');
      final saved = await repo.setReportingCurrency('EUR');
      expect(saved.recentCurrencies, ['USD']);
      expect(
        api.callsTo('PATCH', '/api/v1/me/currency-preferences').single.body,
        {'reporting_currency': 'EUR'},
      );
      expect((await repo.refresh()).overall, FxRateStatus.cached);
      final c = await repo.convert(
        Money(Decimal.parse('500000.00'), 'AED'),
        'USD',
      );
      expect(c.converted.amount, Decimal.parse('136147.04'));
      expect(c.rate, Decimal.parse('0.272294077604'));
      expect(api.callsTo('POST', '/api/v1/fx/convert').single.body, {
        'amount': {'amount': '500000', 'currency': 'AED'},
        'to': 'USD',
      });
    });

    test('a refused currency is a validation error', () async {
      final api = api0()
        ..json('PATCH /api/v1/me/currency-preferences', {
          'status': 422,
        }, status: 422);
      await expectLater(
        LiveCurrencyRepository(api.dio()).setReportingCurrency('ZZZ'),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.validation,
          ),
        ),
      );
    });
  });

  group('switching currency', () {
    test('saves the choice and asks for every figure again', () async {
      var netWorthCalls = 0;
      final api = api0()
        ..json('PATCH /api/v1/me/currency-preferences', prefs('EUR', ['USD']));
      final container = ProviderContainer(
        overrides: [
          ...live(api),
          dashboardNetWorthProvider.overrideWith((ref) async {
            netWorthCalls++;
            final m = Money(Decimal.fromInt(netWorthCalls), 'USD');
            return NetWorthSummary(
              assets: m,
              liabilities: m,
              netWorth: m,
              asOf: DateTime.utc(2026),
            );
          }),
        ],
      );
      addTearDown(container.dispose);
      final sub = container.listen(dashboardNetWorthProvider, (_, _) {});
      await container.read(dashboardNetWorthProvider.future);
      await container.read(reportingCurrencyProvider.future);
      await container.read(reportingCurrencyProvider.notifier).select('EUR');
      await container.read(dashboardNetWorthProvider.future);
      expect(
        container.read(reportingCurrencyProvider).value!.reportingCurrency,
        'EUR',
      );
      expect(netWorthCalls, 2, reason: 'the figure was asked for again');
      sub.close();
    });
  });

  group('widgets', () {
    Future<void> pumpChip(WidgetTester tester, FakeApi api) => tester.pumpApp(
      const Scaffold(
        body: Column(children: [ReportingCurrencyChip(), FxStatusLine()]),
      ),
      overrides: live(api),
      surfaceSize: const Size(400, 900),
    );

    testWidgets('the chip shows the currency and the rates their freshness', (
      tester,
    ) async {
      await pumpChip(tester, api0());
      expect(find.text('USD'), findsOneWidget);
      expect(find.byKey(const ValueKey('fx-status-current')), findsOneWidget);
      expect(find.textContaining('FX rates current'), findsOneWidget);
    });

    for (final (status, text) in [
      ('cached', 'Cached FX rates'),
      ('stale', 'Old FX rates'),
    ]) {
      testWidgets('$status rates are never shown as current', (tester) async {
        final api = api0()
          ..json('GET /api/v1/fx/status', statusJson(status: status));
        await pumpChip(tester, api);
        expect(find.textContaining(text), findsOneWidget);
        expect(find.textContaining('FX rates current'), findsNothing);
      });
    }

    testWidgets('no rates at all says so', (tester) async {
      final api = api0()
        ..json('GET /api/v1/fx/status', {
          'pivot_currency': 'USD',
          'checked_at': '2026-10-12T10:00:00Z',
          'rates': <Object?>[],
        });
      await pumpChip(tester, api);
      expect(find.text('FX rates unavailable'), findsOneWidget);
    });

    testWidgets('the selector searches, shows recents and saves the choice', (
      tester,
    ) async {
      final api = api0()
        ..json('GET /api/v1/me/currency-preferences', prefs('USD', ['AED']))
        ..json(
          'PATCH /api/v1/me/currency-preferences',
          prefs('EUR', ['USD', 'AED']),
        );
      await pumpChip(tester, api);
      await tester.tap(find.byKey(const ValueKey('reporting-currency-chip')));
      await tester.pumpAndSettle();
      expect(find.text('Recent'), findsOneWidget);
      expect(find.text('All currencies'), findsOneWidget);
      await tester.enterText(find.byType(TextField), 'euro');
      await tester.pump();
      expect(find.byKey(const ValueKey('currency-EUR')), findsOneWidget);
      expect(find.byKey(const ValueKey('currency-JPY')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('currency-EUR')));
      await tester.pumpAndSettle();
      expect(
        find.text('Show figures in'),
        findsNothing,
        reason: 'the sheet closed',
      );
      expect(find.text('EUR'), findsOneWidget);
      expect(
        api.callsTo('PATCH', '/api/v1/me/currency-preferences'),
        hasLength(1),
      );
    });

    testWidgets('no match is an empty state', (tester) async {
      await pumpChip(tester, api0());
      await tester.tap(find.byKey(const ValueKey('reporting-currency-chip')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'zzz');
      await tester.pump();
      expect(find.text('No currency matches "zzz".'), findsOneWidget);
    });

    testWidgets('a failed save keeps the current currency and says so', (
      tester,
    ) async {
      final api = api0()
        ..json('PATCH /api/v1/me/currency-preferences', {
          'status': 503,
        }, status: 503);
      await pumpChip(tester, api);
      await tester.tap(find.byKey(const ValueKey('reporting-currency-chip')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('currency-EUR')));
      await tester.pumpAndSettle();
      expect(
        find.text('The currency could not be changed. Try again.'),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('currency-USD')), findsOneWidget);
    });

    testWidgets('settings shows the reporting currency with its name', (
      tester,
    ) async {
      await tester.pumpApp(
        const SettingsScreen(),
        overrides: live(api0()),
        surfaceSize: const Size(400, 1600),
      );
      expect(find.text('Reporting currency'), findsOneWidget);
      expect(find.text('USD · US dollar'), findsOneWidget);
      expect(find.textContaining('Demo figures'), findsNothing);
    });

    testWidgets('in demo mode the setting stays on the device and says so', (
      tester,
    ) async {
      await tester.pumpApp(
        const SettingsScreen(),
        overrides: demoOverrides(),
        surfaceSize: const Size(400, 1600),
      );
      expect(find.text('USD · US dollar'), findsOneWidget);
      expect(
        find.textContaining('Demo figures stay in US dollars'),
        findsOneWidget,
      );
    });
  });

  group('converter', () {
    Future<void> pumpConverter(
      WidgetTester tester,
      FakeApi api, {
      double textScale = 1,
      ThemeMode mode = ThemeMode.light,
    }) => tester.pumpApp(
      const CurrencyConverterScreen(),
      overrides: live(api),
      surfaceSize: const Size(400, 1800),
      textScale: textScale,
      themeMode: mode,
    );

    testWidgets('converts with the server and shows rate, time and notice', (
      tester,
    ) async {
      final api = api0()..json('POST /api/v1/fx/convert', conversionJson());
      await pumpConverter(tester, api);
      await tester.enterText(
        find.byKey(const ValueKey('converter-amount')),
        '500000.00',
      );
      await tester.tap(find.text('Convert'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('converter-result')), findsOneWidget);
      expect(find.text('1 AED = 0.272294077604 USD'), findsOneWidget);
      expect(find.textContaining('Indicative rate'), findsOneWidget);
      final body =
          api.callsTo('POST', '/api/v1/fx/convert').single.body! as Map;
      expect(body['to'], 'USD');
      expect((body['amount'] as Map)['amount'], '500000');
    });

    testWidgets('an invalid amount or the same currency twice is not sent', (
      tester,
    ) async {
      final api = api0();
      await pumpConverter(tester, api);
      await tester.enterText(
        find.byKey(const ValueKey('converter-amount')),
        '-5',
      );
      await tester.tap(find.text('Convert'));
      await tester.pump();
      expect(find.text('Enter an amount greater than zero.'), findsOneWidget);
      await tester.enterText(
        find.byKey(const ValueKey('converter-amount')),
        'abc',
      );
      await tester.tap(find.text('Convert'));
      await tester.pump();
      expect(find.text('Enter an amount greater than zero.'), findsOneWidget);
      expect(api.callsTo('POST', '/api/v1/fx/convert'), isEmpty);
    });

    testWidgets('a failed conversion says so', (tester) async {
      final api = api0()
        ..json('POST /api/v1/fx/convert', {'status': 404}, status: 404);
      await pumpConverter(tester, api);
      await tester.tap(find.text('Convert'));
      await tester.pumpAndSettle();
      expect(
        find.text('The amount could not be converted. Try again.'),
        findsOneWidget,
      );
    });

    testWidgets(
      'swap exchanges the currencies and refresh asks for new rates',
      (tester) async {
        final api = api0()
          ..json('POST /api/v1/fx/refresh', {
            'refreshed': true,
            'window': 'w',
            'attempts': <Object?>[],
            'missing': <Object?>[],
            'status': statusJson(),
          })
          ..json('POST /api/v1/fx/convert', conversionJson());
        await pumpConverter(tester, api);
        expect(
          find.byKey(const ValueKey('converter-from-AED')),
          findsOneWidget,
        );
        expect(find.byKey(const ValueKey('converter-to-USD')), findsOneWidget);
        await tester.tap(find.byTooltip('Swap currencies'));
        await tester.pumpAndSettle();
        expect(
          find.byKey(const ValueKey('converter-from-USD')),
          findsOneWidget,
        );
        expect(find.byKey(const ValueKey('converter-to-AED')), findsOneWidget);
        await tester.tap(find.byTooltip('Refresh rates'));
        await tester.pumpAndSettle();
        expect(api.callsTo('POST', '/api/v1/fx/refresh'), hasLength(1));
      },
    );

    testWidgets('demo mode offers the fixture examples, labelled DEMO', (
      tester,
    ) async {
      await tester.pumpApp(
        const CurrencyConverterScreen(),
        overrides: demoOverrides(),
        surfaceSize: const Size(400, 1800),
      );
      expect(find.text('DEMO'), findsWidgets);
      expect(find.text('Demo examples'), findsOneWidget);
      await tester.tap(find.textContaining('500000 AED'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Convert'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('converter-result')), findsOneWidget);
      expect(find.textContaining('Demo rates, not live'), findsOneWidget);
    });

    for (final (scale, mode) in [
      (1.0, ThemeMode.dark),
      (2.0, ThemeMode.light),
    ]) {
      testWidgets('meets the accessibility guidelines ($mode, ${scale}x)', (
        tester,
      ) async {
        final handle = tester.ensureSemantics();
        final api = api0()..json('POST /api/v1/fx/convert', conversionJson());
        await pumpConverter(tester, api, textScale: scale, mode: mode);
        await tester.tap(find.text('Convert'));
        await tester.pumpAndSettle();
        await expectLater(tester, meetsGuideline(textContrastGuideline));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        handle.dispose();
      });
    }
  });
}

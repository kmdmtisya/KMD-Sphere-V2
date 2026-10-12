import 'package:decimal/decimal.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/token_manager.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';
import 'package:wealthsphere_app/core/network/api_client.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';
import 'package:wealthsphere_app/core/network/asset_class_names.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/features/dashboard/data/dashboard_repository.dart';
import 'package:wealthsphere_app/features/dashboard/data/live_dashboard_repository.dart';
import 'package:wealthsphere_app/features/dashboard/domain/dashboard_layout.dart';
import 'package:wealthsphere_app/features/portfolios/data/live_portfolio_repository.dart';
import 'package:wealthsphere_app/shared/design_system/components/period_selector.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/auth_fakes.dart';

const config = AppConfig(
  apiBaseUrl: 'http://127.0.0.1:8000',
  oidcIssuer: 'http://127.0.0.1:8081/realms/wealthsphere',
);

Map<String, String> money(String amount, [String currency = 'USD']) => {
  'amount': amount,
  'currency': currency,
};

const stamp = '2026-10-12T10:00:00Z';
final now = DateTime.utc(2026, 10, 12, 12);

Map<String, Object?> summaryJson({
  bool complete = true,
  List<Object?> unpriced = const [],
  List<Object?> stale = const [],
}) => {
  'portfolio_ids': ['p1'],
  'currency': 'USD',
  'total_value': money('12345.67'),
  'holdings_value': money('10000.00'),
  'cash': money('2345.67'),
  'net_contributions': money('10000.00'),
  'unpriced_assets': unpriced,
  'freshness': {
    'computed_at': stamp,
    'data_as_of': '2026-10-12T09:30:00Z',
    'stale_prices': stale,
    'stale_fx': <Object?>[],
    'unconverted_currencies': <Object?>[],
    'complete': complete,
  },
};

Map<String, Object?> performanceJson({String? returnPercent = '23.46'}) => {
  'portfolio_id': 'p1',
  'currency': 'USD',
  'as_of': stamp,
  'profit_loss': money('2345.67'),
  'return_percent': returnPercent,
};

Map<String, Object?> riskJson() => {
  'currency': 'USD',
  'as_of': stamp,
  'points': [
    {'on': '2026-09-01', 'value': money('10000.00'), 'complete': true},
    {'on': '2026-09-15', 'value': money('0.00'), 'complete': false},
    {'on': '2026-10-01', 'value': money('12000.50'), 'complete': true},
  ],
  'time_weighted_annualized_percent': '8.10',
  'volatility_percent': '12.34',
};

void main() {
  late FakeAdapter api;
  late LivePortfolioRepository portfolios;
  late LiveDashboardRepository dashboard;

  setUp(() {
    api = FakeAdapter();
    final manager = TokenManager(
      store: InMemoryTokenStore(tokens('a')),
      client: FakeOidcClient(),
      clock: () => epoch,
    );
    final dio = buildApiClient(config: config, tokens: manager, adapter: api);
    portfolios = LivePortfolioRepository(
      dio,
      AssetClassNames(dio),
      clock: () => now,
    );
    dashboard = LiveDashboardRepository(dio);
  });

  List<String> paths() => [for (final s in api.sent) s.options.uri.path];

  group('portfolio summary', () {
    test(
      'shows the server figures exactly and asks for nothing else',
      () async {
        api.replies.addAll([
          reply(200, summaryJson()),
          reply(200, performanceJson()),
          reply(200, {'id': 'p1', 'name': 'Retirement'}),
        ]);
        final s = await portfolios.summary('p1');
        expect(s.value.amount, Decimal.parse('12345.67'));
        expect(s.invested.amount, Decimal.parse('10000.00'));
        expect(s.profitLoss!.amount, Decimal.parse('2345.67'));
        expect(s.returnPercent, Decimal.parse('23.46'));
        expect(s.name, 'Retirement');
        expect(s.baseCurrency, 'USD');
        expect(s.asOf, DateTime.utc(2026, 10, 12, 9, 30));
        expect(s.complete, isTrue);
        expect(
          paths(),
          containsAll([
            '/api/v1/portfolios/p1/summary',
            '/api/v1/portfolios/p1/performance',
            '/api/v1/portfolios/p1',
          ]),
        );
      },
    );

    test('profit and return the server did not supply stay empty', () async {
      api.replies.addAll([
        reply(200, summaryJson()),
        reply(200, performanceJson(returnPercent: null)),
        reply(200, {'id': 'p1', 'name': 'Retirement'}),
      ]);
      final s = await portfolios.summary('p1');
      expect(s.returnPercent, isNull);
      expect(s.profitLoss, isNotNull);
    });

    test('unpriced assets and stale prices are carried through', () async {
      api.replies.addAll([
        reply(
          200,
          summaryJson(
            complete: false,
            unpriced: [
              {'id': 'a'},
              {'id': 'b'},
            ],
            stale: [
              {'id': 'c'},
            ],
          ),
        ),
        reply(200, performanceJson()),
        reply(200, {'id': 'p1', 'name': 'Retirement'}),
      ]);
      final s = await portfolios.summary('p1');
      expect(s.complete, isFalse);
      expect(s.unpricedAssetCount, 2);
      expect(s.stalePriceCount, 1);
    });

    test('all portfolios use the server consolidated summary only', () async {
      api.replies.add(reply(200, summaryJson()));
      final s = await portfolios.summary(PortfolioRef.consolidatedId);
      expect(paths(), ['/api/v1/portfolios/consolidated/summary']);
      expect(s.name, 'All portfolios');
      expect(
        s.profitLoss,
        isNull,
        reason: 'the app does not add portfolios up',
      );
      expect(s.returnPercent, isNull);
    });

    test('a failure reaches the caller as an ApiException', () async {
      api.replies.addAll([reply(404), reply(404), reply(404)]);
      await expectLater(
        portfolios.summary('missing'),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.notFound,
          ),
        ),
      );
    });
  });

  group('portfolios list', () {
    test('maps the list', () async {
      api.replies.add(
        reply(200, [
          {'id': 'p1', 'name': 'Retirement', 'base_currency': 'USD'},
          {'id': 'p2', 'name': 'Growth', 'base_currency': 'EUR'},
        ]),
      );
      final list = await portfolios.portfolios();
      expect([for (final p in list) p.name], ['Retirement', 'Growth']);
    });
  });

  group('performance series', () {
    test('skips incomplete points and asks for the right window', () async {
      api.replies.add(reply(200, riskJson()));
      final series = await portfolios.performance('p1', ChartPeriod.month);
      expect(
        [for (final p in series.points) p.value],
        [Decimal.parse('10000.00'), Decimal.parse('12000.50')],
      );
      expect(series.currencyCode, 'USD');
      final query = api.sent.single.options.uri.queryParameters;
      expect(query['frequency'], 'daily');
      expect(query['start'], '2026-09-12');
    });

    test('all history is monthly with no start date', () async {
      api.replies.add(reply(200, riskJson()));
      await portfolios.performance('p1', ChartPeriod.all);
      final query = api.sent.single.options.uri.queryParameters;
      expect(query['frequency'], 'monthly');
      expect(query.containsKey('start'), isFalse);
    });

    test('year to date starts on 1 January', () async {
      api.replies.add(reply(200, riskJson()));
      await portfolios.performance('p1', ChartPeriod.yearToDate);
      expect(
        api.sent.single.options.uri.queryParameters['start'],
        '2026-01-01',
      );
    });

    test('all portfolios have no series yet and make no request', () async {
      final series = await portfolios.performance(
        PortfolioRef.consolidatedId,
        ChartPeriod.month,
      );
      expect(series.points, isEmpty);
      expect(api.sent, isEmpty);
    });
  });

  group('allocation', () {
    Map<String, Object?> allocation(List<Map<String, Object?>> slices) => {
      'portfolio_id': 'p1',
      'asset_class': {'slices': slices, 'hhi': '4000.00'},
    };

    test('uses the server class names and weights', () async {
      api.replies.addAll([
        reply(200, [
          {
            'code': 'stock',
            'name': 'Stocks',
            'valuation_mode': 'market',
            'metadata_fields': <String, Object?>{},
          },
        ]),
        reply(
          200,
          allocation([
            {
              'key': 'stock',
              'value': money('7000.00'),
              'weight_percent': '70.00',
              'parts': 2,
            },
            {
              'key': 'mystery',
              'value': money('3000.00'),
              'weight_percent': '30.00',
              'parts': 1,
            },
          ]),
        ),
      ]);
      final shares = await portfolios.allocation('p1');
      expect([for (final s in shares) s.label], ['Stocks', 'mystery']);
      expect(shares.first.weightPercent, Decimal.parse('70.00'));
    });

    test('a slice with no weight is left out, not guessed', () async {
      api.replies.addAll([
        reply(200, <Object?>[]),
        reply(
          200,
          allocation([
            {
              'key': 'stock',
              'value': money('0.00'),
              'weight_percent': null,
              'parts': 0,
            },
          ]),
        ),
      ]);
      expect(await portfolios.allocation('p1'), isEmpty);
    });

    test('all portfolios have no allocation yet', () async {
      expect(await portfolios.allocation(PortfolioRef.consolidatedId), isEmpty);
    });
  });

  group('metrics', () {
    test('takes each figure from the endpoint that computes it', () async {
      api.replies.addAll([
        reply(200, performanceJson()),
        reply(200, riskJson()),
        reply(200, {'as_of': stamp, 'portfolio_yield_percent': '2.50'}),
      ]);
      final m = await portfolios.metrics('p1');
      expect(m.totalReturnPercent, Decimal.parse('23.46'));
      expect(m.cagrPercent, Decimal.parse('8.10'));
      expect(m.volatilityPercent, Decimal.parse('12.34'));
      expect(m.dividendYieldPercent, Decimal.parse('2.50'));
    });

    test('a figure the server could not compute stays empty', () async {
      api.replies.addAll([
        reply(200, performanceJson(returnPercent: null)),
        reply(200, {...riskJson(), 'volatility_percent': null}),
        reply(200, {'as_of': stamp, 'portfolio_yield_percent': null}),
      ]);
      final m = await portfolios.metrics('p1');
      expect(m.totalReturnPercent, isNull);
      expect(m.volatilityPercent, isNull);
      expect(m.dividendYieldPercent, isNull);
    });

    test('all portfolios have no metrics yet', () async {
      final m = await portfolios.metrics(PortfolioRef.consolidatedId);
      expect(m.totalReturnPercent, isNull);
      expect(api.sent, isEmpty);
    });
  });

  group('holdings', () {
    Map<String, Object?> holding(
      String name, {
      String? symbol,
      Map<String, String>? value,
      bool? stale,
    }) => {
      'asset': {
        'id': 'asset-$name',
        'asset_class': 'stock',
        'symbol': symbol,
        'name': name,
        'currency': 'USD',
        'is_custom': symbol == null,
      },
      'quantity': '10',
      'value': value,
      'native_value': value,
      'value_as_of': value == null ? null : stamp,
      'value_source': value == null ? null : 'price',
      'value_stale': stale,
    };

    test('maps priced, unpriced and custom assets', () async {
      api.replies.addAll([
        reply(200, [
          {
            'code': 'stock',
            'name': 'Stocks',
            'valuation_mode': 'market',
            'metadata_fields': <String, Object?>{},
          },
        ]),
        reply(200, [
          holding('Acme', symbol: 'ACM', value: money('1000.00'), stale: true),
          holding('My flat'),
        ]),
      ]);
      final list = await portfolios.holdings('p1');
      expect(list.first.symbol, 'ACM');
      expect(list.first.assetClass, 'Stocks');
      expect(list.first.value!.amount, Decimal.parse('1000.00'));
      expect(list.first.valueStale, isTrue);
      expect(list.first.detailKey, 'asset-Acme');
      expect(list.last.symbol, isNull);
      expect(list.last.value, isNull, reason: 'unpriced is not zero');
    });

    test('all portfolios list every portfolio\'s holdings', () async {
      api.replies.addAll([
        reply(200, [
          {'id': 'p1', 'name': 'A', 'base_currency': 'USD'},
          {'id': 'p2', 'name': 'B', 'base_currency': 'EUR'},
        ]),
        reply(200, <Object?>[]),
        reply(200, [holding('One', symbol: 'ONE', value: money('5.00'))]),
        reply(200, [
          holding('Two', symbol: 'TWO', value: money('6.00', 'EUR')),
        ]),
      ]);
      final list = await portfolios.holdings(PortfolioRef.consolidatedId);
      expect([for (final h in list) h.symbol], ['ONE', 'TWO']);
    });
  });

  group('dashboard', () {
    test('net worth, income and goals are the server summaries', () async {
      api.replies.addAll([
        reply(200, {
          'currency': 'USD',
          'assets': money('100.00'),
          'liabilities': money('40.00'),
          'net_worth': money('60.00'),
          'as_of': stamp,
        }),
        reply(200, {
          'currency': 'USD',
          'monthly': money('10.00'),
          'yearly': money('120.00'),
          'as_of': stamp,
        }),
        reply(200, {
          'on_track': 1,
          'total': 2,
          'as_of': stamp,
          'notice': 'Estimates under stated assumptions',
          'items': [
            {
              'id': 'g1',
              'name': 'House',
              'progress_percent': '40.00',
              'status': 'on_track',
              'reached': false,
              'target': money('1000.00'),
              'target_date': '2030-01-01',
            },
          ],
        }),
      ]);
      final nw = await dashboard.netWorth();
      final income = await dashboard.income();
      final goals = await dashboard.goals();
      expect(nw.netWorth.amount, Decimal.parse('60.00'));
      expect(income.yearly.amount, Decimal.parse('120.00'));
      expect(goals.onTrack, 1);
      expect(goals.items.single.name, 'House');
      expect(paths(), [
        '/api/v1/net-worth',
        '/api/v1/income/summary',
        '/api/v1/goals/summary',
      ]);
    });

    test('there is no insight until the AI service exists', () async {
      expect(await dashboard.insight(), isNull);
      expect(api.sent, isEmpty);
    });

    test('the greeting uses the display name, then the email', () async {
      api.replies.addAll([
        reply(200, {'display_name': ' Amina ', 'email': 'a@example.test'}),
        reply(200, {'display_name': null, 'email': 'sam@example.test'}),
        reply(200, {'display_name': null, 'email': null}),
      ]);
      expect(await dashboard.greetingName(), 'Amina');
      expect(await dashboard.greetingName(), 'sam');
      expect(await dashboard.greetingName(), 'there');
    });
  });

  group('dashboard layout sync', () {
    late InMemoryPreferencesStore store;
    late SyncedDashboardLayoutRepository synced;

    setUp(() {
      store = InMemoryPreferencesStore();
      final manager = TokenManager(
        store: InMemoryTokenStore(tokens('a')),
        client: FakeOidcClient(),
        clock: () => epoch,
      );
      synced = SyncedDashboardLayoutRepository(
        buildApiClient(config: config, tokens: manager, adapter: api),
        LocalDashboardLayoutRepository(store),
      );
    });

    Map<String, Object?> me(Map<String, Object?>? layout) => {
      'id': 'u1',
      'preferences': {'dashboard_layout': layout, 'theme_mode': null},
    };

    test('the account layout wins and is kept on the device', () async {
      api.replies.add(
        reply(
          200,
          me({
            'order': ['goals', 'wealthSummary'],
            'hidden': ['insight'],
          }),
        ),
      );
      final layout = await synced.load();
      expect(layout.order.first, DashboardSection.goals);
      expect(layout.hidden, {DashboardSection.insight});
      final onDevice = await LocalDashboardLayoutRepository(store).load();
      expect(onDevice, layout);
    });

    test('with no account layout the device layout is used', () async {
      final mine = DashboardLayout.initial().move(DashboardSection.goals, -3);
      await LocalDashboardLayoutRepository(store).save(mine);
      api.replies.add(reply(200, me(null)));
      expect(await synced.load(), mine);
    });

    test('offline shows the device layout', () async {
      final mine = DashboardLayout.initial().move(DashboardSection.metrics, 1);
      await LocalDashboardLayoutRepository(store).save(mine);
      api.replies.add(DioExceptionType.connectionError);
      expect(await synced.load(), mine);
    });

    test('saving writes the device first, then the account', () async {
      api.replies.add(reply(200, me(null)));
      final next = DashboardLayout.initial().withVisibility(
        DashboardSection.insight,
        visible: false,
      );
      await synced.save(next);
      expect(await LocalDashboardLayoutRepository(store).load(), next);
      final sent = api.sent.single;
      expect(sent.options.method, 'PATCH');
      expect(sent.options.uri.path, '/api/v1/me/preferences');
      expect(sent.body, contains('"hidden":["insight"]'));
      expect(sent.body, contains('"wealthSummary"'));
    });

    test('a failed sync keeps the device layout and does not throw', () async {
      api.replies.add(DioExceptionType.connectionError);
      final next = DashboardLayout.initial().withVisibility(
        DashboardSection.goals,
        visible: false,
      );
      await synced.save(next);
      expect(await LocalDashboardLayoutRepository(store).load(), next);
    });
  });
}

import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/network/asset_class_names.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/features/dashboard/data/dashboard_repository.dart';
import 'package:wealthsphere_app/features/dashboard/data/live_dashboard_repository.dart';
import 'package:wealthsphere_app/features/dashboard/presentation/home_screen.dart';
import 'package:wealthsphere_app/features/portfolios/data/live_portfolio_repository.dart';
import 'package:wealthsphere_app/features/portfolios/data/portfolio_repository.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';

/// Answers each path with a canned JSON body, whatever the order of the requests.
class _PathAdapter implements HttpClientAdapter {
  _PathAdapter(this.bodies);

  final Map<String, Object?> bodies;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final body = bodies[options.uri.path];
    return ResponseBody.fromString(
      body == null ? '{"title":"Not found"}' : jsonEncode(body),
      body == null ? 404 : 200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Map<String, String> m(String amount) => {'amount': amount, 'currency': 'USD'};

const stamp = '2026-10-12T09:30:00Z';

void main() {
  testWidgets(
    'Home in live mode shows the backend numbers exactly, with the data-quality notice',
    (tester) async {
      final dio = Dio(BaseOptions(baseUrl: 'http://api.test'))
        ..httpClientAdapter = _PathAdapter({
          '/api/v1/me': {'display_name': 'Amina', 'email': null},
          '/api/v1/portfolios/consolidated/summary': {
            'portfolio_ids': ['p1'],
            'currency': 'USD',
            'total_value': m('12345.67'),
            'net_contributions': m('10000.00'),
            'unpriced_assets': [
              {'id': 'x'},
            ],
            'freshness': {
              'data_as_of': stamp,
              'stale_prices': [
                {'id': 'y'},
                {'id': 'z'},
              ],
              'complete': false,
            },
          },
          '/api/v1/net-worth': {
            'assets': m('15000.00'),
            'liabilities': m('2654.33'),
            'net_worth': m('12345.67'),
            'as_of': stamp,
          },
          '/api/v1/income/summary': {
            'monthly': m('100.00'),
            'yearly': m('1200.00'),
            'as_of': stamp,
          },
          '/api/v1/goals/summary': {
            'on_track': 0,
            'total': 0,
            'items': <Object?>[],
            'as_of': stamp,
            'notice': 'Estimates',
          },
        });
      await tester.pumpApp(
        const HomeScreen(),
        overrides: [
          liveModeOverride(),
          dashboardRepositoryProvider.overrideWithValue(
            LiveDashboardRepository(dio),
          ),
          portfolioRepositoryProvider.overrideWithValue(
            LivePortfolioRepository(dio, AssetClassNames(dio)),
          ),
          preferencesStoreProvider.overrideWithValue(
            InMemoryPreferencesStore(),
          ),
        ],
        surfaceSize: const Size(400, 2600),
      );
      expect(find.text('Hello, Amina'), findsOneWidget);
      expect(
        find.text(r'$12,345.67'),
        findsWidgets,
        reason: 'total and net worth',
      );
      expect(
        find.textContaining('may be incomplete'),
        findsOneWidget,
        reason: 'the total does not cover every asset',
      );
      expect(find.textContaining('2 prices are out of date'), findsOneWidget);
      expect(
        find.text('AI insight'),
        findsNothing,
        reason: 'no invented insight',
      );
    },
  );
}

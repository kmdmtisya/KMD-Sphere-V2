import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/network/asset_catalog.dart';
import 'package:wealthsphere_app/core/network/asset_class_names.dart';
import 'package:wealthsphere_app/features/investments/data/investment_repository.dart';
import 'package:wealthsphere_app/features/investments/data/live_investment_repository.dart';
import 'package:wealthsphere_app/features/investments/presentation/investment_detail_screen.dart';
import 'package:wealthsphere_app/features/portfolios/application/portfolio_providers.dart';
import 'package:wealthsphere_app/features/portfolios/data/live_portfolio_repository.dart';
import 'package:wealthsphere_app/features/portfolios/data/portfolio_repository.dart';
import 'package:wealthsphere_app/features/transactions/application/ledger_view.dart';
import 'package:wealthsphere_app/features/transactions/data/live_transaction_repository.dart';
import 'package:wealthsphere_app/features/transactions/data/transaction_repository.dart';
import 'package:wealthsphere_app/features/transactions/presentation/add_transaction_screen.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/fake_api.dart';
import '../../helpers/pump_app.dart';

final DateTime fixedToday = DateTime(2026, 10, 9, 12);

Map<String, Object?> summary(String total) => {
  'portfolio_ids': ['p1'],
  'currency': 'USD',
  'total_value': usd(total),
  'net_contributions': usd(total),
  'unpriced_assets': <Object?>[],
  'freshness': {
    'data_as_of': '2026-10-09T09:00:00Z',
    'stale_prices': <Object?>[],
    'complete': true,
  },
};

FakeApi backend() => FakeApi()
  ..json('GET /api/v1/portfolios', [
    {'id': 'p1', 'name': 'Retirement', 'base_currency': 'USD'},
  ])
  ..json('GET /api/v1/asset-classes', [
    {'code': 'stock', 'name': 'Stocks'},
  ])
  ..json('GET /api/v1/assets/a1/prices', {
    'asset_id': 'a1',
    'currency': 'USD',
    'latest': null,
    'points': <Object?>[],
  })
  ..json('GET /api/v1/assets/a1', {
    'id': 'a1',
    'symbol': 'ACM',
    'name': 'Acme Corp',
    'asset_class': 'stock',
    'asset_class_name': 'Stocks',
    'currency': 'USD',
  })
  ..json('GET /api/v1/portfolios/p1/holdings', [
    {
      'asset': {
        'id': 'a1',
        'asset_class': 'stock',
        'symbol': 'ACM',
        'name': 'Acme Corp',
        'currency': 'USD',
      },
      'quantity': '10',
      'average_cost': usd('100.00'),
      'cost_basis': usd('1000.00'),
      'value': null,
      'native_value': null,
      'value_as_of': null,
    },
  ])
  ..json('GET /api/v1/portfolios/p1/summary', summary('1000.00'))
  ..json('GET /api/v1/portfolios/p1', {'id': 'p1', 'name': 'Retirement'})
  ..json('GET /api/v1/portfolios/p1/performance', {
    'as_of': '2026-10-09T09:00:00Z',
    'profit_loss': usd('0.00'),
    'return_percent': null,
  });

List<Override> live(FakeApi api) {
  final Dio dio = api.dio();
  final portfolios = LivePortfolioRepository(dio, AssetClassNames(dio));
  final catalog = AssetCatalog(dio);
  return demoOverrides(
    extra: [
      liveModeOverride(),
      todayProvider.overrideWithValue(fixedToday),
      portfolioRepositoryProvider.overrideWithValue(portfolios),
      transactionRepositoryProvider.overrideWithValue(
        LiveTransactionRepository(
          dio,
          catalog,
          () async => [for (final p in await portfolios.portfolios()) p.id],
        ),
      ),
      investmentRepositoryProvider.overrideWithValue(
        LiveInvestmentRepository(dio, catalog, portfolios.portfolios),
      ),
    ],
  );
}

Future<void> choose(WidgetTester tester, String label, String option) async {
  await tester.tap(find.widgetWithText(DropdownButtonFormField<String>, label));
  await tester.pumpAndSettle();
  await tester.tap(find.text(option).last);
  await tester.pumpAndSettle();
}

Finder field(String label) => find.widgetWithText(TextField, label);

void main() {
  testWidgets(
    'a trade is posted once with one key, even after a failed first try',
    (tester) async {
      final api = backend();
      var posts = 0;
      api.on('POST /api/v1/portfolios/p1/transactions', (c) {
        posts++;
        if (posts == 1) return (503, {'title': 'Unavailable', 'status': 503});
        return (
          201,
          {
            'id': 't1',
            'portfolio_id': 'p1',
            'transaction_type': 'BUY',
            'trade_date': '2026-10-09',
            'asset_id': 'a1',
            'currency': 'USD',
            'quantity': '5',
            'unit_price': usd('190.10'),
            'gross_amount': usd('950.50'),
            'fees': usd('1.00'),
            'source': 'manual',
            'created_at': '2026-10-09T10:00:00Z',
          },
        );
      });
      await tester.pumpApp(
        const AddTransactionScreen(),
        overrides: live(api),
        surfaceSize: const Size(400, 2400),
      );
      await choose(tester, 'Portfolio', 'Retirement');
      await choose(tester, 'Investment', 'Acme Corp');
      await tester.tap(find.text('Select a date'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      await tester.enterText(field('Quantity'), '5');
      await tester.enterText(field('Price per unit'), '190.10');
      await tester.enterText(field('Fee (optional)'), '1.00');
      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save transaction'));
      await tester.pumpAndSettle();
      expect(find.textContaining('could not be saved'), findsOneWidget);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.text('Transaction recorded'), findsOneWidget);

      final sent = api.callsTo('POST', '/api/v1/portfolios/p1/transactions');
      expect(sent, hasLength(2));
      final key = sent.first.header('idempotency-key');
      expect(key, matches(RegExp(r'^[0-9a-f]{32}$')));
      expect(
        sent.last.header('idempotency-key'),
        key,
        reason: 'same entry, same key',
      );
      final body = sent.last.body! as Map<String, Object?>;
      expect(body['asset_id'], 'a1');
      expect(
        body.containsKey('gross_amount'),
        isFalse,
        reason: 'the server totals a trade',
      );
      // The figure shown is the server's total, not quantity x price worked out on the device.
      expect(find.textContaining('950.50'), findsWidgets);
    },
  );

  testWidgets(
    'after a ledger change the summaries are read again from the server',
    (tester) async {
      final api = backend();
      await tester.pumpApp(
        Consumer(
          builder: (context, ref, _) {
            final s = ref.watch(portfolioSummaryProvider('p1'));
            return Column(
              children: [
                Text(s.hasValue ? 'loaded' : 'loading'),
                TextButton(
                  onPressed: () => refreshLedger(ref),
                  child: const Text('changed'),
                ),
              ],
            );
          },
        ),
        overrides: live(api),
      );
      expect(api.callsTo('GET', '/api/v1/portfolios/p1/summary'), hasLength(1));
      await tester.tap(find.text('changed'));
      await tester.pumpAndSettle();
      expect(
        api.callsTo('GET', '/api/v1/portfolios/p1/summary'),
        hasLength(2),
        reason:
            'the server recomputes totals; the app never adjusts them itself',
      );
    },
  );

  testWidgets(
    'investment detail in live mode shows positions and no invented price',
    (tester) async {
      final api = backend();
      await tester.pumpApp(
        const InvestmentDetailScreen(symbol: 'a1'),
        overrides: live(api),
        surfaceSize: const Size(400, 2000),
      );
      expect(
        find.text('ACM'),
        findsWidgets,
        reason: 'title is the ticker, not the id',
      );
      expect(find.text('a1'), findsNothing);
      expect(find.text('No market price yet'), findsOneWidget);
      expect(find.text('DEMO'), findsNothing);
      await tester.tap(find.text('Position'));
      await tester.pumpAndSettle();
      expect(find.text('No value yet'), findsOneWidget);
      expect(
        find.text(r'$1,000.00'),
        findsOneWidget,
        reason: 'cost basis from the server',
      );
    },
  );
}

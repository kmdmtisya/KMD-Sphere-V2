import 'package:decimal/decimal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';
import 'package:wealthsphere_app/core/network/asset_catalog.dart';
import 'package:wealthsphere_app/features/investments/data/live_investment_repository.dart';
import 'package:wealthsphere_app/features/transactions/application/transaction_draft.dart';
import 'package:wealthsphere_app/features/transactions/data/live_transaction_repository.dart';
import 'package:wealthsphere_app/features/transactions/data/transaction_repository.dart';
import 'package:wealthsphere_app/shared/design_system/components/period_selector.dart';
import 'package:wealthsphere_app/shared/design_system/components/transaction_tile.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/fake_api.dart';

Map<String, Object?> tx(
  String id, {
  String portfolio = 'p1',
  String type = 'BUY',
  String? asset = 'a1',
  String gross = '1000.00',
  String fees = '0.00',
  String? reverses,
  String? reversedBy,
}) => {
  'id': id,
  'portfolio_id': portfolio,
  'transaction_type': type,
  'trade_date': '2026-10-01',
  'asset_id': asset,
  'currency': 'USD',
  'quantity': asset == null ? null : '10',
  'unit_price': asset == null ? null : usd('100.00'),
  'gross_amount': usd(gross),
  'fees': usd(fees),
  'taxes': usd('0.00'),
  'source': 'manual',
  'reverses_transaction_id': reverses,
  'reversed_by_transaction_id': reversedBy,
  'note': null,
  'created_at': '2026-10-01T10:00:00Z',
};

Map<String, Object?> asset(String id, {String? symbol = 'ACM'}) => {
  'id': id,
  'symbol': symbol,
  'name': 'Acme $id',
  'asset_class': 'stock',
  'asset_class_name': 'Stocks',
  'currency': 'USD',
};

Map<String, Object?> holding(String assetId, {String? value = '1200.00'}) => {
  'asset': {
    'id': assetId,
    'asset_class': 'stock',
    'symbol': 'ACM',
    'name': 'Acme',
    'currency': 'USD',
  },
  'quantity': '10',
  'average_cost': usd('100.00'),
  'cost_basis': usd('1000.00'),
  'value': value == null ? null : usd(value),
  'native_value': value == null ? null : usd(value),
  'value_as_of': value == null ? null : '2026-10-12T09:00:00Z',
};

void main() {
  late FakeApi api;
  late LiveTransactionRepository ledger;

  setUp(() {
    api = FakeApi()
      ..json('GET /api/v1/assets/a1', asset('a1'))
      ..json('GET /api/v1/assets/a2', asset('a2', symbol: null));
    final dio = api.dio();
    ledger = LiveTransactionRepository(
      dio,
      AssetCatalog(dio),
      () async => ['p1', 'p2'],
    );
  });

  group('ledger', () {
    test('follows the cursor and names each asset', () async {
      api.on('GET /api/v1/portfolios/p1/transactions', (c) {
        final second = c.query['cursor'] == 'next';
        return (
          200,
          {
            'items': [second ? tx('t2', asset: 'a2') : tx('t1')],
            'next_cursor': second ? null : 'next',
          },
        );
      });
      final entries = await ledger.entries('p1');
      expect([for (final e in entries) e.id], ['t1', 't2']);
      expect(entries.first.assetSymbol, 'ACM');
      expect(entries.first.assetName, 'Acme a1');
      expect(entries.first.assetId, 'a1');
      expect(entries.last.assetSymbol, isNull, reason: 'custom asset');
      expect(entries.first.gross.amount, Decimal.parse('1000.00'));
      expect(entries.first.fees, isNull, reason: 'zero fees shown as none');
      expect(api.callsTo('GET', '/api/v1/assets/a1'), hasLength(1));
      expect(
        api.callsTo('GET', '/api/v1/portfolios/p1/transactions').first.query,
        containsPair('limit', '100'),
      );
    });

    test('all portfolios join every portfolio ledger', () async {
      api
        ..json('GET /api/v1/portfolios/p1/transactions', {
          'items': [tx('t1')],
          'next_cursor': null,
        })
        ..json('GET /api/v1/portfolios/p2/transactions', {
          'items': [tx('t9', portfolio: 'p2', type: 'DEPOSIT', asset: null)],
          'next_cursor': null,
        });
      final all = await ledger.entries(PortfolioRef.consolidatedId);
      expect({for (final e in all) e.id}, {'t1', 't9'});
    });

    test('one entry is read from its own portfolio', () async {
      api
        ..json('GET /api/v1/portfolios/p1/transactions', {
          'items': <Object?>[],
          'next_cursor': null,
        })
        ..json('GET /api/v1/portfolios/p2/transactions', {
          'items': [tx('t9', portfolio: 'p2')],
          'next_cursor': null,
        })
        ..json(
          'GET /api/v1/portfolios/p2/transactions/t9',
          tx('t9', portfolio: 'p2'),
        );
      final e = await ledger.entry('t9');
      expect(e.portfolioId, 'p2');
      expect(
        api.callsTo('GET', '/api/v1/portfolios/p2/transactions/t9'),
        hasLength(1),
      );
    });

    test('an unknown entry is not found', () async {
      api
        ..json('GET /api/v1/portfolios/p1/transactions', {
          'items': <Object?>[],
          'next_cursor': null,
        })
        ..json('GET /api/v1/portfolios/p2/transactions', {
          'items': <Object?>[],
          'next_cursor': null,
        });
      await expectLater(
        ledger.entry('nope'),
        throwsA(
          isA<LedgerRuleException>().having(
            (e) => e.rule,
            'rule',
            LedgerRule.notFound,
          ),
        ),
      );
    });
  });

  group('adding', () {
    NewTransaction buy() => NewTransaction(
      kind: TransactionKind.buy,
      portfolioId: 'p1',
      currency: 'USD',
      date: DateTime(2026, 10, 1),
      assetId: 'a1',
      assetSymbol: 'ACM',
      quantity: Decimal.parse('10'),
      unitPrice: Decimal.parse('100.5'),
      fee: Decimal.parse('1.25'),
      idempotencyKey: 'k-123',
    );

    test(
      'a trade sends quantity and price; the server works out the total',
      () async {
        api.json(
          'POST /api/v1/portfolios/p1/transactions',
          tx('t1', gross: '1005.00', fees: '1.25'),
          status: 201,
        );
        final saved = await ledger.add(buy());
        final call = api
            .callsTo('POST', '/api/v1/portfolios/p1/transactions')
            .single;
        expect(call.header('idempotency-key'), 'k-123');
        final body = call.body! as Map<String, Object?>;
        expect(body['transaction_type'], 'BUY');
        expect(body['trade_date'], '2026-10-01');
        expect(body['asset_id'], 'a1');
        expect(body['quantity'], '10');
        expect(body['unit_price'], {'amount': '100.5', 'currency': 'USD'});
        expect(body['fees'], {'amount': '1.25', 'currency': 'USD'});
        expect(body.containsKey('gross_amount'), isFalse);
        expect(saved.gross.amount, Decimal.parse('1005.00'));
      },
    );

    test('a cash entry sends its amount and no asset', () async {
      api.json(
        'POST /api/v1/portfolios/p1/transactions',
        tx('t2', type: 'DEPOSIT', asset: null, gross: '500.00'),
        status: 201,
      );
      await ledger.add(
        NewTransaction(
          kind: TransactionKind.deposit,
          portfolioId: 'p1',
          currency: 'USD',
          date: DateTime(2026, 10, 1),
          amount: Decimal.parse('500'),
        ),
      );
      final post = api
          .callsTo('POST', '/api/v1/portfolios/p1/transactions')
          .single;
      final body = post.body! as Map<String, Object?>;
      expect(body['gross_amount'], {'amount': '500', 'currency': 'USD'});
      expect(body.containsKey('asset_id'), isFalse);
      expect(post.header('idempotency-key'), isNull);
    });

    test('a refused entry is a validation error', () async {
      api.json('POST /api/v1/portfolios/p1/transactions', {
        'title': 'Validation failed',
        'status': 422,
      }, status: 422);
      await expectLater(
        ledger.add(buy()),
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

  group('correcting', () {
    void ledgerWith(Map<String, Object?> entry) => api
      ..json('GET /api/v1/portfolios/p1/transactions', {
        'items': [entry],
        'next_cursor': null,
      })
      ..json('GET /api/v1/portfolios/p2/transactions', {
        'items': <Object?>[],
        'next_cursor': null,
      })
      ..json('GET /api/v1/portfolios/p1/transactions/${entry['id']}', entry);

    test('posts a linked reversal', () async {
      ledgerWith(tx('t1'));
      api.json(
        'POST /api/v1/portfolios/p1/transactions/t1/reversal',
        tx('r1', reverses: 't1'),
        status: 201,
      );
      final reversal = await ledger.reverse('t1', note: 'typo');
      expect(reversal.reversesId, 't1');
      expect(
        api
            .callsTo('POST', '/api/v1/portfolios/p1/transactions/t1/reversal')
            .single
            .body,
        {'note': 'typo'},
      );
    });

    test('an entry already reversed is refused without asking', () async {
      ledgerWith(tx('t1', reversedBy: 'r1'));
      await expectLater(
        ledger.reverse('t1'),
        throwsA(
          isA<LedgerRuleException>().having(
            (e) => e.rule,
            'rule',
            LedgerRule.alreadyReversed,
          ),
        ),
      );
      expect(
        api.callsTo('POST', '/api/v1/portfolios/p1/transactions/t1/reversal'),
        isEmpty,
      );
    });

    test('a reversal cannot be reversed', () async {
      ledgerWith(tx('r1', reverses: 't1'));
      await expectLater(
        ledger.reverse('r1'),
        throwsA(
          isA<LedgerRuleException>().having(
            (e) => e.rule,
            'rule',
            LedgerRule.isReversal,
          ),
        ),
      );
    });

    test(
      'a conflict from the server (reversed meanwhile) is reported as such',
      () async {
        ledgerWith(tx('t1'));
        api.json('POST /api/v1/portfolios/p1/transactions/t1/reversal', {
          'title': 'Conflict',
          'status': 409,
        }, status: 409);
        await expectLater(
          ledger.reverse('t1'),
          throwsA(
            isA<LedgerRuleException>().having(
              (e) => e.rule,
              'rule',
              LedgerRule.alreadyReversed,
            ),
          ),
        );
      },
    );
  });

  group('investment detail', () {
    late LiveInvestmentRepository investments;

    setUp(() {
      final dio = api.dio();
      investments = LiveInvestmentRepository(
        dio,
        AssetCatalog(dio),
        () async => const [
          PortfolioRef(id: 'p1', name: 'Retirement', baseCurrency: 'USD'),
          PortfolioRef(id: 'p2', name: 'Growth', baseCurrency: 'USD'),
        ],
        clock: () => DateTime.utc(2026, 10, 12),
      );
      for (final id in ['a1', 'a2']) {
        api.json('GET /api/v1/assets/$id/prices', {
          'asset_id': id,
          'currency': 'USD',
          'latest': null,
          'points': <Object?>[],
        });
      }
      api
        ..json('GET /api/v1/portfolios/p1/holdings', [
          holding('a1'),
          holding('zz'),
        ])
        ..json('GET /api/v1/portfolios/p2/holdings', [
          holding('a1', value: null),
        ]);
    });

    test('shows the asset and each portfolio position as reported', () async {
      final d = await investments.detail('a1');
      expect(d.symbol, 'ACM');
      expect(d.assetClass, 'Stocks');
      expect(
        [for (final p in d.positions) p.portfolioName],
        ['Retirement', 'Growth'],
      );
      expect(d.positions.first.value!.amount, Decimal.parse('1200.00'));
      expect(d.positions.last.value, isNull, reason: 'unpriced is not zero');
    });

    test('nothing the API lacks is invented', () async {
      final d = await investments.detail('a1');
      expect(d.price, isNull);
      expect(d.changePercent, isNull);
      expect(d.fundamentals, isNull);
      expect(d.research, isEmpty);
      expect(
        d.positions.first.unrealisedPl,
        isNull,
        reason: 'not value minus cost',
      );
      final history = await investments.priceHistory('a1', ChartPeriod.year);
      expect(history.points, isEmpty);
    });

    test('not held anywhere: no positions', () async {
      final d = await investments.detail('a2');
      expect(d.positions, isEmpty);
    });
  });
}

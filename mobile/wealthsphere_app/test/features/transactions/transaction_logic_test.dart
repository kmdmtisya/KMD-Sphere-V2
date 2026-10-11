import 'package:decimal/decimal.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/json_reader.dart';
import 'package:wealthsphere_app/features/transactions/application/ledger_view.dart';
import 'package:wealthsphere_app/features/transactions/application/transaction_draft.dart';
import 'package:wealthsphere_app/features/transactions/data/transaction_repository.dart';
import 'package:wealthsphere_app/features/transactions/domain/ledger_entry.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../helpers/demo_overrides.dart';

final DateTime today = DateTime(2026, 10, 9);

TransactionDraft draft({
  TransactionKind kind = TransactionKind.buy,
  String? portfolio = 'p-growth',
  String? asset = 'DEMO-TEC',
  DateTime? date,
  String quantity = '5',
  String price = '190',
  String amount = '',
  String fee = '',
  String note = '',
}) => TransactionDraft(
  kind: kind,
  portfolioId: portfolio,
  assetSymbol: asset,
  assetName: asset == null ? null : 'Demo Technology ETF',
  date: date ?? DateTime(2026, 10, 8),
  quantity: quantity,
  unitPrice: price,
  amount: amount,
  fee: fee,
  note: note,
);

DraftValidation check(TransactionDraft d) =>
    validateDraft(d, today: today, currency: 'USD');

LedgerEntry entry(
  String id,
  DateTime date, {
  TransactionKind kind = TransactionKind.buy,
  DateTime? created,
}) => LedgerEntry(
  id: id,
  portfolioId: 'p-growth',
  kind: kind,
  tradeDate: date,
  gross: Money.parse('10.00', 'USD'),
  source: 'manual',
  createdAt: created ?? DateTime.utc(2026, 1, 1),
);

void main() {
  group('parseNumber', () {
    (Decimal?, TxFieldError?) parse(
      String t, {
      int places = 2,
      bool zero = false,
    }) {
      final (v, issue) = parseNumber(t, places: places, allowZero: zero);
      return (v, issue?.error);
    }

    test('reads plain decimals exactly', () {
      expect(parse('12.50').$1, Decimal.parse('12.5'));
      expect(parse(' 7 ').$1, Decimal.parse('7'));
      expect(parse('0.1').$1! + parse('0.2').$1!, Decimal.parse('0.3'));
    });

    test('explains each kind of mistake', () {
      expect(parse('').$2, TxFieldError.required);
      expect(parse('   ').$2, TxFieldError.required);
      expect(parse('abc').$2, TxFieldError.notANumber);
      expect(parse('1,5').$2, TxFieldError.notANumber);
      expect(parse('1e5').$2, TxFieldError.notANumber);
      expect(parse('.5').$2, TxFieldError.notANumber);
      expect(parse('-3').$2, TxFieldError.negative);
      expect(parse('0').$2, TxFieldError.notPositive);
      expect(parse('0.00').$2, TxFieldError.notPositive);
      expect(parse('1.005').$2, TxFieldError.tooManyDecimals);
      expect(parse('1000000000000').$2, TxFieldError.tooLarge);
    });

    test('allows zero only when asked to', () {
      expect(parse('0', zero: true).$1, Decimal.zero);
      expect(parse('0', zero: true).$2, isNull);
    });

    test('reports the allowed decimal places', () {
      final (_, issue) = parseNumber('1.123', places: 2);
      expect(issue, const TxIssue(TxFieldError.tooManyDecimals, places: 2));
    });
  });

  group('validateDraft', () {
    test('accepts a valid trade and parses it exactly', () {
      final result = check(draft(fee: '1.25', note: '  first buy '));
      expect(result.isValid, isTrue);
      final t = result.value!;
      expect(t.kind, TransactionKind.buy);
      expect(t.quantity, Decimal.parse('5'));
      expect(t.unitPrice, Decimal.parse('190'));
      expect(t.fee, Decimal.parse('1.25'));
      expect(t.amount, isNull, reason: 'the server derives a trade total');
      expect(t.note, 'first buy');
      expect(t.currency, 'USD');
    });

    test('a trade needs an asset, quantity and price but not an amount', () {
      final result = check(
        draft(asset: null, quantity: '', price: '', amount: 'ignored'),
      );
      expect(result.issues.keys.toSet(), {
        TxField.asset,
        TxField.quantity,
        TxField.unitPrice,
      });
      expect(result.value, isNull);
    });

    test('a deposit needs only an amount and a date', () {
      final result = check(
        draft(kind: TransactionKind.deposit, asset: null, amount: '250.00'),
      );
      expect(result.isValid, isTrue);
      expect(result.value!.amount, Decimal.parse('250'));
      expect(result.value!.assetSymbol, isNull);
      expect(result.value!.quantity, isNull);
    });

    test('a dividend needs an asset and an amount', () {
      final missing = check(
        draft(kind: TransactionKind.dividend, asset: null, amount: ''),
      );
      expect(missing.issues.keys.toSet(), {TxField.asset, TxField.amount});
      final ok = check(draft(kind: TransactionKind.dividend, amount: '12.30'));
      expect(ok.isValid, isTrue);
      expect(ok.value!.assetSymbol, 'DEMO-TEC');
    });

    test('money is limited to the currency minor units', () {
      final usd = check(draft(kind: TransactionKind.fee, amount: '1.234'));
      expect(usd.issues[TxField.amount]!.places, 2);
      final yen = validateDraft(
        draft(kind: TransactionKind.fee, amount: '100.5'),
        today: today,
        currency: 'JPY',
      );
      expect(yen.issues[TxField.amount]!.places, 0);
    });

    test('quantity allows 8 decimals and price 6', () {
      expect(check(draft(quantity: '0.12345678')).isValid, isTrue);
      expect(
        check(draft(quantity: '0.123456789')).issues[TxField.quantity]!.places,
        quantityPlaces,
      );
      expect(check(draft(price: '1.123456')).isValid, isTrue);
      expect(
        check(draft(price: '1.1234567')).issues[TxField.unitPrice]!.places,
        unitPricePlaces,
      );
    });

    test('the fee is optional but cannot be negative', () {
      expect(check(draft(fee: '')).isValid, isTrue);
      expect(check(draft(fee: '0')).isValid, isTrue);
      expect(
        check(draft(fee: '-1')).issues[TxField.fee]!.error,
        TxFieldError.negative,
      );
    });

    test('the date is required, not in the future and not before 2000', () {
      final none = validateDraft(
        const TransactionDraft(
          kind: TransactionKind.buy,
          portfolioId: 'p',
          assetSymbol: 'A',
          quantity: '1',
          unitPrice: '1',
        ),
        today: today,
        currency: 'USD',
      );
      expect(none.issues[TxField.date]!.error, TxFieldError.required);
      expect(
        check(draft(date: DateTime(2026, 10, 10))).issues[TxField.date]!.error,
        TxFieldError.futureDate,
      );
      expect(check(draft(date: DateTime(2026, 10, 9))).isValid, isTrue);
      expect(
        check(draft(date: DateTime(1999, 12, 31))).issues[TxField.date]!.error,
        TxFieldError.tooOld,
      );
      expect(check(draft(date: DateTime(2000))).isValid, isTrue);
    });

    test('the time of day never makes today look like the future', () {
      final late = DateTime(2026, 10, 9, 23, 59);
      final result = validateDraft(
        draft(date: late),
        today: DateTime(2026, 10, 9, 0, 1),
        currency: 'USD',
      );
      expect(result.isValid, isTrue);
    });

    test('a portfolio must be chosen', () {
      expect(
        check(draft(portfolio: null)).issues[TxField.portfolio]!.error,
        TxFieldError.required,
      );
    });

    test('only hand-enterable kinds are offered', () {
      expect(addableKinds, isNot(contains(TransactionKind.transferIn)));
      expect(
        addableKinds,
        isNot(contains(TransactionKind.valuationAdjustment)),
      );
      expect(addableKinds, contains(TransactionKind.buy));
    });
  });

  group('filters and grouping', () {
    test('each filter matches only its kinds and every kind has a home', () {
      for (final k in TransactionKind.values) {
        final homes = [
          for (final f in TxFilter.values)
            if (f != TxFilter.all && f.matches(k)) f,
        ];
        expect(homes, hasLength(1), reason: '$k is in exactly one group');
        expect(TxFilter.all.matches(k), isTrue);
      }
    });

    test('filtersPresent hides groups with no entries', () {
      final entries = [entry('a', today), entry('b', today)];
      expect(filtersPresent(entries), [TxFilter.all, TxFilter.trades]);
      expect(filtersPresent(const []), [TxFilter.all]);
    });

    test('groups by month, newest first, with a stable tie-break', () {
      final entries = [
        entry('a', DateTime(2026, 9, 30)),
        entry(
          'b',
          DateTime(2026, 10, 1),
          created: DateTime.utc(2026, 10, 1, 8),
        ),
        entry(
          'c',
          DateTime(2026, 10, 1),
          created: DateTime.utc(2026, 10, 1, 9),
        ),
        entry('d', DateTime(2026, 10, 20)),
        entry('e', DateTime(2025, 10, 5)),
      ];
      final months = groupByMonth(entries);
      expect(months.map((m) => m.month), [
        DateTime(2026, 10),
        DateTime(2026, 9),
        DateTime(2025, 10),
      ]);
      expect(months.first.entries.map((e) => e.id), ['d', 'c', 'b']);
      // A second call gives the same order.
      expect(
        groupByMonth(entries.reversed.toList()).first.entries.map((e) => e.id),
        ['d', 'c', 'b'],
      );
    });

    test('an empty list gives no groups', () {
      expect(groupByMonth(const []), isEmpty);
    });
  });

  group('LedgerEntry.fromJson', () {
    test('keeps the trade date as a calendar day', () {
      final e = LedgerEntry.fromJson(
        JsonReaderFor.entry(tradeDate: '2026-03-01'),
      );
      expect(e.tradeDate, DateTime(2026, 3));
      expect(e.tradeDate.isUtc, isFalse);
    });

    test('rejects an unknown transaction type loudly', () {
      expect(
        () => LedgerEntry.fromJson(JsonReaderFor.entry(type: 'GIFT')),
        throwsFormatException,
      );
    });

    test('rejects money given as a JSON number', () {
      expect(
        () => LedgerEntry.fromJson(JsonReaderFor.entry(grossAsNumber: true)),
        throwsFormatException,
      );
    });

    test('only a live original can be corrected', () {
      final live = entry('a', today);
      expect(live.canCorrect, isTrue);
      expect(live.withReversedBy('r').canCorrect, isFalse);
      expect(live.withReversedBy('r').isReversed, isTrue);
    });
  });

  group('DemoTransactionRepository', () {
    late ProviderContainer container;
    late TransactionRepository repo;

    setUp(() {
      container = ProviderContainer(overrides: demoOverrides());
      addTearDown(container.dispose);
      repo = container.read(transactionRepositoryProvider);
    });

    NewTransaction buy() => NewTransaction(
      kind: TransactionKind.buy,
      portfolioId: 'p-growth',
      currency: 'USD',
      date: DateTime(2026, 10, 8),
      assetSymbol: 'DEMO-TEC',
      assetName: 'Demo Technology ETF',
      quantity: Decimal.parse('5'),
      unitPrice: Decimal.parse('190.10'),
    );

    test('loads the fixture, consolidated and per portfolio', () async {
      expect(await repo.entries('consolidated'), hasLength(16));
      expect(await repo.entries('p-growth'), hasLength(4));
      expect(await repo.entries('p-retire'), hasLength(9));
      expect(await repo.entries('p-income'), hasLength(3));
    });

    test('the fixture links the reversal in both directions', () async {
      final original = await repo.entry('t-005');
      final reversal = await repo.entry('t-006');
      expect(original.reversedById, reversal.id);
      expect(reversal.reversesId, original.id);
      expect(original.isReversed, isTrue);
      expect(reversal.isReversal, isTrue);
    });

    test('add appends a new entry and changes nothing else', () async {
      final before = await repo.entries('consolidated');
      final added = await repo.add(buy());
      final after = await repo.entries('consolidated');
      expect(after, hasLength(before.length + 1));
      expect(after.map((e) => e.id), containsAll(before.map((e) => e.id)));
      expect(added.gross.amount, Decimal.parse('950.5'));
      expect(added.gross.currencyCode, 'USD');
      expect(added.source, 'manual');
      expect(await repo.entries('p-growth'), hasLength(5));
      expect(await repo.entries('p-retire'), hasLength(9));
    });

    test('reverse appends a linked reversal and marks the original', () async {
      final reversal = await repo.reverse('t-002', note: 'wrong fund');
      expect(reversal.reversesId, 't-002');
      expect(reversal.note, 'wrong fund');
      final original = await repo.entry('t-002');
      expect(original.reversedById, reversal.id);
      // Nothing about the original changed except the link.
      expect(original.gross.amount, Decimal.parse('2030'));
      expect(original.quantity, Decimal.parse('20'));
      expect(await repo.entries('consolidated'), hasLength(17));
    });

    test(
      'an entry cannot be reversed twice, and a reversal is final',
      () async {
        await repo.reverse('t-002');
        await expectLater(
          repo.reverse('t-002'),
          throwsA(
            isA<LedgerRuleException>().having(
              (e) => e.rule,
              'rule',
              LedgerRule.alreadyReversed,
            ),
          ),
        );
        await expectLater(
          repo.reverse('t-006'),
          throwsA(
            isA<LedgerRuleException>().having(
              (e) => e.rule,
              'rule',
              LedgerRule.isReversal,
            ),
          ),
        );
      },
    );

    test('an unknown entry is reported, not invented', () async {
      await expectLater(
        repo.entry('nope'),
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
}

/// Builds JSON readers for entry fixtures.
abstract final class JsonReaderFor {
  static JsonReader entry({
    String type = 'DEPOSIT',
    String tradeDate = '2026-10-01',
    bool grossAsNumber = false,
  }) => JsonReader({
    'id': 'x',
    'portfolio_id': 'p-growth',
    'transaction_type': type,
    'trade_date': tradeDate,
    'gross_amount': grossAsNumber
        ? 100
        : {'amount': '100.00', 'currency': 'USD'},
    'source': 'manual',
    'created_at': '2026-10-01T09:00:00Z',
  });
}

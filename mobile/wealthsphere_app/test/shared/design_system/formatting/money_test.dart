import 'dart:convert';

import 'package:decimal/decimal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

void main() {
  group('construction and equality', () {
    test('keeps the exact decimal amount', () {
      final m = Money.parse('1234.50', 'USD');
      expect(m.amount, Decimal.parse('1234.5'));
      expect(m.currencyCode, 'USD');
      expect(m.toString(), '1234.5 USD');
    });

    test('equal when numerically equal, regardless of trailing zeros', () {
      final a = Money.parse('1.0', 'USD');
      final b = Money.parse('1.00', 'USD');
      expect(a, b);
      expect(a.hashCode, b.hashCode);
      expect({a, b}.length, 1);
    });

    test('different currency or amount is different', () {
      expect(Money.parse('1', 'USD') == Money.parse('1', 'EUR'), isFalse);
      expect(Money.parse('1', 'USD') == Money.parse('2', 'USD'), isFalse);
    });

    test('sign helpers', () {
      expect(Money.parse('-0.01', 'USD').isNegative, isTrue);
      expect(Money.parse('0.00', 'USD').isZero, isTrue);
      expect(Money.parse('0.01', 'USD').isPositive, isTrue);
      expect(Money.parse('-5', 'USD').abs(), Money.parse('5', 'USD'));
      expect(Money.zero('KES').isZero, isTrue);
    });
  });

  group('API representation: amounts are strings, never numbers', () {
    test('parses {"amount": "...", "currency": "..."}', () {
      final m = Money.fromJson(
        jsonDecode('{"amount":"1247850.00","currency":"USD"}'),
      );
      expect(m, Money.parse('1247850', 'USD'));
    });

    test('rejects JSON numbers for the amount', () {
      for (final body in [
        '{"amount":1234.5,"currency":"USD"}',
        '{"amount":1234,"currency":"USD"}',
      ]) {
        expect(
          () => Money.fromJson(jsonDecode(body)),
          throwsFormatException,
          reason: body,
        );
      }
    });

    test('rejects missing, mistyped or malformed fields', () {
      final bad = <Object?>[
        null,
        'USD',
        <String, dynamic>{},
        <String, dynamic>{'amount': '1'},
        <String, dynamic>{'currency': 'USD'},
        <String, dynamic>{'amount': '1', 'currency': 840},
        <String, dynamic>{'amount': '1', 'currency': 'usd'},
        <String, dynamic>{'amount': '1', 'currency': 'US'},
        <String, dynamic>{'amount': '1', 'currency': 'U\$D'},
        <String, dynamic>{'amount': '1', 'currency': ''},
      ];
      for (final json in bad) {
        expect(
          () => Money.fromJson(json),
          throwsFormatException,
          reason: '$json',
        );
      }
    });

    test('rejects anything that is not a plain decimal string', () {
      for (final amount in [
        '',
        ' 1',
        '1 ',
        '1e3',
        '1E-2',
        '+5',
        '.5',
        '5.',
        '1,000',
        'NaN',
        'Infinity',
        '--1',
        '1.2.3',
        '0x10',
        '１２',
      ]) {
        expect(
          () => Money.parse(amount, 'USD'),
          throwsFormatException,
          reason: '"$amount"',
        );
      }
    });

    test('accepts plain decimals including negatives and long scales', () {
      for (final amount in [
        '0',
        '-0',
        '1',
        '-1',
        '1234.5',
        '-0.000000000001',
        '99999999999999999999999.999999999999',
      ]) {
        expect(
          Money.parse(amount, 'USD').amount,
          Decimal.parse(amount),
          reason: amount,
        );
      }
    });

    test('round-trips through JSON without losing a digit', () {
      for (final amount in [
        '0.1',
        '0.000000000001',
        '9007199254740993.01',
        '12345678901234567890.123456789',
        '-42.50',
      ]) {
        final original = Money.parse(amount, 'KES');
        final back = Money.fromJson(jsonDecode(jsonEncode(original.toJson())));
        expect(back, original, reason: amount);
        expect(back.amount.toString(), original.amount.toString());
      }
    });

    test('toJson uses string amounts', () {
      final json = Money.parse('12.30', 'AED').toJson();
      expect(json['amount'], isA<String>());
      expect(json, {'amount': '12.3', 'currency': 'AED'});
    });
  });

  group('currency table', () {
    test(
      'minor units follow ISO 4217 for the currencies the product supports',
      () {
        expect(CurrencyInfo.of('USD').minorUnits, 2);
        expect(CurrencyInfo.of('AED').minorUnits, 2);
        expect(CurrencyInfo.of('KES').minorUnits, 2);
        expect(CurrencyInfo.of('JPY').minorUnits, 0);
        expect(CurrencyInfo.of('KRW').minorUnits, 0);
        expect(CurrencyInfo.of('KWD').minorUnits, 3);
        expect(CurrencyInfo.of('BHD').minorUnits, 3);
        expect(CurrencyInfo.of('BTC').minorUnits, 8);
      },
    );

    test('symbols only where unambiguous', () {
      expect(CurrencyInfo.of('USD').symbol, r'$');
      expect(CurrencyInfo.of('EUR').symbol, '€');
      expect(CurrencyInfo.of('AED').symbol, isNull);
      expect(CurrencyInfo.of('KES').symbol, isNull);
      expect(CurrencyInfo.of('CNY').symbol, isNull); // would clash with ¥
    });

    test('unknown codes default to two decimals and no symbol', () {
      final info = CurrencyInfo.of('XYZ');
      expect(info.minorUnits, 2);
      expect(info.symbol, isNull);
    });
  });
}

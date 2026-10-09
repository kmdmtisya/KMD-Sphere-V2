import 'package:decimal/decimal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

const nbsp = ' ';
const nnbsp = ' ';

String f(
  String amount,
  String currency, {
  String locale = 'en',
  CurrencyDisplay display = CurrencyDisplay.symbol,
  SignDisplay sign = SignDisplay.auto,
  int? digits,
}) => MoneyFormatter(locale: locale).format(
  Money.parse(amount, currency),
  currency: display,
  sign: sign,
  fractionDigits: digits,
);

String c(
  String amount,
  String currency, {
  String locale = 'en',
  CurrencyDisplay display = CurrencyDisplay.symbol,
  SignDisplay sign = SignDisplay.auto,
}) => MoneyFormatter(
  locale: locale,
).formatCompact(Money.parse(amount, currency), currency: display, sign: sign);

void main() {
  group('English, two-decimal currencies', () {
    test('basic grouping and symbols', () {
      expect(f('1234.5', 'USD'), r'$1,234.50');
      expect(f('0', 'USD'), r'$0.00');
      expect(f('1247850', 'USD'), r'$1,247,850.00');
      expect(f('1234.5', 'EUR'), '€1,234.50');
      expect(f('1234.5', 'GBP'), '£1,234.50');
      expect(f('1234.5', 'INR'), '₹1,234.50');
    });

    test('currencies without an unambiguous symbol show their code', () {
      expect(f('1234.5', 'AED'), 'AED${nbsp}1,234.50');
      expect(f('1234.5', 'KES'), 'KES${nbsp}1,234.50');
      expect(f('0.5', 'XYZ'), 'XYZ${nbsp}0.50');
    });

    test('negative values put the sign before the symbol', () {
      expect(f('-1234.5', 'USD'), r'-$1,234.50');
      expect(
        f('-1234.5', 'AED'),
        'AED${nbsp}1,234.50'.replaceFirst('AED', '-AED'),
      );
    });

    test('currency display modes', () {
      expect(
        f('1234.5', 'USD', display: CurrencyDisplay.code),
        'USD${nbsp}1,234.50',
      );
      expect(f('1234.5', 'USD', display: CurrencyDisplay.none), '1,234.50');
      expect(f('-1234.5', 'USD', display: CurrencyDisplay.none), '-1,234.50');
    });
  });

  group('rounding is half-up on exact decimals (ADR-0006)', () {
    test('ties round away from zero', () {
      expect(f('0.005', 'USD'), r'$0.01');
      expect(f('-0.005', 'USD'), r'-$0.01');
      expect(f('0.015', 'USD'), r'$0.02');
      expect(f('0.025', 'USD'), r'$0.03'); // half-even would give 0.02
      expect(f('-0.025', 'USD'), r'-$0.03');
    });

    test(
      'classic binary-float traps are exact because no double is involved',
      () {
        expect(
          f('1.005', 'USD'),
          r'$1.01',
        ); // (1.005).toStringAsFixed(2) == "1.00" with doubles
        expect(f('2.675', 'USD'), r'$2.68'); // doubles give 2.67
        expect(f('1.255', 'USD'), r'$1.26');
        expect(f('0.285', 'USD'), r'$0.29');
        expect(f('8.345', 'USD'), r'$8.35');
      },
    );

    test('below the tie rounds down, above rounds up', () {
      expect(f('0.00499999999999999999', 'USD'), r'$0.00');
      expect(f('0.00500000000000000001', 'USD'), r'$0.01');
    });

    test('a value that rounds to zero never shows a minus sign', () {
      expect(f('-0.004', 'USD'), r'$0.00');
      expect(f('-0.0000001', 'USD'), r'$0.00');
      expect(f('-0.004', 'USD', sign: SignDisplay.always), r'$0.00');
    });

    test('rounding up can carry into the integer part', () {
      expect(f('0.995', 'USD'), r'$1.00');
      expect(f('999.995', 'USD'), r'$1,000.00');
    });
  });

  group('exactness beyond binary floating point', () {
    test('values above 2^53 keep every digit', () {
      expect(f('9007199254740993.01', 'USD'), r'$9,007,199,254,740,993.01');
      expect(
        f('12345678901234567890.125', 'USD'),
        r'$12,345,678,901,234,567,890.13',
      );
      expect(
        f('-99999999999999999999999.994', 'USD'),
        r'-$99,999,999,999,999,999,999,999.99',
      );
    });

    test('tiny values with a long scale', () {
      expect(f('0.000000000001', 'USD'), r'$0.00');
      expect(f('0.000000000001', 'BTC'), 'BTC${nbsp}0.00000000');
      expect(f('0.123456785', 'BTC'), 'BTC${nbsp}0.12345679');
    });
  });

  group('zero- and three-decimal currencies', () {
    test('JPY has no decimals', () {
      expect(f('1234567', 'JPY'), '¥1,234,567');
      expect(f('2.5', 'JPY'), '¥3');
      expect(f('-2.5', 'JPY'), '-¥3');
      expect(f('0.4', 'JPY'), '¥0');
      expect(f('1234.5', 'KRW'), '₩1,235');
    });

    test('KWD and BHD have three decimals', () {
      expect(f('1.0005', 'KWD'), 'KWD${nbsp}1.001');
      expect(f('1.00049', 'KWD'), 'KWD${nbsp}1.000');
      expect(f('1234.5675', 'KWD'), 'KWD${nbsp}1,234.568');
      expect(f('0.0005', 'BHD'), 'BHD${nbsp}0.001');
    });

    test('an explicit fractionDigits overrides the currency default', () {
      expect(f('1234.5678', 'USD', digits: 4), r'$1,234.5678');
      expect(f('1234.567', 'JPY', digits: 2), '¥1,234.57');
      expect(f('0.123456789', 'BTC', digits: 2), 'BTC${nbsp}0.12');
    });
  });

  group('sign display', () {
    test('always shows plus for positive values and nothing for zero', () {
      expect(f('12', 'USD', sign: SignDisplay.always), r'+$12.00');
      expect(f('-12', 'USD', sign: SignDisplay.always), r'-$12.00');
      expect(f('0', 'USD', sign: SignDisplay.always), r'$0.00');
    });

    test('never drops the sign', () {
      expect(f('-12', 'USD', sign: SignDisplay.never), r'$12.00');
      expect(f('12', 'USD', sign: SignDisplay.never), r'$12.00');
    });
  });

  group('compact amounts', () {
    test('magnitude suffixes', () {
      expect(c('0', 'USD'), r'$0');
      expect(c('999', 'USD'), r'$999');
      expect(c('1000', 'USD'), r'$1K');
      expect(c('1234', 'USD'), r'$1.2K');
      expect(c('1900000', 'USD'), r'$1.9M');
      expect(c('1250000000', 'USD'), r'$1.3B');
      expect(c('1000000000000', 'USD'), r'$1T');
    });

    test('half-up at the compact boundary', () {
      expect(c('1250', 'USD'), r'$1.3K');
      expect(c('1249.99', 'USD'), r'$1.2K');
      expect(c('-1250', 'USD'), r'-$1.3K');
    });

    test('a value that rounds up to the next magnitude is promoted', () {
      expect(c('999.5', 'USD'), r'$1K');
      expect(c('999950', 'USD'), r'$1M');
      expect(c('999949', 'USD'), r'$999.9K');
      expect(c('999950000', 'USD'), r'$1B');
    });

    test('beyond trillions it keeps grouping instead of inventing units', () {
      expect(c('1234567890123456', 'USD'), r'$1,234.6T');
    });

    test('sub-unit amounts do not collapse to zero', () {
      expect(c('0.45', 'USD'), r'$0.45');
      expect(c('-0.45', 'USD'), r'-$0.45');
    });

    test('currency display and negatives', () {
      expect(c('-1234', 'USD'), r'-$1.2K');
      expect(c('1234', 'USD', display: CurrencyDisplay.none), '1.2K');
      expect(c('1234', 'AED'), 'AED${nbsp}1.2K');
      expect(c('1234567', 'JPY'), '¥1.2M');
      expect(c('12', 'USD', sign: SignDisplay.always), r'+$12');
    });
  });

  group('locales', () {
    test('German: dot grouping, comma decimal, trailing symbol', () {
      expect(f('1234.5', 'EUR', locale: 'de'), '1.234,50$nbsp€');
      expect(f('-1234.5', 'EUR', locale: 'de'), '-1.234,50$nbsp€');
      expect(f('1234.5', 'USD', locale: 'de_DE'), '1.234,50$nbsp\$');
      expect(f('1234.5', 'AED', locale: 'de'), '1.234,50${nbsp}AED');
    });

    test('French: narrow no-break space grouping', () {
      expect(
        f('1234567.5', 'EUR', locale: 'fr'),
        '1${nnbsp}234${nnbsp}567,50$nbsp€',
      );
    });

    test('Indian grouping (lakh/crore) in en_IN, also with a dash', () {
      expect(f('1234567.89', 'INR', locale: 'en_IN'), '₹12,34,567.89');
      expect(f('100000', 'INR', locale: 'en-IN'), '₹1,00,000.00');
      expect(f('12345678', 'INR', locale: 'en_IN'), '₹1,23,45,678.00');
      expect(f('999', 'INR', locale: 'en_IN'), '₹999.00');
    });

    test('Arabic uses the locale negative pattern', () {
      expect(f('1234.5', 'USD', locale: 'ar'), '‏1,234.50$nbsp\$');
      expect(f('-1234.5', 'USD', locale: 'ar'), '‏-1,234.50$nbsp\$');
    });

    test('unknown locales fall back to English; language fallback works', () {
      expect(f('1234.5', 'USD', locale: 'xx'), r'$1,234.50');
      expect(f('1234.5', 'USD', locale: 'en_AE'), r'$1,234.50');
      // Austrian German puts the symbol first and groups with a no-break space.
      expect(
        f('1234.5', 'EUR', locale: 'de_AT'),
        allOf(startsWith('€'), endsWith('234,50')),
      );
    });
  });

  group('number only and speech', () {
    test('formatNumber', () {
      const fmt = MoneyFormatter();
      expect(fmt.formatNumber(Decimal.parse('1234.5')), '1,234.50');
      expect(fmt.formatNumber(Decimal.parse('-0.005')), '-0.01');
      expect(
        fmt.formatNumber(
          Decimal.parse('12'),
          fractionDigits: 0,
          sign: SignDisplay.always,
        ),
        '+12',
      );
    });

    test(
      'formatForSpeech uses the code so screen readers do not guess symbols',
      () {
        expect(
          const MoneyFormatter().formatForSpeech(Money.parse('1234.5', 'USD')),
          'USD${nbsp}1,234.50',
        );
      },
    );
  });

  group('the formatter is pure', () {
    test('formatting does not change the money value', () {
      final money = Money.parse('1.005', 'USD');
      const MoneyFormatter().format(money);
      expect(money.amount, Decimal.parse('1.005'));
    });
  });
}

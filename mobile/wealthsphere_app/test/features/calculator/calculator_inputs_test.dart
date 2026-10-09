import 'dart:io';

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/input/decimal_input.dart';
import 'package:wealthsphere_app/features/calculator/application/calculator_providers.dart';
import 'package:wealthsphere_app/features/calculator/domain/forecast_input_limits.dart';
import 'package:wealthsphere_app/features/forecast/data/forecast_repository.dart';

import '../../helpers/demo_container.dart';

void main() {
  group('DecimalInput (English)', () {
    final en = DecimalInput('en');

    test('parses plain decimals exactly', () {
      expect(en.parse('1234.50'), Decimal.parse('1234.50'));
      expect(en.parse('-0.5'), Decimal.parse('-0.5'));
      expect(en.parse('  7 '), Decimal.fromInt(7));
      expect(
        en.parse('9007199254740993.01')!.toString(),
        '9007199254740993.01',
      );
    });

    test('rejects malformed text', () {
      for (final bad in [
        '',
        ' ',
        'abc',
        '1.2.3',
        '1,000',
        '1e3',
        '--1',
        '1-',
        '.',
        '-',
        '1.',
        ',5',
        '１２',
      ]) {
        expect(
          en.parse(bad),
          anyOf(
            isNull,
            isA<Decimal>().having(
              (d) => d.toString(),
              'value',
              isNot(contains('e')),
            ),
          ),
          reason: bad,
        );
      }
      for (final bad in ['abc', '1.2.3', '1,000', '1e3', '--1', '1-', '-']) {
        expect(en.parse(bad), isNull, reason: bad);
      }
    });

    test('counts fraction digits and formats without trailing zeros', () {
      expect(en.fractionDigits('12.345'), 3);
      expect(en.fractionDigits('12'), 0);
      expect(en.format(Decimal.parse('10000.00')), '10000');
      expect(en.format(Decimal.parse('2.50')), '2.5');
      expect(en.format(Decimal.parse('2.50'), minFractionDigits: 2), '2.50');
    });
  });

  group('DecimalInput (German, comma decimal)', () {
    final de = DecimalInput('de');

    test('uses the comma as the decimal separator', () {
      expect(de.decimalSeparator, ',');
      expect(de.parse('1234,50'), Decimal.parse('1234.50'));
      expect(de.parse('-0,5'), Decimal.parse('-0.5'));
      expect(de.format(Decimal.parse('2.5')), '2,5');
    });

    test(
      'rejects a dot, which would be misread (it is a grouping mark in German)',
      () {
        expect(de.parse('1234.50'), isNull);
        expect(de.parse('1.234,50'), isNull);
      },
    );
  });

  group('typing filter', () {
    TextEditingValue type(
      DecimalInput input,
      String text, {
      int digits = 2,
      bool negative = false,
      String before = '',
    }) => input
        .formatter(maxFractionDigits: digits, allowNegative: negative)
        .formatEditUpdate(
          TextEditingValue(text: before),
          TextEditingValue(
            text: text,
            selection: TextSelection.collapsed(offset: text.length),
          ),
        );

    test('drops letters, grouping separators and a second separator', () {
      final en = DecimalInput('en');
      expect(type(en, '12a3').text, '123');
      expect(type(en, '1,234').text, '1234');
      expect(type(en, '1.2.3').text, '1.23');
      expect(type(en, '1 000').text, '1000');
    });

    test('caps the decimal places', () {
      final en = DecimalInput('en');
      expect(type(en, '1.2345').text, '1.23');
      expect(
        type(en, '1.2345', digits: 0).text,
        '12345',
        reason: 'whole-number fields take no separator',
      );
    });

    test('allows one leading minus only when negatives are allowed', () {
      final en = DecimalInput('en');
      expect(type(en, '-5', negative: true).text, '-5');
      expect(type(en, '-5').text, '5');
      expect(type(en, '5-', negative: true).text, '5');
      expect(type(en, '--5', negative: true).text, '-5');
    });

    test('works with a comma separator and rejects the dot', () {
      final de = DecimalInput('de');
      expect(type(de, '12,5').text, '12,5');
      expect(type(de, '12.5').text, '125');
      expect(type(de, '1,2,3').text, '1,23');
    });
  });

  group('ForecastInputLimits', () {
    final en = DecimalInput('en');
    InputIssue? check(CalculatorField f, String text) =>
        ForecastInputLimits.validate(f, text, en);

    test('empty required fields are rejected, empty optional ones are not', () {
      expect(
        check(CalculatorField.initialInvestment, ''),
        const InputIssue(IssueKind.required),
      );
      expect(
        ForecastInputLimits.validate(
          CalculatorField.contributionGrowth,
          '',
          en,
          required: false,
        ),
        isNull,
      );
    });

    test('boundaries are inclusive and one step beyond is rejected', () {
      final cases = <(CalculatorField, String, String, String, String)>[
        // field, just below min, min, max, just above max
        (
          CalculatorField.initialInvestment,
          '-0.01',
          '0',
          '1000000000',
          '1000000000.01',
        ),
        (
          CalculatorField.monthlyContribution,
          '-1',
          '0',
          '10000000',
          '10000000.01',
        ),
        (CalculatorField.annualReturn, '-20.01', '-20', '50', '50.01'),
        (CalculatorField.years, '0', '1', '60', '61'),
        (CalculatorField.contributionGrowth, '-0.01', '0', '20', '20.01'),
        (CalculatorField.inflation, '-0.01', '0', '30', '30.01'),
        (CalculatorField.annualFee, '-0.01', '0', '5', '5.01'),
        (CalculatorField.conservativeReturn, '-20.01', '-20', '50', '50.01'),
        (CalculatorField.growthReturn, '-20.01', '-20', '50', '50.01'),
      ];
      for (final (field, below, min, max, above) in cases) {
        expect(
          check(field, below)?.kind,
          IssueKind.tooLow,
          reason: '${field.name} $below',
        );
        expect(check(field, min), isNull, reason: '${field.name} $min');
        expect(check(field, max), isNull, reason: '${field.name} $max');
        expect(
          check(field, above)?.kind,
          IssueKind.tooHigh,
          reason: '${field.name} $above',
        );
      }
    });

    test('the issue carries the limit so the message can state it', () {
      expect(
        check(CalculatorField.years, '61'),
        InputIssue(IssueKind.tooHigh, Decimal.fromInt(60)),
      );
      expect(
        check(CalculatorField.annualReturn, '-30'),
        InputIssue(IssueKind.tooLow, Decimal.fromInt(-20)),
      );
    });

    test('years must be a whole number', () {
      expect(check(CalculatorField.years, '2.5')?.kind, IssueKind.notWhole);
    });

    test('too many decimal places', () {
      expect(
        check(CalculatorField.initialInvestment, '10.123')?.kind,
        IssueKind.tooManyDecimals,
      );
      expect(
        check(CalculatorField.annualReturn, '7.555')?.kind,
        IssueKind.tooManyDecimals,
      );
    });

    test('garbage is invalid', () {
      expect(
        check(CalculatorField.initialInvestment, 'abc')?.kind,
        IssueKind.invalid,
      );
      expect(
        check(CalculatorField.initialInvestment, '1.2.3')?.kind,
        IssueKind.invalid,
      );
    });

    test('negative returns are allowed within limits, other fields reject negatives', () {
      expect(check(CalculatorField.annualReturn, '-5'), isNull);
      expect(
        ForecastInputLimits.of(CalculatorField.annualReturn).allowsNegative,
        isTrue,
      );
      expect(
        ForecastInputLimits.of(CalculatorField.initialInvestment)
            .allowsNegative,
        isFalse,
      );
    });

    test('conservative <= base <= growth', () {
      const d = Decimal.parse;
      expect(
        ForecastInputLimits.validateOrdering(
          CalculatorField.conservativeReturn,
          d('9'),
          d('8'),
          d('12'),
        )?.kind,
        IssueKind.conservativeAboveBase,
      );
      expect(
        ForecastInputLimits.validateOrdering(
          CalculatorField.growthReturn,
          d('5'),
          d('8'),
          d('7'),
        )?.kind,
        IssueKind.growthBelowBase,
      );
      expect(
        ForecastInputLimits.validateOrdering(
          CalculatorField.conservativeReturn,
          d('8'),
          d('8'),
          d('12'),
        ),
        isNull,
        reason: 'equal is fine',
      );
      expect(
        ForecastInputLimits.validateOrdering(
          CalculatorField.growthReturn,
          d('5'),
          null,
          d('7'),
        ),
        isNull,
        reason: 'not comparable yet',
      );
    });

    test('the default inputs are valid and match the demo forecast fixture exactly', () async {
      final d = ForecastInputLimits.defaults;
      final inputs = CalculatorInputs.defaults('en');
      for (final f in CalculatorField.values) {
        expect(check(f, inputs.text(f)), isNull, reason: f.name);
      }
      expect(inputs.toRequest(en), d);
      final fixture = await demoContainer()
          .read(forecastRepositoryProvider)
          .defaultRequest();
      expect(
        fixture,
        d,
        reason: 'canned demo response must be for the default inputs',
      );
    });
  });

  group('CalculatorInputs.toRequest', () {
    test('builds money and decimals as exact values, in the base currency', () {
      final en = DecimalInput('en');
      final inputs = CalculatorInputs.defaults('en').copyWith(
        texts: {
          ...CalculatorInputs.defaults('en').texts,
          CalculatorField.initialInvestment: '12345.67',
          CalculatorField.annualReturn: '-3.5',
        },
      );
      final r = inputs.toRequest(en)!;
      expect(r.initialInvestment.toJson(), {
        'amount': '12345.67',
        'currency': 'USD',
      });
      expect(r.annualReturnPercent, Decimal.parse('-3.5'));
      final json = r.toJson();
      expect(json['years'], 20);
      expect(
        json['initial_investment'],
        isA<Map<String, String>>().having(
          (m) => m['amount'],
          'amount',
          isA<String>(),
        ),
      );
    });

    test('is null when any field does not parse', () {
      final en = DecimalInput('en');
      final broken = CalculatorInputs.defaults('en').copyWith(
        texts: {
          ...CalculatorInputs.defaults('en').texts,
          CalculatorField.years: '',
        },
      );
      expect(broken.toRequest(en), isNull);
    });

    test('German text builds the same request as English text', () {
      final de = DecimalInput('de');
      final inputs = CalculatorInputs.defaults('de');
      expect(inputs.text(CalculatorField.inflation), '2,5');
      expect(inputs.toRequest(de), ForecastInputLimits.defaults);
    });
  });

  test('no compounding arithmetic exists in the calculator code (DEC-03)', () {
    final files = Directory('lib/features/calculator')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'));
    for (final f in files) {
      final source = f.readAsStringSync();
      expect(source, isNot(contains('dart:math')), reason: f.path);
      expect(source, isNot(contains('pow(')), reason: f.path);
      expect(
        source,
        isNot(matches(RegExp(r'\.pow\(|\bexp\(|\blog\('))),
        reason: f.path,
      );
    }
  });
}

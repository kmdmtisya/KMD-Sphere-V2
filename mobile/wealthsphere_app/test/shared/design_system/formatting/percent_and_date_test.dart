import 'package:decimal/decimal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/number_symbols_data.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/number_style.dart';

const nbsp = ' ';

String p(
  String value, {
  String locale = 'en',
  int digits = 2,
  SignDisplay sign = SignDisplay.auto,
}) =>
    PercentFormatter(locale: locale)
        .format(Decimal.parse(value), fractionDigits: digits, sign: sign);

void main() {
  group('percentages (inputs are percentage points)', () {
    test('basic formatting', () {
      expect(p('6.32'), '6.32%');
      expect(p('8.42'), '8.42%');
      expect(p('0'), '0.00%');
      expect(p('-1.5'), '-1.50%');
      expect(p('123456.789'), '123,456.79%');
    });

    test('half-up rounding on exact decimals', () {
      expect(p('0.005'), '0.01%');
      expect(p('-0.005'), '-0.01%');
      expect(p('1.005'), '1.01%');
      expect(p('12.5', digits: 0), '13%');
      expect(p('-12.5', digits: 0), '-13%');
      expect(p('2.5', digits: 0), '3%');
    });

    test('a value that rounds to zero has no sign', () {
      expect(p('-0.004'), '0.00%');
      expect(p('-0.004', sign: SignDisplay.always), '0.00%');
      expect(p('0', sign: SignDisplay.always), '0.00%');
    });

    test('sign display', () {
      expect(p('0.25', sign: SignDisplay.always), '+0.25%');
      expect(p('-0.25', sign: SignDisplay.always), '-0.25%');
      expect(p('-0.25', sign: SignDisplay.never), '0.25%');
    });

    test('locale placement of the percent sign', () {
      expect(p('6.32', locale: 'de'), '6,32$nbsp%');
      expect(p('-6.32', locale: 'de'), '-6,32$nbsp%');
      expect(p('1234.5', locale: 'en_IN'), '1,234.50%');
    });
  });

  group('relative age', () {
    final now = DateTime.utc(2026, 10, 9, 12);

    RelativeAge age(Duration ago) =>
        RelativeAge.between(now.subtract(ago), now: now);

    test('thresholds', () {
      expect(age(Duration.zero), const RelativeAge(AgeUnit.justNow, 0));
      expect(
        age(const Duration(seconds: 59)),
        const RelativeAge(AgeUnit.justNow, 0),
      );
      expect(
        age(const Duration(minutes: 1)),
        const RelativeAge(AgeUnit.minutes, 1),
      );
      expect(
        age(const Duration(minutes: 59, seconds: 59)),
        const RelativeAge(AgeUnit.minutes, 59),
      );
      expect(
        age(const Duration(hours: 1)),
        const RelativeAge(AgeUnit.hours, 1),
      );
      expect(
        age(const Duration(hours: 23, minutes: 59)),
        const RelativeAge(AgeUnit.hours, 23),
      );
      expect(age(const Duration(days: 1)), const RelativeAge(AgeUnit.days, 1));
      expect(
        age(const Duration(days: 6, hours: 23)),
        const RelativeAge(AgeUnit.days, 6),
      );
      expect(age(const Duration(days: 7)), const RelativeAge(AgeUnit.older, 7));
      expect(
        age(const Duration(days: 400)),
        const RelativeAge(AgeUnit.older, 400),
      );
    });

    test('timestamps in the future are flagged, small skew is "just now"', () {
      final future = RelativeAge.between(
        now.add(const Duration(hours: 3)),
        now: now,
      );
      expect(future.unit, AgeUnit.hours);
      expect(future.isFuture, isTrue);
      expect(
        RelativeAge.between(now.add(const Duration(seconds: 30)), now: now),
        const RelativeAge(AgeUnit.justNow, 0),
      );
    });

    test('time zones do not matter (compared in UTC)', () {
      final local = DateTime.parse('2026-10-09T14:00:00+02:00'); // 12:00 UTC
      expect(
        RelativeAge.between(local, now: now),
        const RelativeAge(AgeUnit.justNow, 0),
      );
      final twoHoursAgo = DateTime.parse(
        '2026-10-09T12:00:00+04:00',
      ); // 08:00 UTC
      expect(
        RelativeAge.between(twoHoursAgo, now: now),
        const RelativeAge(AgeUnit.hours, 4),
      );
    });
  });

  // Order matters: intl's date data is process-global, so the "before initialisation" group
  // must run before anything initialises it.
  group('absolute dates before initialisation never throw', () {
    final date = DateTime(2024, 3, 12, 14, 5);

    test('fall back to plain ISO text', () {
      expect(DateLabels.date(date), '2024-03-12');
      expect(DateLabels.dateTime(date), '2024-03-12 14:05');
      expect(DateLabels.dayMonth(date), '03-12');
      expect(() => DateLabels.date(date, locale: 'zz'), returnsNormally);
    });
  });

  group('absolute dates after initialisation', () {
    final date = DateTime(2024, 3, 12, 14, 5);

    setUpAll(() => initializeDateLabels(['en', 'de']));

    test('English date, date-time and day-month', () {
      expect(DateLabels.date(date), 'Mar 12, 2024');
      expect(DateLabels.dayMonth(date), 'Mar 12');
      final dt = DateLabels.dateTime(date);
      expect(dt, startsWith('Mar 12, 2024'));
      expect(dt, contains('2:05'));
      expect(dt, contains('PM'));
    });

    test('another initialised locale is used', () {
      expect(DateLabels.date(date, locale: 'de'), '12. März 2024');
    });

    test('an unknown locale falls back to English', () {
      expect(DateLabels.date(date, locale: 'zz'), 'Mar 12, 2024');
    });
  });

  group('NumberStyle', () {
    test('grouping sizes come from the locale pattern', () {
      final en = NumberStyle.forLocale('en');
      expect((en.primaryGroup, en.secondaryGroup), (3, 3));
      final india = NumberStyle.forLocale('en_IN');
      expect((india.primaryGroup, india.secondaryGroup), (3, 2));
    });

    test('renders without losing digits for very large values', () {
      final s = NumberStyle.forLocale('en');
      expect(
        s.renderUnsigned(Decimal.parse('123456789012345678901234567890.5'), 2),
        '123,456,789,012,345,678,901,234,567,890.50',
      );
      expect(s.renderUnsigned(Decimal.zero, 0), '0');
      expect(s.renderUnsigned(Decimal.parse('999'), 0), '999');
      expect(s.renderUnsigned(Decimal.parse('1000'), 0), '1,000');
    });

    test(
      'locales with a non-Latin digit set render every digit in that set',
      () {
        final localeWithOwnDigits = numberFormatSymbols.entries.firstWhere(
          (e) => e.value.ZERO_DIGIT != '0',
          orElse: () => numberFormatSymbols.entries.first,
        );
        // No locale with its own digits in this intl build: nothing to check.
        final hasOwnDigits = localeWithOwnDigits.value.ZERO_DIGIT != '0';
        if (!hasOwnDigits) {
          return;
        }
        final style = NumberStyle.forLocale(localeWithOwnDigits.key.toString());
        final text = style.renderUnsigned(Decimal.parse('1234567.89'), 2);
        expect(RegExp(r'[0-9]').hasMatch(text), isFalse, reason: text);
        expect(
          text.runes
              .where(
                (r) => r >= localeWithOwnDigits.value.ZERO_DIGIT.runes.first,
              )
              .length,
          greaterThan(5),
        );
      },
    );

    test('sign text respects the display mode and rounded zero', () {
      final s = NumberStyle.forLocale('en');
      expect(
        s.signText(SignDisplay.auto, isNegative: true, isZero: false),
        '-',
      );
      expect(
        s.signText(SignDisplay.auto, isNegative: false, isZero: false),
        '',
      );
      expect(
        s.signText(SignDisplay.always, isNegative: false, isZero: false),
        '+',
      );
      expect(
        s.signText(SignDisplay.always, isNegative: false, isZero: true),
        '',
      );
      expect(
        s.signText(SignDisplay.never, isNegative: true, isZero: false),
        '',
      );
    });
  });
}

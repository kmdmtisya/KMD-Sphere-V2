import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/l10n/generated/app_localizations.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../../helpers/pump_app.dart';

Widget page(Widget child) =>
    Scaffold(body: SingleChildScrollView(child: child));

void main() {
  group('CurrencyAmount', () {
    testWidgets('shows a formatted amount and speaks it as one phrase', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(CurrencyAmount(money: Money.parse('1234.50', 'USD'))),
      );
      expect(find.text(r'$1,234.50'), findsOneWidget);
      expect(find.bySemanticsLabel('1,234.50 USD'), findsOneWidget);
      handle.dispose();
    });

    testWidgets('negative amounts are spoken as "minus"', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(CurrencyAmount(money: Money.parse('-50.00', 'USD'))),
      );
      expect(find.bySemanticsLabel(RegExp('^minus 50.00 USD')), findsOneWidget);
      handle.dispose();
    });

    testWidgets('compact mode shortens large values', (tester) async {
      await tester.pumpApp(
        page(
          CurrencyAmount(
            money: Money.parse('1234567.89', 'USD'),
            compact: true,
          ),
        ),
      );
      expect(find.text(r'$1.2M'), findsOneWidget);
    });

    testWidgets('a native amount in another currency is shown and announced', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(
          CurrencyAmount(
            money: Money.parse('100.00', 'USD'),
            nativeMoney: Money.parse('367.30', 'AED'),
          ),
        ),
      );
      expect(find.textContaining('367.30'), findsOneWidget);
      expect(
        find.bySemanticsLabel(RegExp('original currency')),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('a native amount in the same currency is not repeated', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          CurrencyAmount(
            money: Money.parse('100.00', 'USD'),
            nativeMoney: Money.parse('100.00', 'USD'),
          ),
        ),
      );
      expect(find.textContaining('100.00'), findsOneWidget);
    });

    testWidgets('a very large value scales down rather than overflowing', (
      tester,
    ) async {
      await tester.pumpApp(
        page(CurrencyAmount(money: Money.parse('123456789012.34', 'USD'))),
        surfaceSize: const Size(200, 400),
        textScale: 2.0,
      );
      expect(tester.takeException(), isNull);
    });
  });

  group('ChangeIndicator', () {
    testWidgets('gain: up arrow, plus sign, spoken as "up"', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(
          ChangeIndicator(percent: Decimal.parse('2.5'), periodLabel: 'today'),
        ),
      );
      expect(find.byIcon(Icons.arrow_upward_rounded), findsOneWidget);
      expect(find.textContaining('+'), findsOneWidget);
      expect(
        find.bySemanticsLabel(RegExp(r'^up .*percent.* today$')),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('loss: down arrow and minus sign, never colour alone', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(ChangeIndicator(percent: Decimal.parse('-1.2'))),
      );
      expect(find.byIcon(Icons.arrow_downward_rounded), findsOneWidget);
      expect(find.textContaining('1.20'), findsOneWidget);
      expect(find.bySemanticsLabel(RegExp('^down ')), findsOneWidget);
      handle.dispose();
    });

    testWidgets('a value that rounds to zero is flat, not up or down', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(ChangeIndicator(percent: Decimal.parse('0.001'))),
      );
      expect(find.byIcon(Icons.arrow_upward_rounded), findsNothing);
      expect(find.byIcon(Icons.arrow_downward_rounded), findsNothing);
      expect(find.bySemanticsLabel(RegExp('unchanged')), findsOneWidget);
      handle.dispose();
    });

    testWidgets('shows amount and percent together', (tester) async {
      await tester.pumpApp(
        page(
          ChangeIndicator(
            percent: Decimal.parse('2.5'),
            amount: Money.parse('125.00', 'USD'),
          ),
        ),
      );
      expect(find.textContaining('125.00'), findsOneWidget);
      expect(find.textContaining('2.50'), findsOneWidget);
    });

    test('requires a percent or an amount', () {
      expect(() => ChangeIndicator(), throwsAssertionError);
    });
  });

  group('RiskLabel', () {
    testWidgets('each level has its own words and icon', (tester) async {
      final icons = <IconData>{};
      for (final (level, words) in [
        (RiskLevel.low, 'Low risk'),
        (RiskLevel.medium, 'Medium risk'),
        (RiskLevel.high, 'High risk'),
      ]) {
        await tester.pumpApp(page(RiskLabel(level: level)));
        expect(find.text(words), findsOneWidget);
        icons.add(tester.widget<Icon>(find.byType(Icon)).icon!);
      }
      expect(icons.length, 3, reason: 'levels must not rely on colour alone');
    });
  });

  group('DisclosurePanel', () {
    Widget panel({bool open = false}) => page(
      DisclosurePanel(
        title: 'Assumptions',
        summary: 'Past performance is not a guide.',
        details: const Text('Detail text'),
        initiallyExpanded: open,
      ),
    );

    testWidgets('summary is always visible; details are hidden until opened', (
      tester,
    ) async {
      await tester.pumpApp(panel());
      expect(find.text('Past performance is not a guide.'), findsOneWidget);
      expect(find.text('Detail text'), findsNothing);
      await tester.tap(find.text('Assumptions'));
      await tester.pumpAndSettle();
      expect(find.text('Detail text'), findsOneWidget);
      expect(find.text('Past performance is not a guide.'), findsOneWidget);
      await tester.tap(find.text('Assumptions'));
      await tester.pumpAndSettle();
      expect(find.text('Detail text'), findsNothing);
    });

    testWidgets('can start expanded', (tester) async {
      await tester.pumpApp(panel(open: true));
      expect(find.text('Detail text'), findsOneWidget);
    });

    testWidgets('announces its show/hide action to screen readers', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(panel());
      expect(find.bySemanticsLabel(RegExp('Assumptions')), findsWidgets);
      handle.dispose();
    });
  });

  group('Demo badge and banner', () {
    testWidgets('badge says DEMO and is announced as demo data', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(const DemoBadge()));
      expect(find.text('DEMO'), findsOneWidget);
      expect(find.bySemanticsLabel('Demo data'), findsOneWidget);
      handle.dispose();
    });

    testWidgets('banner explains the data is not connected to accounts', (
      tester,
    ) async {
      await tester.pumpApp(page(const DemoBanner()));
      expect(
        find.text('Demo data. Not connected to your accounts.'),
        findsOneWidget,
      );
    });
  });

  group('Data as-of label', () {
    final now = DateTime.utc(2026, 10, 9, 12);
    test('relative wording by age', () async {
      final l10n = await AppLocalizations.delegate.load(const Locale('en'));
      String t(Duration ago) =>
          dataAsOfText(l10n, now.subtract(ago), now: now, locale: 'en');
      expect(t(const Duration(seconds: 10)), 'As of just now');
      expect(t(const Duration(minutes: 1)), 'As of 1 minute ago');
      expect(t(const Duration(minutes: 5)), 'As of 5 minutes ago');
      expect(t(const Duration(hours: 1)), 'As of 1 hour ago');
      expect(t(const Duration(hours: 3)), 'As of 3 hours ago');
      expect(t(const Duration(days: 2)), 'As of 2 days ago');
    });

    testWidgets('old data falls back to a date', (tester) async {
      await tester.pumpApp(
        page(
          DataAsOfLabel(asOf: now.subtract(const Duration(days: 90)), now: now),
        ),
      );
      expect(find.textContaining('As of '), findsOneWidget);
      expect(find.textContaining('days ago'), findsNothing);
    });
  });
}

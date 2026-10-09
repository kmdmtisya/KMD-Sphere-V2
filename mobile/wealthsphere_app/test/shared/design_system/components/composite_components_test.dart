import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../../helpers/pump_app.dart';

Widget page(Widget child) =>
    Scaffold(body: SingleChildScrollView(child: child));

final usd = Money.parse('1234.50', 'USD');
final now = DateTime.utc(2026, 10, 9, 12);

void main() {
  group('WealthSummaryCard', () {
    testWidgets('lays out label, amount, change, chart, period and footer', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          WealthSummaryCard(
            label: 'Total wealth',
            amount: CurrencyAmount(money: usd),
            change: ChangeIndicator(percent: Decimal.parse('2.5')),
            chart: const SizedBox(key: Key('chart'), height: 80),
            periodSelector: PeriodSelector(
              periods: const [ChartPeriod.month, ChartPeriod.year],
              selected: ChartPeriod.month,
              onChanged: (_) {},
            ),
            footer: DataAsOfLabel(
              asOf: now.subtract(const Duration(hours: 2)),
              now: now,
            ),
          ),
        ),
      );
      expect(find.text('Total wealth'), findsOneWidget);
      expect(find.text(r'$1,234.50'), findsOneWidget);
      expect(find.byKey(const Key('chart')), findsOneWidget);
      expect(find.text('As of 2 hours ago'), findsOneWidget);
    });

    testWidgets('optional slots can be omitted', (tester) async {
      await tester.pumpApp(
        page(
          WealthSummaryCard(
            label: 'Net worth',
            amount: CurrencyAmount(money: usd),
          ),
        ),
      );
      expect(find.byType(PeriodSelector), findsNothing);
    });
  });

  group('MetricCard', () {
    testWidgets('shows label, value, sub-value, and is tappable', (
      tester,
    ) async {
      var taps = 0;
      await tester.pumpApp(
        page(
          MetricCard(
            icon: Icons.savings_outlined,
            label: 'Passive income',
            value: CurrencyAmount(money: usd),
            subValue: 'per month',
            onTap: () => taps++,
          ),
        ),
      );
      expect(find.text('per month'), findsOneWidget);
      await tester.tap(find.text('Passive income'));
      expect(taps, 1);
    });

    testWidgets('definition button shows a tooltip and is labelled', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(
          MetricCard(
            icon: Icons.percent,
            label: 'Yield',
            value: CurrencyAmount(money: usd),
            definition: 'Income as a share of value.',
          ),
        ),
      );
      expect(find.bySemanticsLabel('About Yield'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.info_outline_rounded));
      await tester.pump();
      expect(find.text('Income as a share of value.'), findsOneWidget);
      handle.dispose();
    });

    testWidgets('no info button without a definition', (tester) async {
      await tester.pumpApp(
        page(
          MetricCard(
            icon: Icons.percent,
            label: 'Yield',
            value: CurrencyAmount(money: usd),
          ),
        ),
      );
      expect(find.byIcon(Icons.info_outline_rounded), findsNothing);
    });
  });

  group('PeriodSelector', () {
    testWidgets('shows only the periods it is given and reports taps', (
      tester,
    ) async {
      final picked = <ChartPeriod>[];
      await tester.pumpApp(
        page(
          PeriodSelector(
            periods: const [
              ChartPeriod.week,
              ChartPeriod.month,
              ChartPeriod.all,
            ],
            selected: ChartPeriod.month,
            onChanged: picked.add,
          ),
        ),
      );
      expect(find.text('1W'), findsOneWidget);
      expect(find.text('1Y'), findsNothing);
      await tester.tap(find.text('ALL'));
      expect(picked, [ChartPeriod.all]);
    });

    testWidgets('every period has a distinct short and spoken label', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(
          PeriodSelector(
            periods: ChartPeriod.values,
            selected: ChartPeriod.yearToDate,
            onChanged: (_) {},
          ),
        ),
        surfaceSize: const Size(800, 600),
      );
      for (final spoken in ['1 week', '3 months', 'Year to date', 'All time']) {
        expect(find.bySemanticsLabel(spoken), findsOneWidget, reason: spoken);
      }
      handle.dispose();
    });

    testWidgets('needs at least two periods', (tester) async {
      expect(
        () => PeriodSelector(
          periods: const [ChartPeriod.week],
          selected: ChartPeriod.week,
          onChanged: (_) {},
        ),
        throwsAssertionError,
      );
    });
  });

  group('PortfolioSwitcher', () {
    final portfolios = [
      PortfolioOption(
        id: 'a',
        name: 'Retirement',
        value: Money.parse('1000.00', 'USD'),
      ),
      PortfolioOption(
        id: 'b',
        name: 'Growth',
        value: Money.parse('250.00', 'USD'),
      ),
    ];

    Widget switcher(String? selected, ValueChanged<String?> on) => page(
      PortfolioSwitcher(
        portfolios: portfolios,
        selectedId: selected,
        onSelected: on,
        consolidatedValue: Money.parse('1250.00', 'USD'),
      ),
    );

    testWidgets('shows the current portfolio, or the consolidated view', (
      tester,
    ) async {
      await tester.pumpApp(switcher('a', (_) {}));
      expect(find.text('Retirement'), findsOneWidget);
      await tester.pumpApp(switcher(null, (_) {}));
      expect(find.text('All portfolios (consolidated)'), findsOneWidget);
    });

    testWidgets('opens a sheet listing all options with values', (
      tester,
    ) async {
      await tester.pumpApp(switcher('a', (_) {}));
      await tester.tap(find.text('Retirement'));
      await tester.pumpAndSettle();
      expect(find.text('Select portfolio'), findsOneWidget);
      expect(find.text('All portfolios (consolidated)'), findsOneWidget);
      expect(find.text(r'$1,250.00'), findsOneWidget);
      expect(find.text('Growth'), findsOneWidget);
      expect(find.byIcon(Icons.check_rounded), findsOneWidget);
    });

    testWidgets('choosing a portfolio reports its id', (tester) async {
      final chosen = <String?>[];
      await tester.pumpApp(switcher('a', chosen.add));
      await tester.tap(find.text('Retirement'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Growth'));
      await tester.pumpAndSettle();
      expect(chosen, ['b']);
      expect(find.text('Select portfolio'), findsNothing);
    });

    testWidgets('choosing the consolidated view reports null', (tester) async {
      final chosen = <String?>[];
      await tester.pumpApp(switcher('a', chosen.add));
      await tester.tap(find.text('Retirement'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('All portfolios (consolidated)'));
      await tester.pumpAndSettle();
      expect(chosen, [null]);
    });

    testWidgets('dismissing the sheet changes nothing', (tester) async {
      final chosen = <String?>[];
      await tester.pumpApp(switcher('a', chosen.add));
      await tester.tap(find.text('Retirement'));
      await tester.pumpAndSettle();
      await tester.tapAt(const Offset(10, 10));
      await tester.pumpAndSettle();
      expect(chosen, isEmpty);
    });

    testWidgets('is announced as a button naming the portfolio', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(switcher('b', (_) {}));
      expect(
        find.bySemanticsLabel('Portfolio: Growth. Double tap to change.'),
        findsOneWidget,
      );
      handle.dispose();
    });
  });

  group('InvestmentRow', () {
    testWidgets('shows symbol, name, value, native value and change', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          InvestmentRow(
            symbol: 'AAPL',
            name: 'Apple Inc.',
            value: Money.parse('1500.00', 'USD'),
            nativeValue: Money.parse('1500.00', 'USD'),
            changePercent: Decimal.parse('1.5'),
          ),
        ),
      );
      expect(find.text('AAPL'), findsOneWidget);
      expect(find.text('Apple Inc.'), findsOneWidget);
      expect(find.text('AA'), findsOneWidget, reason: 'initials avatar');
      expect(find.textContaining('1,500.00'), findsOneWidget);
      expect(find.textContaining('1.50'), findsOneWidget);
    });

    testWidgets('tapping the row calls onTap', (tester) async {
      var taps = 0;
      await tester.pumpApp(
        page(
          InvestmentRow(
            symbol: 'X',
            name: 'Thing',
            value: usd,
            onTap: () => taps++,
          ),
        ),
      );
      await tester.tap(find.text('Thing'));
      expect(taps, 1);
      expect(
        find.text('X'),
        findsWidgets,
        reason: 'single-letter symbol avatar',
      );
    });

    testWidgets('an empty symbol still renders', (tester) async {
      await tester.pumpApp(
        page(InvestmentRow(symbol: ' ', name: 'Cash', value: usd)),
      );
      expect(find.text('?'), findsOneWidget);
    });
  });

  group('ScenarioCard', () {
    Widget card({required bool selected, VoidCallback? onSelected}) => page(
      ScenarioCard(
        name: 'Base',
        annualReturnPercent: Decimal.parse('7'),
        finalValue: Money.parse('1250000', 'USD'),
        selected: selected,
        onSelected: onSelected ?? () {},
      ),
    );

    testWidgets('shows name, assumption wording and projected value', (
      tester,
    ) async {
      await tester.pumpApp(card(selected: false));
      expect(find.text('Base'), findsOneWidget);
      expect(find.text('7.0% a year assumed'), findsOneWidget);
      expect(find.text('Projected value'), findsOneWidget);
      expect(find.text(r'$1.3M'), findsOneWidget);
    });

    testWidgets('selection is shown by an icon, not colour alone', (
      tester,
    ) async {
      await tester.pumpApp(card(selected: false));
      expect(find.byIcon(Icons.check_circle_rounded), findsNothing);
      await tester.pumpApp(card(selected: true));
      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
    });

    testWidgets('is a radio-style semantics node and says "Selected"', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(card(selected: true));
      expect(
        find.bySemanticsLabel(RegExp(r'Base, .*, Selected$')),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('tapping selects', (tester) async {
      var taps = 0;
      await tester.pumpApp(card(selected: false, onSelected: () => taps++));
      await tester.tap(find.text('Base'));
      expect(taps, 1);
    });
  });

  group('EvidenceSourceChip', () {
    final source = EvidenceSource(
      label: 'Price feed',
      provider: 'Example Data Co.',
      asOf: now.subtract(const Duration(hours: 3)),
    );

    testWidgets('shows the source and opens a detail sheet', (tester) async {
      await tester.pumpApp(page(EvidenceSourceChip(source: source, now: now)));
      expect(find.text('Price feed'), findsOneWidget);
      await tester.tap(find.text('Price feed'));
      await tester.pumpAndSettle();
      expect(find.text('Source details'), findsOneWidget);
      expect(find.text('Example Data Co.'), findsOneWidget);
      expect(find.text('As of 3 hours ago'), findsOneWidget);
      await tester.tap(find.text('Close'));
      await tester.pumpAndSettle();
      expect(find.text('Source details'), findsNothing);
    });

    testWidgets('has no link-like behaviour: text is never opened as a URL', (
      tester,
    ) async {
      final hostile = EvidenceSource(
        label: 'https://evil.example/x',
        provider: 'javascript:alert(1)',
        asOf: now,
      );
      await tester.pumpApp(page(EvidenceSourceChip(source: hostile, now: now)));
      await tester.tap(find.byType(ActionChip));
      await tester.pumpAndSettle();
      expect(find.text('javascript:alert(1)'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('is announced with source, provider and age', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(EvidenceSourceChip(source: source, now: now)));
      expect(
        find.bySemanticsLabel(
          'Source: Price feed, provider Example Data Co., As of 3 hours ago. Double tap for details.',
        ),
        findsOneWidget,
      );
      handle.dispose();
    });
  });

  group('AIChatComposer', () {
    final sendButton = find.widgetWithIcon(
      IconButton,
      Icons.arrow_upward_rounded,
    );

    testWidgets('send is disabled until there is non-blank text', (
      tester,
    ) async {
      await tester.pumpApp(page(AIChatComposer(onSend: (_) {})));
      expect(tester.widget<IconButton>(sendButton).onPressed, isNull);
      await tester.enterText(find.byType(TextField), '   ');
      await tester.pump();
      expect(tester.widget<IconButton>(sendButton).onPressed, isNull);
      await tester.enterText(find.byType(TextField), 'hello');
      await tester.pump();
      expect(tester.widget<IconButton>(sendButton).onPressed, isNotNull);
    });

    testWidgets('sending delivers trimmed text and clears the field', (
      tester,
    ) async {
      final sent = <String>[];
      await tester.pumpApp(page(AIChatComposer(onSend: sent.add)));
      await tester.enterText(
        find.byType(TextField),
        '  How is my portfolio?  ',
      );
      await tester.pump();
      await tester.tap(sendButton);
      await tester.pump();
      expect(sent, ['How is my portfolio?']);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        isEmpty,
      );
    });

    testWidgets('while streaming it shows stop instead of send', (
      tester,
    ) async {
      var stopped = 0;
      await tester.pumpApp(
        page(
          AIChatComposer(
            onSend: (_) {},
            streaming: true,
            onStop: () => stopped++,
          ),
        ),
      );
      expect(sendButton, findsNothing);
      await tester.tap(find.byIcon(Icons.stop_rounded));
      expect(stopped, 1);
    });

    testWidgets('input beyond the maximum is not accepted', (tester) async {
      await tester.pumpApp(page(AIChatComposer(onSend: (_) {}, maxLength: 10)));
      await tester.enterText(find.byType(TextField), 'abcdefghijklmnop');
      await tester.pump();
      expect(
        tester
            .widget<TextField>(find.byType(TextField))
            .controller!
            .text
            .length,
        10,
      );
    });

    testWidgets('a counter appears only near the limit', (tester) async {
      await tester.pumpApp(page(AIChatComposer(onSend: (_) {}, maxLength: 10)));
      await tester.enterText(find.byType(TextField), 'abc');
      await tester.pump();
      expect(find.text('3 of 10'), findsNothing);
      await tester.enterText(find.byType(TextField), 'abcdefghi');
      await tester.pump();
      expect(find.text('9 of 10'), findsOneWidget);
    });

    testWidgets('buttons are labelled for screen readers', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(AIChatComposer(onSend: (_) {})));
      expect(find.byTooltip('Send'), findsOneWidget);
      handle.dispose();
    });
  });

  group('Variant matrix: light/dark x LTR/RTL x text 1.0/2.0 on 320x568', () {
    final builders = <String, Widget Function()>{
      'summary card': () => WealthSummaryCard(
        label: 'Total wealth',
        amount: CurrencyAmount(money: Money.parse('123456789.12', 'USD')),
        change: ChangeIndicator(
          percent: Decimal.parse('-3.2'),
          periodLabel: 'this year',
        ),
        periodSelector: PeriodSelector(
          periods: const [
            ChartPeriod.week,
            ChartPeriod.month,
            ChartPeriod.year,
            ChartPeriod.all,
          ],
          selected: ChartPeriod.year,
          onChanged: (_) {},
        ),
        footer: DataAsOfLabel(asOf: now, now: now),
      ),
      'metric card': () => MetricCard(
        icon: Icons.savings_outlined,
        label: 'Projected passive income each month',
        value: CurrencyAmount(money: usd),
        subValue: 'illustrative',
        definition: 'Definition',
      ),
      'investment row': () => InvestmentRow(
        symbol: 'BRK.B',
        name: 'Berkshire Hathaway Inc. Class B',
        value: Money.parse('98765432.10', 'USD'),
        nativeValue: Money.parse('362000000.00', 'AED'),
        changePercent: Decimal.parse('12.34'),
      ),
      'scenario card': () => ScenarioCard(
        name: 'Conservative',
        annualReturnPercent: Decimal.parse('4'),
        finalValue: Money.parse('987654321', 'USD'),
        selected: true,
        onSelected: () {},
      ),
      'evidence chip': () => EvidenceSourceChip(
        source: EvidenceSource(
          label: 'A very long source name for a price feed',
          provider: 'P',
          asOf: now,
        ),
        now: now,
      ),
      'composer': () => AIChatComposer(onSend: (_) {}),
      'switcher': () => PortfolioSwitcher(
        portfolios: const [
          PortfolioOption(id: 'a', name: 'A long portfolio name that wraps'),
        ],
        selectedId: 'a',
        onSelected: (_) {},
      ),
    };

    for (final name in builders.keys) {
      for (final mode in [ThemeMode.light, ThemeMode.dark]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          for (final scale in [1.0, 2.0]) {
            testWidgets('$name / ${mode.name} / ${dir.name} / ${scale}x', (
              tester,
            ) async {
              await tester.pumpApp(
                page(
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: builders[name]!(),
                  ),
                ),
                themeMode: mode,
                textDirection: dir,
                textScale: scale,
                surfaceSize: const Size(320, 568),
              );
              expect(tester.takeException(), isNull);
            });
          }
        }
      }
    }
  });
}

import 'package:decimal/decimal.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/l10n/generated/app_localizations.dart';
import 'package:wealthsphere_app/shared/design_system/charts/charts.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../../helpers/pump_app.dart';

Widget page(Widget child) =>
    Scaffold(body: SingleChildScrollView(child: child));

ChartPoint pt(int month, String y) =>
    ChartPoint(DateTime.utc(2026, month, 1), Decimal.parse(y));

ChartSeries series(
  List<ChartPoint> points, {
  String label = 'Portfolio value',
}) => ChartSeries(id: 'p', label: label, currencyCode: 'USD', points: points);

Future<String> summary(ChartSeries s, {String? range}) async {
  final l10n = await AppLocalizations.delegate.load(const Locale('en'));
  return ChartSemantics.summarize(
    l10n,
    s,
    money: const MoneyFormatter(),
    locale: 'en',
    rangeLabel: range,
  );
}

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('ChartSemantics.summarize', () {
    test('rising series: start, end, range, high and low with dates', () async {
      final s = series([
        pt(1, '1000'),
        pt(2, '1500'),
        pt(3, '900'),
        pt(4, '1200'),
      ]);
      expect(
        await summary(s, range: '1 year'),
        r'Portfolio value rose from $1,000.00 to $1,200.00 over 1 year. '
        r'High $1,500.00 on Feb 1, 2026, low $900.00 on Mar 1, 2026.',
      );
    });

    test('falling series', () async {
      final s = series([pt(1, '2000'), pt(2, '1000')]);
      expect(
        await summary(s, range: '1 month'),
        startsWith(
          r'Portfolio value fell from $2,000.00 to $1,000.00 over 1 month.',
        ),
      );
    });

    test('flat series', () async {
      final s = series([pt(1, '500'), pt(2, '700'), pt(3, '500')]);
      final text = await summary(s, range: '3 months');
      expect(
        text,
        startsWith(r'Portfolio value stayed at $500.00 over 3 months.'),
      );
      expect(text, contains(r'High $700.00'));
    });

    test('single point and empty series', () async {
      expect(
        await summary(series([pt(1, '10')])),
        r'Portfolio value: $10.00 on Jan 1, 2026.',
      );
      expect(await summary(series([])), 'No data to chart yet');
    });

    test('without a range label the first and last dates are used', () async {
      final text = await summary(series([pt(1, '1'), pt(2, '2')]));
      expect(text, contains('Jan 1, 2026 – Feb 1, 2026'));
    });

    test(
      'amounts above 2^53 keep every digit (no double in the summary)',
      () async {
        final big = series([
          pt(1, '9007199254740993.01'),
          pt(2, '9007199254740995.02'),
        ]);
        final text = await summary(big, range: 'r');
        expect(text, contains(r'$9,007,199,254,740,993.01'));
        expect(text, contains(r'$9,007,199,254,740,995.02'));
      },
    );

    test('ChartSeries rejects out-of-order points', () {
      expect(() => series([pt(2, '1'), pt(1, '2')]), throwsAssertionError);
    });
  });

  group('PerformanceLineChart', () {
    testWidgets('draws a line chart for data', (tester) async {
      await tester.pumpApp(
        page(
          PerformanceLineChart(
            series: series([pt(1, '1'), pt(2, '3'), pt(3, '2')]),
          ),
        ),
      );
      expect(find.byType(LineChart), findsOneWidget);
    });

    testWidgets('empty series shows a message, not an empty box', (
      tester,
    ) async {
      await tester.pumpApp(page(PerformanceLineChart(series: series([]))));
      expect(find.byType(LineChart), findsNothing);
      expect(find.text('No data to chart yet'), findsOneWidget);
    });

    testWidgets('a single point renders without error', (tester) async {
      await tester.pumpApp(
        page(PerformanceLineChart(series: series([pt(1, '5')]))),
      );
      expect(find.byType(LineChart), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('loading shows the skeleton instead of the chart', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          PerformanceLineChart(
            series: series([pt(1, '1'), pt(2, '2')]),
            loading: true,
          ),
        ),
        settle: false,
      );
      expect(find.byType(LineChart), findsNothing);
      expect(find.bySemanticsLabel('Loading'), findsOneWidget);
      expect(find.byType(ShaderMask), findsOneWidget);
    });

    testWidgets('screen readers get the summary instead of the drawing', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(
          PerformanceLineChart(
            series: series([pt(1, '1000'), pt(2, '1200')]),
            rangeLabel: '1 month',
          ),
        ),
      );
      expect(
        find.bySemanticsLabel(
          RegExp(
            r'^Portfolio value rose from \$1,000.00 to \$1,200.00 over 1 month',
          ),
        ),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets(
      '"View as table" lists exact formatted values and toggles back',
      (tester) async {
        await tester.pumpApp(
          page(
            PerformanceLineChart(
              series: series([pt(1, '1000.5'), pt(2, '1200.25')]),
            ),
          ),
        );
        await tester.tap(find.text('View as table'));
        await tester.pumpAndSettle();
        expect(find.byType(LineChart), findsNothing);
        expect(find.text(r'$1,000.50'), findsOneWidget);
        expect(find.text(r'$1,200.25'), findsOneWidget);
        expect(find.text('Date'), findsOneWidget);
        await tester.tap(find.text('View as chart'));
        await tester.pumpAndSettle();
        expect(find.byType(LineChart), findsOneWidget);
      },
    );

    testWidgets('touch tooltip shows the exact formatted value and date', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          PerformanceLineChart(
            series: series([
              pt(1, '1000.50'),
              pt(2, '1200.25'),
              pt(3, '1100.75'),
            ]),
          ),
        ),
      );
      final chart = tester.widget<LineChart>(find.byType(LineChart));
      final tip = chart.data.lineTouchData.touchTooltipData;
      final bar = chart.data.lineBarsData.first;
      final items = tip.getTooltipItems([LineBarSpot(bar, 0, bar.spots[1])]);
      expect(items.single!.text, 'Feb 1, 2026\n\$1,200.25');
    });

    testWidgets(
      'plot coordinates are the only doubles; labels come from Decimals',
      (tester) async {
        // 0.1 + 0.2 style digits must survive in the table, proving labels use the Decimal.
        await tester.pumpApp(
          page(
            PerformanceLineChart(
              series: series([pt(1, '0.10'), pt(2, '0.30')]),
            ),
          ),
        );
        await tester.tap(find.text('View as table'));
        await tester.pumpAndSettle();
        expect(find.text(r'$0.10'), findsOneWidget);
        expect(find.text(r'$0.30'), findsOneWidget);
      },
    );

    testWidgets('reduced motion: no chart animation', (tester) async {
      await tester.pumpApp(
        page(
          Builder(
            builder: (context) => MediaQuery(
              data: MediaQuery.of(context).copyWith(disableAnimations: true),
              child: PerformanceLineChart(
                series: series([pt(1, '1'), pt(2, '2')]),
              ),
            ),
          ),
        ),
      );
      expect(
        tester.widget<LineChart>(find.byType(LineChart)).duration,
        Duration.zero,
      );
    });
  });

  group('AllocationDonutChart', () {
    final slices = [
      AllocationSlice(
        id: 'eq',
        label: 'Equities',
        percent: Decimal.parse('60'),
      ),
      AllocationSlice(id: 'bd', label: 'Bonds', percent: Decimal.parse('30.5')),
      AllocationSlice(id: 'ca', label: 'Cash', percent: Decimal.parse('9.5')),
    ];

    testWidgets('draws a donut and a legend with labels and percentages', (
      tester,
    ) async {
      await tester.pumpApp(
        page(AllocationDonutChart(slices: slices, centre: const Text('Mix'))),
      );
      expect(find.byType(PieChart), findsOneWidget);
      expect(find.text('Mix'), findsOneWidget);
      for (final label in ['Equities', 'Bonds', 'Cash']) {
        expect(find.text(label), findsOneWidget);
      }
      expect(find.text('60.00%'), findsOneWidget);
      expect(find.text('30.50%'), findsOneWidget);
    });

    testWidgets('slice sizes are the supplied percentages, not recomputed', (
      tester,
    ) async {
      await tester.pumpApp(page(AllocationDonutChart(slices: slices)));
      final sections = tester
          .widget<PieChart>(find.byType(PieChart))
          .data
          .sections;
      expect(sections.map((s) => s.value), [60.0, 30.5, 9.5]);
    });

    testWidgets(
      'tapping a legend row highlights its slice; tapping again clears it',
      (tester) async {
        await tester.pumpApp(page(AllocationDonutChart(slices: slices)));
        double radiusOf(int i) => tester
            .widget<PieChart>(find.byType(PieChart))
            .data
            .sections[i]
            .radius;
        expect(radiusOf(1), radiusOf(0));
        await tester.tap(find.text('Bonds'));
        await tester.pump();
        expect(radiusOf(1), greaterThan(radiusOf(0)));
        await tester.tap(find.text('Bonds'));
        await tester.pump();
        expect(radiusOf(1), radiusOf(0));
      },
    );

    testWidgets('legend rows are announced and selectable', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(AllocationDonutChart(slices: slices)));
      expect(find.bySemanticsLabel('Equities, 60.00%'), findsWidgets);
      handle.dispose();
    });

    testWidgets('table view and summary', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(AllocationDonutChart(slices: slices)));
      expect(
        find.bySemanticsLabel(
          'Allocation: Equities, 60.00%, Bonds, 30.50%, Cash, 9.50%.',
        ),
        findsOneWidget,
      );
      await tester.tap(find.text('View as table'));
      await tester.pumpAndSettle();
      expect(find.text('Name'), findsOneWidget);
      handle.dispose();
    });

    testWidgets('empty allocation shows a message and no legend', (
      tester,
    ) async {
      await tester.pumpApp(page(const AllocationDonutChart(slices: [])));
      expect(find.byType(PieChart), findsNothing);
      expect(find.byType(AllocationLegend), findsNothing);
      expect(find.text('No data to chart yet'), findsOneWidget);
    });

    testWidgets('more slices than palette colours still render', (
      tester,
    ) async {
      final many = [
        for (var i = 0; i < 12; i++)
          AllocationSlice(
            id: '$i',
            label: 'S$i',
            percent: Decimal.parse('8.33'),
          ),
      ];
      await tester.pumpApp(
        page(AllocationDonutChart(slices: many)),
        surfaceSize: const Size(400, 1200),
      );
      expect(tester.takeException(), isNull);
    });
  });

  group('ForecastComparisonChart', () {
    ForecastSeries fs(String id, String label, List<String> values) =>
        ForecastSeries(
          id: id,
          label: label,
          currencyCode: 'USD',
          points: [
            for (var i = 0; i < values.length; i++)
              ForecastPoint(i * 5, Decimal.parse(values[i])),
          ],
        );
    final all = [
      fs('cons', 'Conservative', ['1000', '1200', '1500']),
      fs('base', 'Base', ['1000', '1400', '2000']),
      fs('grow', 'Growth', ['1000', '1700', '2800']),
    ];

    testWidgets(
      'selected line is solid and thick; the others are dashed and thinner',
      (tester) async {
        await tester.pumpApp(
          page(ForecastComparisonChart(series: all, selectedId: 'base')),
        );
        final bars = tester
            .widget<LineChart>(find.byType(LineChart))
            .data
            .lineBarsData;
        expect(bars[1].dashArray, isNull);
        expect(bars[0].dashArray, isNotNull);
        expect(bars[2].dashArray, isNotNull);
        expect(bars[1].barWidth, greaterThan(bars[0].barWidth));
      },
    );

    testWidgets('changing the selection changes the emphasis', (tester) async {
      await tester.pumpApp(
        page(ForecastComparisonChart(series: all, selectedId: 'grow')),
      );
      final bars = tester
          .widget<LineChart>(find.byType(LineChart))
          .data
          .lineBarsData;
      expect(bars[2].dashArray, isNull);
      expect(bars[1].dashArray, isNotNull);
    });

    testWidgets(
      'legend names every series and marks the selected one in words',
      (tester) async {
        await tester.pumpApp(
          page(ForecastComparisonChart(series: all, selectedId: 'base')),
        );
        expect(find.text('Conservative'), findsOneWidget);
        expect(find.text('Base (selected)'), findsOneWidget);
        expect(find.text('Growth'), findsOneWidget);
      },
    );

    testWidgets('screen-reader summary gives each end value', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(ForecastComparisonChart(series: all, selectedId: 'base')),
      );
      expect(
        find.bySemanticsLabel(
          r'Forecast comparison. Conservative: $1.5K after 10 years. Base: $2K after 10 years. Growth: $2.8K after 10 years.',
        ),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('table view has a column per scenario', (tester) async {
      await tester.pumpApp(
        page(ForecastComparisonChart(series: all, selectedId: 'base')),
      );
      await tester.tap(find.text('View as table'));
      await tester.pumpAndSettle();
      expect(find.text('Year'), findsOneWidget);
      expect(find.text(r'$2,800.00'), findsOneWidget);
    });

    testWidgets('tooltip names the scenario, year and compact value', (
      tester,
    ) async {
      await tester.pumpApp(
        page(ForecastComparisonChart(series: all, selectedId: 'base')),
      );
      final chart = tester.widget<LineChart>(find.byType(LineChart));
      final bar = chart.data.lineBarsData[1];
      final items = chart.data.lineTouchData.touchTooltipData.getTooltipItems([
        LineBarSpot(bar, 1, bar.spots[2]),
      ]);
      expect(items.single!.text, 'Base\n10 years: \$2K');
    });

    testWidgets('more than three scenarios is rejected', (tester) async {
      expect(
        () => ForecastComparisonChart(
          series: [
            ...all,
            fs('x', 'X', ['1']),
          ],
          selectedId: 'base',
        ),
        throwsAssertionError,
      );
    });

    testWidgets('no points shows the empty message', (tester) async {
      await tester.pumpApp(
        page(
          ForecastComparisonChart(series: [fs('a', 'A', [])], selectedId: 'a'),
        ),
      );
      expect(find.text('No data to chart yet'), findsOneWidget);
    });
  });

  group('Variant matrix: light/dark x LTR/RTL x text 1.0/2.0 on 320x568', () {
    final line = series([
      pt(1, '1000'),
      pt(2, '1500'),
      pt(3, '900'),
      pt(4, '1200'),
    ]);
    final builders = <String, Widget Function()>{
      'line': () => PerformanceLineChart(series: line),
      'donut': () => AllocationDonutChart(
        centre: const Text('Mix'),
        slices: [
          AllocationSlice(
            id: 'a',
            label: 'A long asset class name',
            percent: Decimal.parse('55.5'),
          ),
          AllocationSlice(
            id: 'b',
            label: 'Bonds',
            percent: Decimal.parse('44.5'),
          ),
        ],
      ),
      'forecast': () => ForecastComparisonChart(
        selectedId: 'b',
        series: [
          ForecastSeries(
            id: 'a',
            label: 'Conservative',
            currencyCode: 'USD',
            points: [
              ForecastPoint(0, Decimal.parse('1')),
              ForecastPoint(10, Decimal.parse('2')),
            ],
          ),
          ForecastSeries(
            id: 'b',
            label: 'Base',
            currencyCode: 'USD',
            points: [
              ForecastPoint(0, Decimal.parse('1')),
              ForecastPoint(10, Decimal.parse('3')),
            ],
          ),
        ],
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

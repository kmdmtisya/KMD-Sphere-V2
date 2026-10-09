@Tags(['golden'])
library;

import 'dart:io';

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/charts/charts.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../../helpers/pump_app.dart';
import '../../../helpers/test_fonts.dart';

// Golden images are authoritative on the CI Linux runner (dart_test.yaml). Other platforms render
// text slightly differently, so the comparison is skipped there instead of producing false failures.
final Object _skip = Platform.isLinux
    ? false
    : 'Golden images are only authoritative on the CI Linux runner';

ChartPoint _pt(int month, String y) =>
    ChartPoint(DateTime.utc(2026, month, 1), Decimal.parse(y));

Widget _frame(Widget child) => Scaffold(
  body: Padding(padding: const EdgeInsets.all(16), child: child),
);

void main() {
  setUpAll(() async {
    await loadTestFonts();
    await initializeDateLabels(['en']);
  });

  final charts = <String, Widget Function()>{
    'performance_line': () => PerformanceLineChart(
      rangeLabel: '6 months',
      series: ChartSeries(
        id: 'p',
        label: 'Portfolio value',
        currencyCode: 'USD',
        points: [
          _pt(1, '100000'),
          _pt(2, '104500'),
          _pt(3, '101200'),
          _pt(4, '110800'),
          _pt(5, '118300'),
          _pt(6, '121900'),
        ],
      ),
    ),
    'allocation_donut': () => AllocationDonutChart(
      centre: const Text('Mix'),
      slices: [
        AllocationSlice(
          id: 'eq',
          label: 'Equities',
          percent: Decimal.parse('52'),
        ),
        AllocationSlice(id: 'bd', label: 'Bonds', percent: Decimal.parse('23')),
        AllocationSlice(id: 'cs', label: 'Cash', percent: Decimal.parse('10')),
        AllocationSlice(
          id: 're',
          label: 'Real estate',
          percent: Decimal.parse('15'),
        ),
      ],
    ),
    'forecast_comparison': () => ForecastComparisonChart(
      selectedId: 'base',
      series: [
        for (final (id, label, end) in [
          ('cons', 'Conservative', '150000'),
          ('base', 'Base', '210000'),
          ('grow', 'Growth', '300000'),
        ])
          ForecastSeries(
            id: id,
            label: label,
            currencyCode: 'USD',
            points: [
              ForecastPoint(0, Decimal.parse('100000')),
              ForecastPoint(10, Decimal.parse(end)),
            ],
          ),
      ],
    ),
  };

  for (final entry in charts.entries) {
    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      testWidgets('${entry.key} (${mode.name})', (tester) async {
        await tester.pumpApp(
          _frame(entry.value()),
          themeMode: mode,
          surfaceSize: const Size(360, 520),
        );
        await expectLater(
          find.byType(Scaffold),
          matchesGoldenFile('goldens/${entry.key}_${mode.name}.png'),
        );
      }, skip: _skip != false);
    }
  }
}

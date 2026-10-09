import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/data/json_reader.dart';
import 'package:wealthsphere_app/features/calculator/application/calculator_providers.dart';
import 'package:wealthsphere_app/features/calculator/domain/forecast_input_limits.dart';
import 'package:wealthsphere_app/features/calculator/presentation/forecast/forecast_screen.dart';
import 'package:wealthsphere_app/features/forecast/data/forecast_repository.dart';
import 'package:wealthsphere_app/features/forecast/domain/forecast_models.dart';
import 'package:wealthsphere_app/shared/design_system/charts/charts.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';

class _Seeded extends ForecastResultNotifier {
  _Seeded(this._result);

  final ForecastResult? _result;

  @override
  ForecastResult? build() => _result;
}

Future<CompoundForecastResponse> cannedResponse() => DemoForecastRepository(
  DemoAssets(SyncFileBundle()),
  () async {},
).compound(ForecastInputLimits.defaults);

const money = MoneyFormatter();

Future<CompoundForecastResponse> pumpForecast(
  WidgetTester tester, {
  CompoundForecastRequest? request,
  bool noResult = false,
  Size size = const Size(400, 3200),
  double textScale = 1.0,
  ThemeMode mode = ThemeMode.light,
  TextDirection dir = TextDirection.ltr,
}) async {
  final response = await cannedResponse();
  await tester.pumpApp(
    const ForecastScreen(),
    overrides: demoOverrides(
      extra: [
        forecastResultProvider.overrideWith(
          () => _Seeded(
            noResult
                ? null
                : ForecastResult(
                    request: request ?? ForecastInputLimits.defaults,
                    response: response,
                  ),
          ),
        ),
      ],
    ),
    surfaceSize: size,
    textScale: textScale,
    themeMode: mode,
    textDirection: dir,
  );
  return response;
}

String finalShown(WidgetTester tester) => tester
    .widget<CurrencyAmount>(find.byKey(const ValueKey('final-value')))
    .money
    .toJson()['amount']!;

ForecastComparisonChart chart(WidgetTester tester) => tester
    .widget<ForecastComparisonChart>(find.byType(ForecastComparisonChart));

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  testWidgets('without a result it points to the calculator', (tester) async {
    await pumpForecast(tester, noResult: true);
    expect(find.text('No forecast yet'), findsOneWidget);
    expect(find.text('Open calculator'), findsOneWidget);
    expect(find.byType(ForecastComparisonChart), findsNothing);
  });

  group('scenarios', () {
    testWidgets(
      'base is selected by default and drives the final value and chart',
      (tester) async {
        final r = await pumpForecast(tester);
        final base = r.scenarios[ForecastScenarioKind.base]!;
        expect(finalShown(tester), base.finalNominal.amount.toString());
        expect(find.text(money.format(base.finalNominal)), findsOneWidget);
        expect(chart(tester).selectedId, 'base');
        expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
        expect(find.text('Projected value after 20 years'), findsOneWidget);
      },
    );

    testWidgets('each card shows its rate and final value from the response', (
      tester,
    ) async {
      final r = await pumpForecast(tester);
      for (final kind in ForecastScenarioKind.values) {
        final s = r.scenarios[kind]!;
        final card = tester.widget<ScenarioCard>(
          find.byKey(ValueKey('scenario-${kind.name}')),
        );
        expect(
          card.annualReturnPercent,
          s.annualReturnPercent,
          reason: kind.name,
        );
        expect(card.finalValue, s.finalNominal, reason: kind.name);
      }
    });

    testWidgets(
      'tapping a scenario updates the value, chart, breakdown and selection',
      (tester) async {
        final r = await pumpForecast(tester);
        final growth = r.scenarios[ForecastScenarioKind.growth]!;
        await tester.tap(find.byKey(const ValueKey('scenario-growth')));
        await tester.pumpAndSettle();
        expect(finalShown(tester), growth.finalNominal.amount.toString());
        expect(chart(tester).selectedId, 'growth');
        expect(find.text(money.format(growth.totalGrowth)), findsOneWidget);
        expect(
          tester
              .widget<ScenarioCard>(
                find.byKey(const ValueKey('scenario-growth')),
              )
              .selected,
          isTrue,
        );
        expect(
          tester
              .widget<ScenarioCard>(find.byKey(const ValueKey('scenario-base')))
              .selected,
          isFalse,
        );
      },
    );

    testWidgets('selection is announced to screen readers', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpForecast(tester);
      await tester.tap(find.byKey(const ValueKey('scenario-conservative')));
      await tester.pumpAndSettle();
      expect(
        find.bySemanticsLabel(RegExp(r'^Conservative, .*Selected$')),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(RegExp(r'^Base, .*Selected$')),
        findsNothing,
      );
      handle.dispose();
    });
  });

  group('nominal and real', () {
    testWidgets(
      "Today's money swaps to the response's real values (no client inflation maths)",
      (tester) async {
        final r = await pumpForecast(tester);
        final base = r.scenarios[ForecastScenarioKind.base]!;
        await tester.tap(find.text("Today's money"));
        await tester.pumpAndSettle();
        expect(finalShown(tester), base.finalReal.amount.toString());
        final baseSeries = chart(tester).series
            .firstWhere((s) => s.id == 'base');
        expect(
          baseSeries.points.map((p) => p.value),
          base.real.map((p) => p.value),
        );
        for (final kind in ForecastScenarioKind.values) {
          final card = tester.widget<ScenarioCard>(
            find.byKey(ValueKey('scenario-${kind.name}')),
          );
          expect(card.finalValue, r.scenarios[kind]!.finalReal);
        }
        await tester.tap(find.text('Nominal'));
        await tester.pumpAndSettle();
        expect(finalShown(tester), base.finalNominal.amount.toString());
      },
    );

    testWidgets(
      'the contributions vs growth breakdown is from the response and labelled nominal',
      (tester) async {
        final r = await pumpForecast(tester);
        final base = r.scenarios[ForecastScenarioKind.base]!;
        expect(
          find.text(money.format(base.totalContributions)),
          findsOneWidget,
        );
        expect(find.text(money.format(base.totalGrowth)), findsOneWidget);
        expect(find.text('Your contributions'), findsOneWidget);
        expect(find.text('Investment growth'), findsOneWidget);
        expect(find.text('Shown before inflation.'), findsOneWidget);
      },
    );

    testWidgets('the breakdown bar is spoken with both amounts', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      final r = await pumpForecast(tester);
      final base = r.scenarios[ForecastScenarioKind.base]!;
      expect(
        find.bySemanticsLabel(
          '${money.format(base.totalContributions)} from your contributions and ${money.format(base.totalGrowth)} from investment growth',
        ),
        findsOneWidget,
      );
      handle.dispose();
    });
  });

  group('assumptions and honesty', () {
    testWidgets(
      '"not guaranteed" is always visible; details echo every input',
      (tester) async {
        await pumpForecast(tester);
        expect(
          find.textContaining('Projections are not guaranteed'),
          findsOneWidget,
        );
        expect(
          find.text(r'$10,000.00'),
          findsNothing,
          reason: 'details are collapsed',
        );
        await tester.tap(find.text('Assumptions'));
        await tester.pumpAndSettle();
        for (final value in [
          r'$10,000.00',
          r'$500.00',
          '20 years',
          '5.00% / 8.00% / 12.00% a year (conservative / base / growth)',
          '2.50%',
          '0.50%',
          '0.00%',
        ]) {
          expect(find.text(value), findsOneWidget, reason: value);
        }
        expect(find.text('Monthly'), findsNWidgets(2));
        expect(
          find.textContaining('not guaranteed', findRichText: true),
          findsWidgets,
        );
      },
    );

    testWidgets(
      'demo notice appears only when the inputs differ from the sample',
      (tester) async {
        await pumpForecast(tester);
        expect(
          find.textContaining('Demo projection for the default inputs'),
          findsNothing,
        );
        await tester.pumpWidget(const SizedBox());
        final other = CompoundForecastRequest.fromJson(
          JsonReader({...ForecastInputLimits.defaults.toJson(), 'years': 10}),
        );
        await pumpForecast(tester, request: other);
        expect(
          find.textContaining('Demo projection for the default inputs'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'every amount shown outside the chart is a field of the response',
      (tester) async {
        final r = await pumpForecast(tester);
        await tester.tap(find.text('Assumptions'));
        await tester.pumpAndSettle();
        final allowed = <String>{};
        void add(Money m) => allowed
          ..add(money.format(m))
          ..add(money.formatCompact(m));
        for (final s in r.scenarios.values) {
          for (final m in [
            s.finalNominal,
            s.finalReal,
            s.totalContributions,
            s.totalGrowth,
          ]) {
            add(m);
          }
        }
        add(r.assumptions.initialInvestment);
        add(r.assumptions.monthlyContribution);

        final insideChart = find
            .descendant(
              of: find.byType(ForecastComparisonChart),
              matching: find.byType(Text),
            )
            .evaluate()
            .map((e) => e.widget)
            .toSet();
        final amountPattern = RegExp(r'\$[\d,]+(\.\d+)?[KMBT]?');
        for (final e in find.byType(Text).evaluate()) {
          final widget = e.widget as Text;
          if (insideChart.contains(widget)) continue;
          for (final m in amountPattern.allMatches(widget.data ?? '')) {
            expect(
              allowed,
              contains(m.group(0)),
              reason: 'untraceable amount "${m.group(0)}" in "${widget.data}"',
            );
          }
        }
      },
    );
  });

  group('navigation', () {
    testWidgets(
      'Ask AI carries the forecast scope, Edit assumptions returns to the calculator',
      (tester) async {
        final router = await pumpRouterApp(
          tester,
          initialLocation: AppRoutes.calculator,
          surfaceSize: const Size(400, 3200),
        );
        await tester.ensureVisible(find.text('Calculate'));
        await tester.tap(find.text('Calculate'));
        await tester.pumpAndSettle();
        expect(find.byType(ForecastScreen), findsOneWidget);

        await tester.ensureVisible(find.text('Edit assumptions'));
        await tester.tap(find.text('Edit assumptions'));
        await tester.pumpAndSettle();
        expect(find.byType(ForecastScreen), findsNothing);
        expect(find.text('Calculate'), findsOneWidget);

        await tester.tap(find.text('Calculate'));
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('Ask AI about this forecast'));
        await tester.tap(find.text('Ask AI about this forecast'));
        await tester.pumpAndSettle();
        final uri = router.routerDelegate.currentConfiguration.uri;
        expect(uri.path, AppRoutes.ai);
        expect(
          AiScope.tryParse(uri.queryParameters['scope']),
          const AiScope(AiScopeKind.forecast, 'current'),
        );
      },
    );

    testWidgets('Open calculator from the empty state', (tester) async {
      final router = await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.forecast,
      );
      await tester.tap(find.text('Open calculator'));
      await tester.pumpAndSettle();
      expect(
        router.routerDelegate.currentConfiguration.uri.path,
        AppRoutes.calculator,
      );
    });
  });

  group('layout', () {
    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
        for (final scale in [1.0, 2.0]) {
          testWidgets(
            '320 wide, ${mode.name}, ${dir.name}, ${scale}x: no overflow',
            (tester) async {
              await pumpForecast(
                tester,
                size: const Size(320, 6000),
                mode: mode,
                dir: dir,
                textScale: scale,
                request: CompoundForecastRequest.fromJson(
                  JsonReader({
                    ...ForecastInputLimits.defaults.toJson(),
                    'years': 10,
                  }),
                ),
              );
              await tester.tap(find.text("Today's money"));
              await tester.pumpAndSettle();
              await tester.tap(find.text('Assumptions'));
              await tester.pumpAndSettle();
              expect(tester.takeException(), isNull);
            },
          );
        }
      }
    }
  });
}

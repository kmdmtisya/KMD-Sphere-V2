import 'dart:async';

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart' show ProviderScope;
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/calculator/application/calculator_providers.dart';
import 'package:wealthsphere_app/features/calculator/presentation/calculator_screen.dart';
import 'package:wealthsphere_app/features/forecast/data/forecast_repository.dart';
import 'package:wealthsphere_app/features/forecast/domain/forecast_models.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';

/// Records requests, can be slowed down or made to fail.
class RecordingForecasts implements ForecastRepository {
  RecordingForecasts(this._inner);

  final ForecastRepository _inner;
  final List<CompoundForecastRequest> requests = [];
  bool fail = false;
  Completer<void>? hold;

  @override
  Future<CompoundForecastRequest> defaultRequest() => _inner.defaultRequest();

  @override
  Future<CompoundForecastResponse> compound(
    CompoundForecastRequest request,
  ) async {
    requests.add(request);
    if (hold != null) await hold!.future;
    if (fail) throw const DataLoadException('down');
    return _inner.compound(request);
  }
}

Override recording(void Function(RecordingForecasts) use) =>
    forecastRepositoryProvider.overrideWith((ref) {
      final repo = RecordingForecasts(
        DemoForecastRepository(
          ref.watch(demoAssetsProvider),
          ref.read(demoBehaviorProvider.notifier).gate,
        ),
      );
      use(repo);
      return repo;
    });

Finder field(String name) => find.byKey(ValueKey('field-$name'));

Future<void> enter(WidgetTester tester, String name, String text) async {
  await tester.ensureVisible(field(name));
  await tester.enterText(field(name), text);
  await tester.pump();
}

Future<void> openAdvanced(WidgetTester tester) async {
  await tester.ensureVisible(find.text('Advanced options'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Advanced options'));
  await tester.pumpAndSettle();
}

Future<void> pumpCalculator(
  WidgetTester tester, {
  List<Override> extra = const [],
  Size size = const Size(400, 900),
  double textScale = 1.0,
  ThemeMode mode = ThemeMode.light,
  TextDirection dir = TextDirection.ltr,
}) => tester.pumpApp(
  const CalculatorScreen(),
  overrides: demoOverrides(extra: extra),
  surfaceSize: size,
  textScale: textScale,
  themeMode: mode,
  textDirection: dir,
);

/// The Forecast screen is on top (pushed routes are not reflected in the router's location).
bool onForecast() => find
    .descendant(of: find.byType(AppBar), matching: find.text('Wealth forecast'))
    .evaluate()
    .isNotEmpty;

String textOf(WidgetTester tester, String name) =>
    tester.widget<TextFormField>(field(name)).controller!.text;

void main() {
  group('defaults and layout', () {
    testWidgets('opens with the default inputs and the footnote', (
      tester,
    ) async {
      await pumpCalculator(tester);
      expect(textOf(tester, 'initialInvestment'), '10000');
      expect(textOf(tester, 'monthlyContribution'), '500');
      expect(textOf(tester, 'annualReturn'), '8');
      expect(textOf(tester, 'years'), '20');
      expect(find.text('Calculate'), findsOneWidget);
      expect(
        find.text('Projections are illustrative and not guaranteed.'),
        findsOneWidget,
      );
      expect(find.text('DEMO'), findsWidgets);
    });

    testWidgets('advanced options are collapsed, then show the assumptions', (
      tester,
    ) async {
      await pumpCalculator(tester);
      expect(find.text('Inflation (per year)'), findsNothing);
      await openAdvanced(tester);
      for (final label in [
        'Inflation (per year)',
        'Annual fee',
        'Compounding',
        'Contributions',
        'Your assumptions',
        'Conservative return',
        'Growth return',
      ]) {
        expect(find.text(label), findsOneWidget, reason: label);
      }
      expect(textOf(tester, 'conservativeReturn'), '5');
      expect(textOf(tester, 'growthReturn'), '12');
    });

    testWidgets(
      'the footnote stays visible when the keyboard is open (small phone)',
      (tester) async {
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        await pumpCalculator(tester, size: const Size(320, 568));
        tester.view.viewInsets = const FakeViewPadding(bottom: 280);
        await tester.pumpAndSettle();
        expect(
          find.text('Projections are illustrative and not guaranteed.'),
          findsOneWidget,
        );
        final footnote = tester.getRect(
          find.text('Projections are illustrative and not guaranteed.'),
        );
        expect(
          footnote.bottom,
          lessThanOrEqualTo(568 - 280 + 1),
          reason: 'sits above the keyboard',
        );
      },
    );

    testWidgets('a focused field is scrolled above the keyboard', (
      tester,
    ) async {
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await pumpCalculator(tester, size: const Size(320, 568));
      tester.view.viewInsets = const FakeViewPadding(bottom: 280);
      await tester.pumpAndSettle();
      await tester.ensureVisible(field('years'));
      await tester.tap(field('years'));
      await tester.pumpAndSettle();
      expect(
        tester.getRect(field('years')).bottom,
        lessThanOrEqualTo(568 - 280),
      );
    });
  });

  group('validation', () {
    testWidgets('an invalid value shows an inline message', (tester) async {
      await pumpCalculator(tester);
      await enter(tester, 'years', '75');
      expect(find.text('Must be at most 60.'), findsOneWidget);
      await enter(tester, 'years', '');
      expect(find.text('Enter a value.'), findsOneWidget);
      await enter(tester, 'initialInvestment', '12.345');
      // The typing filter stops a third decimal, so the stored value is valid.
      expect(textOf(tester, 'initialInvestment'), '12.34');
    });

    testWidgets('invalid input cannot be submitted', (tester) async {
      RecordingForecasts? repo;
      await pumpCalculator(tester, extra: [recording((r) => repo = r)]);
      await enter(tester, 'years', '');
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
      expect(repo?.requests ?? const [], isEmpty);
      expect(find.text('Enter a value.'), findsOneWidget);
      expect(
        find.text('Fix the highlighted fields to continue.'),
        findsOneWidget,
      );
    });

    testWidgets(
      'an invalid field inside the collapsed advanced section still blocks submit',
      (tester) async {
        RecordingForecasts? repo;
        await pumpCalculator(tester, extra: [recording((r) => repo = r)]);
        await openAdvanced(tester);
        await enter(tester, 'conservativeReturn', '9'); // above the base 8%
        await tester.tap(find.text('Advanced options'));
        await tester.pumpAndSettle();
        expect(
          find.text('Conservative return'),
          findsNothing,
          reason: 'collapsed again',
        );

        await tester.ensureVisible(find.text('Calculate'));
        await tester.tap(find.text('Calculate'));
        await tester.pumpAndSettle();
        expect(repo?.requests ?? const [], isEmpty);
        expect(
          find.text('Conservative return'),
          findsOneWidget,
          reason: 'the section opens to show the problem',
        );
        expect(
          find.text(
            "Conservative return can't be higher than the base return.",
          ),
          findsOneWidget,
        );
      },
    );

    testWidgets('an invalid field scrolled out of view still blocks submit', (
      tester,
    ) async {
      RecordingForecasts? repo;
      await pumpCalculator(
        tester,
        size: const Size(320, 480),
        extra: [recording((r) => repo = r)],
      );
      await enter(tester, 'initialInvestment', '');
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
      expect(repo?.requests ?? const [], isEmpty);
    });

    testWidgets(
      'negative return rates are accepted within limits and rejected beyond',
      (tester) async {
        await pumpCalculator(tester);
        await enter(tester, 'annualReturn', '-5');
        expect(find.text('Must be at least -20.'), findsNothing);
        expect(
          find.text('Negative returns are allowed to model losses.'),
          findsOneWidget,
        );
        await enter(tester, 'annualReturn', '-25');
        expect(find.text('Must be at least -20.'), findsOneWidget);
      },
    );

    testWidgets('typing letters and extra separators is filtered out', (
      tester,
    ) async {
      await pumpCalculator(tester);
      await enter(tester, 'monthlyContribution', '5a0,0.5');
      expect(textOf(tester, 'monthlyContribution'), '500.5');
    });

    testWidgets('conservative cannot exceed the base return', (tester) async {
      await pumpCalculator(tester);
      await openAdvanced(tester);
      await enter(tester, 'conservativeReturn', '9');
      expect(
        find.text("Conservative return can't be higher than the base return."),
        findsOneWidget,
      );
    });

    testWidgets('an empty optional field counts as zero and can be submitted', (
      tester,
    ) async {
      late RecordingForecasts repo;
      await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.calculator,
        overrides: demoOverrides(extra: [recording((r) => repo = r)]),
        surfaceSize: const Size(400, 1000),
      );
      await enter(tester, 'contributionGrowth', '');
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
      expect(repo.requests, hasLength(1));
      expect(repo.requests.single.contributionGrowthPercent, Decimal.zero);
      expect(onForecast(), isTrue, reason: 'Forecast screen pushed');
    });
  });

  group('calculate', () {
    testWidgets('sends the request as strings and opens the Forecast screen', (
      tester,
    ) async {
      late RecordingForecasts repo;
      await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.calculator,
        overrides: demoOverrides(extra: [recording((r) => repo = r)]),
        surfaceSize: const Size(400, 1000),
      );
      await enter(tester, 'initialInvestment', '25000.50');
      await enter(tester, 'years', '15');
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();

      final json = repo.requests.single.toJson();
      expect(json['initial_investment'], {
        'amount': '25000.5',
        'currency': 'USD',
      });
      expect(json['monthly_contribution'], {
        'amount': '500',
        'currency': 'USD',
      });
      expect(json['years'], 15);
      expect(json['annual_return_percent'], '8');
      expect(json['compounding_frequency'], 'monthly');
      expect(onForecast(), isTrue, reason: 'Forecast screen pushed');
      final container = ProviderScope.containerOf(
        tester.element(find.byType(Scaffold).first),
      );
      expect(
        container.read(forecastResultProvider)!.request,
        repo.requests.single,
      );
    });

    testWidgets('frequency choices are sent', (tester) async {
      late RecordingForecasts repo;
      await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.calculator,
        overrides: demoOverrides(extra: [recording((r) => repo = r)]),
        surfaceSize: const Size(400, 1400),
      );
      await tester.tap(find.text('Advanced options'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Quarterly').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Yearly').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
      final json = repo.requests.single.toJson();
      expect(json['compounding_frequency'], 'quarterly');
      expect(json['contribution_frequency'], 'yearly');
    });

    testWidgets(
      'shows a loading state on the button and prevents a double submit',
      (tester) async {
        late RecordingForecasts repo;
        await pumpRouterApp(
          tester,
          initialLocation: AppRoutes.calculator,
          overrides: demoOverrides(
            extra: [recording((r) => repo = r..hold = Completer<void>())],
          ),
          surfaceSize: const Size(400, 1000),
        );
        await tester.ensureVisible(find.text('Calculate'));
        await tester.tap(find.text('Calculate'));
        await tester.pump();
        expect(find.text('Calculating…'), findsOneWidget);
        expect(find.byType(CircularProgressIndicator), findsOneWidget);
        expect(
          tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
          isNull,
        );
        expect(repo.requests, hasLength(1));
        repo.hold!.complete();
        await tester.pumpAndSettle();
      },
    );

    testWidgets('a failure shows a message and the button retries', (
      tester,
    ) async {
      late RecordingForecasts repo;
      final router = await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.calculator,
        overrides: demoOverrides(
          extra: [recording((r) => repo = r..fail = true)],
        ),
        surfaceSize: const Size(400, 1000),
      );
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
      expect(find.textContaining("couldn't calculate"), findsOneWidget);
      expect(
        router.routerDelegate.currentConfiguration.uri.path,
        AppRoutes.calculator,
      );
      expect(find.text('Try again'), findsOneWidget);

      repo.fail = false;
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(repo.requests, hasLength(2));
      expect(onForecast(), isTrue, reason: 'Forecast screen pushed');
    });

    testWidgets('inputs survive navigating to the Forecast screen and back', (
      tester,
    ) async {
      final router = await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.calculator,
        surfaceSize: const Size(400, 1000),
      );
      await enter(tester, 'initialInvestment', '33333');
      await tester.tap(find.text('Advanced options'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Yearly').first);
      await tester.pumpAndSettle();
      await enter(tester, 'growthReturn', '14');
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
      expect(onForecast(), isTrue, reason: 'Forecast screen pushed');

      router.pop();
      await tester.pumpAndSettle();
      expect(textOf(tester, 'initialInvestment'), '33333');
      // The advanced section is still open, as the user left it.
      expect(textOf(tester, 'growthReturn'), '14');
      final selected = tester
          .widget<SegmentedButton<Frequency>>(
            find.byType(SegmentedButton<Frequency>).first,
          )
          .selected;
      expect(selected, {Frequency.yearly});
    });
  });

  group('accessibility and layout', () {
    testWidgets('every field has a label and the button is a 48dp target', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpCalculator(tester);
      for (final label in [
        'Initial investment',
        'Monthly contribution',
        'Expected annual return (base)',
        'Investment period (years)',
      ]) {
        expect(
          find.bySemanticsLabel(RegExp(RegExp.escape(label))),
          findsWidgets,
          reason: label,
        );
      }
      expect(
        tester.getSize(find.byType(FilledButton)).height,
        greaterThanOrEqualTo(48),
      );
      handle.dispose();
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
        for (final scale in [1.0, 2.0]) {
          testWidgets(
            '320 wide, ${mode.name}, ${dir.name}, ${scale}x: no overflow, with advanced open and errors',
            (tester) async {
              await pumpCalculator(
                tester,
                size: const Size(320, 568),
                mode: mode,
                dir: dir,
                textScale: scale,
              );
              await openAdvanced(tester);
              await enter(tester, 'years', '99');
              await enter(tester, 'conservativeReturn', '30');
              expect(tester.takeException(), isNull);
              await tester.ensureVisible(find.text('Calculate'));
              await tester.tap(find.text('Calculate'));
              await tester.pumpAndSettle();
              expect(tester.takeException(), isNull);
            },
          );
        }
      }
    }
  });
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/portfolios/application/portfolio_providers.dart';
import 'package:wealthsphere_app/features/portfolios/data/portfolio_repository.dart';
import 'package:wealthsphere_app/features/portfolios/presentation/portfolio_overview_screen.dart';
import 'package:wealthsphere_app/shared/design_system/charts/charts.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';

/// The real demo repository with a few switches to simulate empty and failing sections.
class TweakedPortfolios implements PortfolioRepository {
  TweakedPortfolios(this._inner);

  final PortfolioRepository _inner;
  bool emptyHoldings = false;
  bool metricsFail = false;
  final List<String> summaryRequests = [];
  int metricsRequests = 0;
  int holdingsRequests = 0;
  int allocationRequests = 0;
  int seriesRequests = 0;

  @override
  Future<List<PortfolioRef>> portfolios() => _inner.portfolios();

  @override
  Future<PortfolioSummary> summary(String id) {
    summaryRequests.add(id);
    return _inner.summary(id);
  }

  @override
  Future<PerformanceSeries> performance(String id, ChartPeriod p) {
    seriesRequests++;
    return _inner.performance(id, p);
  }

  @override
  Future<List<AllocationShare>> allocation(String id) async {
    allocationRequests++;
    return emptyHoldings ? const [] : _inner.allocation(id);
  }

  @override
  Future<PerformanceMetrics> metrics(String id) async {
    metricsRequests++;
    if (metricsFail) throw const DataLoadException('metrics down');
    return _inner.metrics(id);
  }

  @override
  Future<List<HoldingSummary>> holdings(String id) async {
    holdingsRequests++;
    return emptyHoldings ? const [] : _inner.holdings(id);
  }
}

const tall = Size(400, 3600);

Override tweaked(void Function(TweakedPortfolios) configure) =>
    portfolioRepositoryProvider.overrideWith((ref) {
      final repo = TweakedPortfolios(
        DemoPortfolioRepository(
          ref.watch(demoAssetsProvider),
          ref.read(demoBehaviorProvider.notifier).gate,
        ),
      );
      configure(repo);
      return repo;
    });

Future<void> pumpOverview(
  WidgetTester tester, {
  List<Override> extra = const [],
  Size size = tall,
  double textScale = 1.0,
  ThemeMode mode = ThemeMode.light,
  TextDirection dir = TextDirection.ltr,
  DemoBehavior behavior = DemoBehavior.instant,
}) => tester.pumpApp(
  const PortfolioOverviewScreen(),
  overrides: demoOverrides(behavior: behavior, extra: extra),
  surfaceSize: size,
  textScale: textScale,
  themeMode: mode,
  textDirection: dir,
);

Future<void> choose(WidgetTester tester, String current, String target) async {
  await tester.tap(
    find.descendant(of: find.byType(AppBar), matching: find.text(current)),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text(target));
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('consolidated view (default)', () {
    testWidgets(
      'shows value, P/L, chart, allocation, metrics and top holdings',
      (tester) async {
        await pumpOverview(tester);
        expect(
          find.descendant(
            of: find.byType(AppBar),
            matching: find.text('All portfolios (consolidated)'),
          ),
          findsOneWidget,
        );
        expect(find.text(r'$139,986.35'), findsWidgets);
        expect(find.textContaining('17,286.35'), findsOneWidget);
        expect(find.byType(PerformanceLineChart), findsOneWidget);
        expect(find.byType(AllocationDonutChart), findsOneWidget);
        expect(find.text('Total'), findsOneWidget, reason: 'donut centre');
        for (final label in [
          'Total return',
          'Annualised return (CAGR)',
          'Dividend yield',
          'Volatility',
        ]) {
          expect(find.text(label), findsOneWidget, reason: label);
        }
        expect(find.text('14.09%'), findsOneWidget);
        expect(find.text('10.10%'), findsOneWidget);
        expect(find.text('Top holdings'), findsOneWidget);
        expect(
          find.byType(InvestmentRow),
          findsNWidgets(5),
          reason: 'preview is limited to five',
        );
        expect(find.text('View all holdings'), findsOneWidget);
      },
    );

    testWidgets('native-currency holdings show their own value too', (
      tester,
    ) async {
      await pumpOverview(tester, extra: [tweaked((_) {})]);
      await choose(tester, 'All portfolios (consolidated)', 'Retirement');
      expect(find.text('DEMO-EMR'), findsOneWidget);
      expect(find.textContaining('AED'), findsWidgets);
    });

    testWidgets('each metric has a definition tooltip', (tester) async {
      await pumpOverview(tester);
      expect(find.byIcon(Icons.info_outline_rounded), findsNWidgets(4));
      await tester.tap(find.byIcon(Icons.info_outline_rounded).first);
      await tester.pump();
      expect(find.textContaining('gained or lost overall'), findsOneWidget);
    });
  });

  group('switching portfolios refreshes every section', () {
    testWidgets('Growth portfolio', (tester) async {
      await pumpOverview(tester);
      await choose(tester, 'All portfolios (consolidated)', 'Growth');
      expect(find.text(r'$31,940.15'), findsWidgets);
      expect(find.text(r'$139,986.35'), findsNothing);
      expect(
        find.text('17.80%'),
        findsOneWidget,
        reason: 'volatility of the growth portfolio',
      );
      expect(find.text('DEMO-TEC'), findsOneWidget);
      expect(find.text('DEMO-GEQ'), findsNothing);
      expect(find.byType(InvestmentRow), findsNWidgets(3));
      final donut = tester.widget<AllocationDonutChart>(
        find.byType(AllocationDonutChart),
      );
      expect(donut.slices.map((s) => s.label), contains('Alternatives'));
    });

    testWidgets('every portfolio loads, and the consolidated view returns', (
      tester,
    ) async {
      await pumpOverview(tester);
      for (final (from, to, value) in [
        ('All portfolios (consolidated)', 'Retirement', r'$90,250.40'),
        ('Retirement', 'Income', r'$17,795.80'),
        ('Income', 'All portfolios (consolidated)', r'$139,986.35'),
      ]) {
        await choose(tester, from, to);
        expect(find.text(value), findsWidgets, reason: to);
        expect(tester.takeException(), isNull, reason: to);
      }
    });

    testWidgets('the selection is shared through a provider', (tester) async {
      await pumpOverview(tester);
      await choose(tester, 'All portfolios (consolidated)', 'Income');
      final container = ProviderScope.containerOf(
        tester.element(find.byType(PortfolioOverviewScreen)),
      );
      expect(container.read(selectedPortfolioIdProvider), 'p-income');
    });

    testWidgets('period change swaps the series for the selected portfolio', (
      tester,
    ) async {
      await pumpOverview(tester);
      int points() => tester
          .widget<PerformanceLineChart>(find.byType(PerformanceLineChart))
          .series
          .points
          .length;
      expect(points(), 13, reason: 'default 1Y');
      await tester.tap(find.text('3M'));
      await tester.pumpAndSettle();
      expect(points(), 14);
      await tester.tap(find.text('ALL'));
      await tester.pumpAndSettle();
      expect(points(), 17);
    });
  });

  group('states', () {
    testWidgets(
      'an empty portfolio shows the empty state with a disabled add button',
      (tester) async {
        await pumpOverview(
          tester,
          extra: [tweaked((r) => r.emptyHoldings = true)],
        );
        expect(find.text('No investments yet'), findsOneWidget);
        expect(find.byType(AllocationDonutChart), findsNothing);
        expect(find.byType(InvestmentRow), findsNothing);
        final add = tester.widget<FilledButton>(find.byType(FilledButton));
        expect(
          add.onPressed,
          isNull,
          reason: 'adding is not available in demo mode',
        );
        expect(find.text('Add investment'), findsOneWidget);
        expect(find.text('Ask AI about this portfolio'), findsOneWidget);
      },
    );

    testWidgets('a failing metrics section is isolated and retries', (
      tester,
    ) async {
      late TweakedPortfolios repo;
      await pumpOverview(
        tester,
        extra: [tweaked((r) => repo = r..metricsFail = true)],
      );
      expect(find.byType(ErrorState), findsOneWidget);
      expect(find.text('Total return'), findsNothing);
      expect(find.text(r'$139,986.35'), findsWidgets);
      expect(find.text('Top holdings'), findsOneWidget);

      repo.metricsFail = false;
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.byType(ErrorState), findsNothing);
      expect(find.text('Total return'), findsOneWidget);
    });

    testWidgets('every section failing leaves retries and the header', (
      tester,
    ) async {
      await pumpOverview(
        tester,
        behavior: DemoBehavior.instant.copyWith(failAlways: true),
      );
      expect(find.byType(ErrorState), findsWidgets);
      expect(find.byType(AppBar), findsOneWidget);
    });

    testWidgets('sections show skeletons while loading', (tester) async {
      await tester.pumpApp(
        const PortfolioOverviewScreen(),
        overrides: demoOverrides(
          behavior: const DemoBehavior(latency: Duration(milliseconds: 500)),
        ),
        surfaceSize: tall,
        settle: false,
      );
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byType(SkeletonLoader), findsWidgets);
      await tester.pumpAndSettle(const Duration(seconds: 3));
      expect(find.byType(SkeletonLoader), findsNothing);
    });

    testWidgets('pull to refresh reloads every section', (tester) async {
      late TweakedPortfolios repo;
      await pumpOverview(tester, extra: [tweaked((r) => repo = r)]);
      List<int> counts() => [
        repo.summaryRequests.length,
        repo.seriesRequests,
        repo.allocationRequests,
        repo.metricsRequests,
        repo.holdingsRequests,
      ];
      final before = counts();
      unawaited(
        tester
            .state<RefreshIndicatorState>(find.byType(RefreshIndicator))
            .show(),
      );
      await tester.pumpAndSettle();
      final after = counts();
      for (var i = 0; i < before.length; i++) {
        expect(after[i], greaterThan(before[i]), reason: 'section $i reloaded');
      }
    });
  });

  group('navigation', () {
    testWidgets('View all holdings opens the holdings screen', (tester) async {
      final router = await pumpRouterApp(
        tester,
        overrides: demoOverrides(),
        surfaceSize: tall,
      );
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Portfolio'),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('View all holdings'));
      await tester.tap(find.text('View all holdings'));
      await tester.pumpAndSettle();
      expect(
        router.routerDelegate.currentConfiguration.uri.path,
        AppRoutes.holdings,
      );
    });

    testWidgets('Ask AI carries the selected portfolio as the scope', (
      tester,
    ) async {
      final router = await pumpRouterApp(
        tester,
        overrides: demoOverrides(),
        surfaceSize: tall,
      );
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Portfolio'),
        ),
      );
      await tester.pumpAndSettle();
      await choose(tester, 'All portfolios (consolidated)', 'Growth');
      await tester.ensureVisible(find.text('Ask AI about this portfolio'));
      await tester.tap(find.text('Ask AI about this portfolio'));
      await tester.pumpAndSettle();
      final uri = router.routerDelegate.currentConfiguration.uri;
      expect(uri.path, AppRoutes.ai);
      expect(uri.queryParameters['scope'], 'portfolio:p-growth');
    });

    testWidgets('the consolidated view is a valid AI scope too', (
      tester,
    ) async {
      final router = await pumpRouterApp(
        tester,
        overrides: demoOverrides(),
        surfaceSize: tall,
      );
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('Portfolio'),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Ask AI about this portfolio'));
      await tester.tap(find.text('Ask AI about this portfolio'));
      await tester.pumpAndSettle();
      expect(
        AiScope.tryParse(
          router
              .routerDelegate
              .currentConfiguration
              .uri
              .queryParameters['scope'],
        ),
        isNotNull,
      );
    });
  });

  group('accessibility and layout', () {
    testWidgets('the switcher is announced with the current portfolio', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpOverview(tester);
      expect(
        find.bySemanticsLabel(RegExp('Portfolio: All portfolios')),
        findsOneWidget,
      );
      handle.dispose();
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
        for (final scale in [1.0, 2.0]) {
          testWidgets(
            '320 wide, ${mode.name}, ${dir.name}, ${scale}x: no overflow',
            (tester) async {
              await pumpOverview(
                tester,
                size: const Size(320, 5200),
                mode: mode,
                dir: dir,
                textScale: scale,
              );
              expect(tester.takeException(), isNull);
              await choose(tester, 'All portfolios (consolidated)', 'Growth');
              expect(tester.takeException(), isNull);
            },
          );
        }
      }
    }
  });
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/features/dashboard/data/dashboard_repository.dart';
import 'package:wealthsphere_app/features/dashboard/domain/dashboard_layout.dart';
import 'package:wealthsphere_app/features/dashboard/presentation/home_screen.dart';
import 'package:wealthsphere_app/shared/design_system/charts/charts.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';

/// Wraps the real demo repository so a test can break one section and count calls.
class _FlakyDashboard implements DashboardRepository {
  _FlakyDashboard(this._inner);

  final DashboardRepository _inner;
  bool incomeFails = true;
  int calls = 0;
  int netWorthCalls = 0;
  int incomeCalls = 0;
  int goalsCalls = 0;
  int insightCalls = 0;

  @override
  Future<String> greetingName() {
    calls++;
    return _inner.greetingName();
  }

  @override
  Future<NetWorthSummary> netWorth() {
    netWorthCalls++;
    return _inner.netWorth();
  }

  @override
  Future<IncomeSummary> income() async {
    incomeCalls++;
    if (incomeFails) throw const DataLoadException('income down');
    return _inner.income();
  }

  @override
  Future<GoalsSummary> goals() {
    goalsCalls++;
    return _inner.goals();
  }

  @override
  Future<InsightSummary> insight() {
    insightCalls++;
    return _inner.insight();
  }
}

const tall = Size(400, 2600);

Future<void> pumpHome(
  WidgetTester tester, {
  InMemoryPreferencesStore? store,
  List<Override> extra = const [],
  Size size = tall,
  double textScale = 1.0,
  ThemeMode mode = ThemeMode.light,
  TextDirection dir = TextDirection.ltr,
  DemoBehavior behavior = DemoBehavior.instant,
}) => tester.pumpApp(
  const HomeScreen(),
  overrides: demoOverrides(store: store, extra: extra, behavior: behavior),
  surfaceSize: size,
  textScale: textScale,
  themeMode: mode,
  textDirection: dir,
);

double top(WidgetTester tester, Finder f) => tester.getTopLeft(f).dy;

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('content', () {
    testWidgets('renders every section from the fixtures', (tester) async {
      await pumpHome(tester);
      expect(find.text('Hello, Alex'), findsOneWidget);
      expect(find.text('DEMO'), findsWidgets);
      expect(find.text('Total wealth'), findsOneWidget);
      expect(find.text(r'$139,986.35'), findsWidgets);
      expect(find.byType(PerformanceLineChart), findsOneWidget);
      for (final label in [
        'Portfolio value',
        'Net worth',
        'Monthly income',
        'Goals',
      ]) {
        expect(find.text(label), findsWidgets, reason: label);
      }
      expect(find.text('3 on track'), findsOneWidget);
      expect(find.text('AI insight'), findsOneWidget);
      expect(find.textContaining('up 14.09%'), findsOneWidget);
      expect(find.byType(EvidenceSourceChip), findsNWidgets(2));
      expect(find.text('Ask Wealth AI'), findsOneWidget);
      expect(find.text('Home deposit'), findsOneWidget);
      expect(find.byType(DataAsOfLabel), findsWidgets);
    });

    testWidgets(
      'return is shown with an arrow, sign and the backend P/L amount',
      (tester) async {
        await pumpHome(tester);
        expect(find.byIcon(Icons.arrow_upward_rounded), findsWidgets);
        expect(find.textContaining('14.09%'), findsWidgets);
        expect(find.textContaining('17,286.35'), findsOneWidget);
      },
    );

    testWidgets('the notifications icon is present but inert', (tester) async {
      await pumpHome(tester);
      final button = tester.widget<IconButton>(
        find.widgetWithIcon(IconButton, Icons.notifications_none_rounded),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('sections show skeletons while loading', (tester) async {
      await tester.pumpApp(
        const HomeScreen(),
        overrides: demoOverrides(
          behavior: const DemoBehavior(latency: Duration(milliseconds: 500)),
        ),
        surfaceSize: tall,
        settle: false,
      );
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byType(SkeletonLoader), findsWidgets);
      await tester.pumpAndSettle(const Duration(seconds: 2));
      expect(find.byType(SkeletonLoader), findsNothing);
    });
  });

  group('period selection', () {
    testWidgets('changing the period swaps the chart series', (tester) async {
      await pumpHome(tester);
      int points() => tester
          .widget<PerformanceLineChart>(find.byType(PerformanceLineChart))
          .series
          .points
          .length;
      final month = points();
      await tester.tap(find.text('1Y'));
      await tester.pumpAndSettle();
      expect(points(), isNot(month));
      expect(points(), 13, reason: 'the year fixture has 13 points');
      await tester.tap(find.text('1W'));
      await tester.pumpAndSettle();
      expect(points(), 8);
    });
  });

  group('personalisation', () {
    Future<void> openCustomise(WidgetTester tester) async {
      await tester.tap(find.byTooltip('Customise'));
      await tester.pumpAndSettle();
    }

    testWidgets(
      'customise mode lists every section with move buttons and switches',
      (tester) async {
        await pumpHome(tester);
        await openCustomise(tester);
        expect(find.text('Customise home'), findsOneWidget);
        expect(find.byType(Switch), findsNWidgets(4));
        expect(find.byTooltip('Move up'), findsNWidgets(4));
        expect(
          tester
              .widget<IconButton>(
                find
                    .widgetWithIcon(IconButton, Icons.arrow_upward_rounded)
                    .first,
              )
              .onPressed,
          isNull,
        );
        expect(find.byTooltip('Done'), findsOneWidget);
      },
    );

    testWidgets('reorder and hide persist across a restart', (tester) async {
      final store = InMemoryPreferencesStore();
      await pumpHome(tester, store: store);
      expect(
        top(tester, find.text('Total wealth')),
        lessThan(top(tester, find.text('Portfolio value').first)),
      );

      await openCustomise(tester);
      await tester.tap(
        find.byIcon(Icons.arrow_downward_rounded).first,
      ); // wealth summary down
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Switch).at(3)); // hide goals
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Done'));
      await tester.pumpAndSettle();
      expect(
        top(tester, find.text('Portfolio value').first),
        lessThan(top(tester, find.text('Total wealth'))),
      );
      expect(find.text('Home deposit'), findsNothing);

      // "Restart": a brand new widget tree and provider scope on the same store.
      await tester.pumpWidget(const SizedBox());
      await pumpHome(tester, store: store);
      expect(
        top(tester, find.text('Portfolio value').first),
        lessThan(top(tester, find.text('Total wealth'))),
      );
      expect(find.text('Home deposit'), findsNothing);
      expect(find.text('Net worth'), findsOneWidget);
    });

    testWidgets('Move up undoes Move down', (tester) async {
      await pumpHome(tester);
      await openCustomise(tester);
      await tester.tap(find.byIcon(Icons.arrow_downward_rounded).first);
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded).at(1));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Done'));
      await tester.pumpAndSettle();
      expect(
        top(tester, find.text('Total wealth')),
        lessThan(top(tester, find.text('Portfolio value').first)),
      );
    });

    testWidgets('a hidden section can be shown again', (tester) async {
      await pumpHome(tester);
      await openCustomise(tester);
      await tester.tap(find.byType(Switch).at(2)); // hide insight
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Switch).at(2));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Done'));
      await tester.pumpAndSettle();
      expect(find.text('AI insight'), findsOneWidget);
    });

    testWidgets(
      'screen-reader users can reorder without dragging (custom actions)',
      (tester) async {
        final handle = tester.ensureSemantics();
        final store = InMemoryPreferencesStore();
        await pumpHome(tester, store: store);
        await openCustomise(tester);

        final node = tester.getSemantics(
          find.bySemanticsLabel(RegExp('Wealth summary, position 1 of 4')),
        );
        final actions = node
            .getSemanticsData()
            .customSemanticsActionIds!
            .map(CustomSemanticsAction.getAction)
            .map((a) => a!.label)
            .toList();
        expect(actions, [
          'Move down',
        ], reason: 'the first section can only move down');

        final id = node.getSemanticsData().customSemanticsActionIds!.single;
        tester.semantics.performAction(
          find.semantics.byLabel(RegExp('Wealth summary, position 1 of 4')),
          SemanticsAction.customAction,
          args: id,
        );
        await tester.pumpAndSettle();
        expect(
          find.bySemanticsLabel(RegExp('Wealth summary, position 2 of 4')),
          findsOneWidget,
        );
        expect(
          DashboardLayout.fromJsonString(
            store.values[LocalDashboardLayoutRepository.key],
          ).order[1],
          DashboardSection.wealthSummary,
        );
        handle.dispose();
      },
    );
  });

  group('failures stay inside their own section', () {
    testWidgets(
      'one failing card does not blank the page, and its retry works',
      (tester) async {
        late _FlakyDashboard flaky;
        await pumpHome(
          tester,
          extra: [
            dashboardRepositoryProvider.overrideWith((ref) {
              flaky = _FlakyDashboard(
                DemoDashboardRepository(
                  ref.watch(demoAssetsProvider),
                  ref.read(demoBehaviorProvider.notifier).gate,
                ),
              );
              return flaky;
            }),
          ],
        );
        expect(find.text("This section couldn't be loaded."), findsOneWidget);
        expect(find.text('Net worth'), findsOneWidget);
        expect(find.text('Total wealth'), findsOneWidget);
        expect(find.text('Home deposit'), findsOneWidget);
        expect(
          find.text('Monthly income'),
          findsNothing,
          reason: 'the failed tile shows the error instead',
        );

        flaky.incomeFails = false;
        await tester.tap(find.text('Try again'));
        await tester.pumpAndSettle();
        expect(find.text("This section couldn't be loaded."), findsNothing);
        expect(find.text('Monthly income'), findsOneWidget);
      },
    );

    testWidgets(
      'when every section fails the page still shows retries, not a blank screen',
      (tester) async {
        await pumpHome(
          tester,
          behavior: DemoBehavior.instant.copyWith(failAlways: true),
        );
        expect(find.byType(ErrorState), findsWidgets);
        expect(find.text('Try again'), findsWidgets);
        expect(find.byType(AppBar), findsOneWidget);
      },
    );
  });

  group('refresh', () {
    testWidgets('pulling down reloads the sections', (tester) async {
      late _FlakyDashboard flaky;
      await pumpHome(
        tester,
        extra: [
          dashboardRepositoryProvider.overrideWith((ref) {
            flaky = _FlakyDashboard(
              DemoDashboardRepository(
                ref.watch(demoAssetsProvider),
                ref.read(demoBehaviorProvider.notifier).gate,
              ),
            )..incomeFails = false;
            return flaky;
          }),
        ],
      );
      final before = [
        flaky.calls,
        flaky.netWorthCalls,
        flaky.incomeCalls,
        flaky.goalsCalls,
        flaky.insightCalls,
      ];
      // The same call the pull-to-refresh gesture makes.
      unawaited(
        tester
            .state<RefreshIndicatorState>(find.byType(RefreshIndicator))
            .show(),
      );
      await tester.pumpAndSettle();
      final after = [
        flaky.calls,
        flaky.netWorthCalls,
        flaky.incomeCalls,
        flaky.goalsCalls,
        flaky.insightCalls,
      ];
      for (var i = 0; i < before.length; i++) {
        expect(after[i], greaterThan(before[i]), reason: 'section $i reloaded');
      }
    });
  });

  group('navigation', () {
    testWidgets(
      'Ask Wealth AI opens the AI tab, and the goals card opens Goals',
      (tester) async {
        final router = await pumpRouterApp(
          tester,
          overrides: demoOverrides(),
          surfaceSize: tall,
        );
        await tester.ensureVisible(find.text('Ask Wealth AI'));
        await tester.tap(find.text('Ask Wealth AI'));
        await tester.pumpAndSettle();
        expect(
          router.routerDelegate.currentConfiguration.uri.path,
          AppRoutes.ai,
        );

        await tester.tap(
          find.descendant(
            of: find.byType(NavigationBar),
            matching: find.text('Home'),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('3 on track'));
        await tester.pumpAndSettle();
        expect(
          router.routerDelegate.currentConfiguration.uri.path,
          AppRoutes.goals,
        );
      },
    );

    testWidgets('the portfolio value card opens Portfolio', (tester) async {
      final router = await pumpRouterApp(
        tester,
        overrides: demoOverrides(),
        surfaceSize: tall,
      );
      await tester.tap(find.text('Portfolio value'));
      await tester.pumpAndSettle();
      expect(
        router.routerDelegate.currentConfiguration.uri.path,
        AppRoutes.portfolio,
      );
    });
  });

  group('accessibility and layout', () {
    testWidgets(
      'amounts are spoken as phrases, and goals are announced with status',
      (tester) async {
        final handle = tester.ensureSemantics();
        await pumpHome(tester);
        expect(find.bySemanticsLabel(RegExp('139,986.35 USD')), findsWidgets);
        expect(
          find.bySemanticsLabel(RegExp('Home deposit: .* complete, on track')),
          findsOneWidget,
        );
        expect(
          find.bySemanticsLabel(RegExp('Family travel: .* complete, behind')),
          findsOneWidget,
        );
        handle.dispose();
      },
    );

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
        for (final scale in [1.0, 2.0]) {
          testWidgets(
            '320 wide, ${mode.name}, ${dir.name}, ${scale}x: no overflow',
            (tester) async {
              await pumpHome(
                tester,
                size: const Size(320, 3600),
                mode: mode,
                dir: dir,
                textScale: scale,
              );
              expect(tester.takeException(), isNull);
              await tester.tap(find.byTooltip('Customise'));
              await tester.pumpAndSettle();
              expect(tester.takeException(), isNull);
            },
          );
        }
      }
    }
  });
}

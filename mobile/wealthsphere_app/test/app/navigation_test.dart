import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:wealthsphere_app/app/app_routes.dart';

import '../helpers/pump_router.dart';

Future<void> tapTab(WidgetTester tester, String label) async {
  await tester.tap(
    find.descendant(of: find.byType(NavigationBar), matching: find.text(label)),
  );
  await tester.pumpAndSettle();
}

Finder get appBarTitle =>
    find.descendant(of: find.byType(AppBar), matching: find.byType(Text));

bool onScreen(String title) =>
    appBarTitle.evaluate().any((e) => (e.widget as Text).data == title);

void main() {
  group('start and redirects', () {
    testWidgets('opens on Home with the five labelled tabs', (tester) async {
      final router = await pumpRouterApp(tester);
      expect(currentPath(router), AppRoutes.home);
      for (final label in ['Home', 'Portfolio', 'AI Wealth', 'Goals', 'More']) {
        expect(
          find.descendant(
            of: find.byType(NavigationBar),
            matching: find.text(label),
          ),
          findsOneWidget,
        );
      }
    });

    testWidgets('the bare host redirects to Home', (tester) async {
      final router = await pumpRouterApp(tester, initialLocation: '/');
      expect(currentPath(router), AppRoutes.home);
    });

    testWidgets('an unknown path shows a not-found screen with a way home', (
      tester,
    ) async {
      final router = await pumpRouterApp(
        tester,
        initialLocation: '/definitely/not/a/page',
      );
      expect(find.text('Page not found'), findsWidgets);
      await tester.tap(find.text('Go to Home'));
      await tester.pumpAndSettle();
      expect(currentPath(router), AppRoutes.home);
      expect(find.byType(NavigationBar), findsOneWidget);
    });

    testWidgets('deep links open the right tab', (tester) async {
      final router = await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.holdings,
      );
      expect(currentPath(router), AppRoutes.holdings);
      expect(find.text('Holdings'), findsWidgets);
      expect(
        tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex,
        1,
      );
    });
  });

  group('tab switching keeps each tab\'s own stack', () {
    testWidgets('a pushed screen survives a trip to another tab', (
      tester,
    ) async {
      await pumpRouterApp(tester);
      await tapTab(tester, 'Portfolio');
      await tester.tap(find.text('Holdings'));
      await tester.pumpAndSettle();
      expect(find.byType(BackButton), findsOneWidget);

      await tapTab(tester, 'Home');
      expect(find.text('Total wealth'), findsOneWidget);

      await tapTab(tester, 'Portfolio');
      // Still on Holdings (the nested screen), not back at the Portfolio root.
      expect(find.byType(BackButton), findsOneWidget);
      expect(
        appBarTitle.evaluate().any(
          (e) => (e.widget as Text).data == 'Holdings',
        ),
        isTrue,
      );
    });

    testWidgets(
      'each of the five tabs can be reached and shows its own screen',
      (tester) async {
        final router = await pumpRouterApp(tester);
        final expected = {
          'Portfolio': AppRoutes.portfolio,
          'AI Wealth': AppRoutes.ai,
          'Goals': AppRoutes.goals,
          'More': AppRoutes.more,
          'Home': AppRoutes.home,
        }; // fmt: skip
        for (final e in expected.entries) {
          await tapTab(tester, e.key);
          expect(currentPath(router), e.value, reason: e.key);
        }
      },
    );

    testWidgets('the selected tab is marked selected', (tester) async {
      await pumpRouterApp(tester);
      for (final entry in {'Goals': 3, 'AI Wealth': 2, 'Home': 0}.entries) {
        await tapTab(tester, entry.key);
        expect(
          tester
              .widget<NavigationBar>(find.byType(NavigationBar))
              .selectedIndex,
          entry.value,
        );
      }
    });
  });

  group('back behaviour', () {
    testWidgets(
      'Android back pops a nested screen, then leaves the app from a tab root',
      (tester) async {
        final exits = SystemBackRecorder(tester);
        final router = await pumpRouterApp(tester);
        await tapTab(tester, 'More');
        await tester.tap(find.text('Compounding calculator'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Wealth forecast'));
        await tester.pumpAndSettle();
        expect(onScreen('Wealth forecast'), isTrue);

        await tester.binding.handlePopRoute();
        await tester.pumpAndSettle();
        expect(onScreen('Compounding calculator'), isTrue);
        await tester.binding.handlePopRoute();
        await tester.pumpAndSettle();
        expect(find.byType(BackButton), findsNothing);
        expect(currentPath(router), AppRoutes.more);
        expect(
          exits.exits,
          0,
          reason: 'nested screens are popped, the app stays open',
        );

        await tester.binding.handlePopRoute();
        await tester.pumpAndSettle();
        expect(exits.exits, 1, reason: 'back at a tab root leaves the app');
      },
    );

    testWidgets('the on-screen back button returns to the tab root', (
      tester,
    ) async {
      final router = await pumpRouterApp(tester);
      await tapTab(tester, 'Portfolio');
      await tester.tap(find.text('Holdings'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(currentPath(router), AppRoutes.portfolio);
    });

    testWidgets('re-tapping the active tab returns it to its root', (
      tester,
    ) async {
      final router = await pumpRouterApp(tester);
      await tapTab(tester, 'More');
      await tester.tap(find.text('Compounding calculator'));
      await tester.pumpAndSettle();
      expect(onScreen('Compounding calculator'), isTrue);

      await tapTab(tester, 'More');
      expect(currentPath(router), AppRoutes.more);
      expect(find.byType(BackButton), findsNothing);
    });

    testWidgets(
      're-tapping a tab that is already at its root changes nothing',
      (tester) async {
        final router = await pumpRouterApp(tester);
        await tapTab(tester, 'Home');
        expect(currentPath(router), AppRoutes.home);
      },
    );
  });

  group('contextual AI entry', () {
    testWidgets('a valid scope is shown as the conversation context', (
      tester,
    ) async {
      final router = await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.aiWith(
          const AiScope(AiScopeKind.portfolio, 'p-1'),
        ),
      );
      expect(find.text('Context: portfolio:p-1'), findsOneWidget);
      expect(
        tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex,
        2,
      );
      expect(router.state.uri.path, AppRoutes.ai);
    });

    testWidgets('an invalid or hostile scope is ignored, not displayed', (
      tester,
    ) async {
      for (final raw in [
        'portfolio:../../x',
        'bogus',
        'goal:<script>alert(1)</script>',
      ]) {
        await pumpRouterApp(
          tester,
          initialLocation: Uri(
            path: '/ai',
            queryParameters: {'scope': raw},
          ).toString(),
        );
        expect(find.textContaining('Context:'), findsNothing, reason: raw);
        expect(find.textContaining('script'), findsNothing, reason: raw);
      }
    });

    testWidgets('no scope means no context chip', (tester) async {
      await pumpRouterApp(tester, initialLocation: AppRoutes.ai);
      expect(find.textContaining('Context:'), findsNothing);
    });
  });

  group('layout resilience', () {
    for (final scale in [1.0, 2.0]) {
      for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
        testWidgets(
          'small phone, text scale $scale, $dir: no overflow on any tab',
          (tester) async {
            await pumpRouterApp(
              tester,
              surfaceSize: const Size(320, 568),
              textScale: scale,
              textDirection: dir,
            );
            for (final label in [
              'Portfolio',
              'AI Wealth',
              'Goals',
              'More',
              'Home',
            ]) {
              await tapTab(tester, label);
              expect(
                tester.takeException(),
                isNull,
                reason: '$label @ $scale $dir',
              );
            }
          },
        );
      }
    }
  });

  testWidgets('router navigation helpers use the route constants', (
    tester,
  ) async {
    final router = await pumpRouterApp(tester);
    router.go(AppRoutes.goals);
    await tester.pumpAndSettle();
    expect(find.text('Coming soon'), findsOneWidget);
    expect(
      GoRouter.of(tester.element(find.byType(Scaffold).first)),
      same(router),
    );
  });
}

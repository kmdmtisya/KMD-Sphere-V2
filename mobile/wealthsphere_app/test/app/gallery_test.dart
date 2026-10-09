import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/app/gallery/gallery_screen.dart';
import 'package:wealthsphere_app/app/gallery/gallery_sections.dart';
import 'package:wealthsphere_app/app/router.dart';

import '../helpers/pump_app.dart';
import '../helpers/pump_router.dart';

void main() {
  group('GalleryScreen', () {
    testWidgets('shows every section title', (tester) async {
      await tester.pumpApp(
        const GalleryScreen(),
        surfaceSize: const Size(400, 800),
        settle: false,
      );
      for (final s in gallerySections) {
        await tester.scrollUntilVisible(
          find.text(s.title),
          300,
          scrollable: find.byType(Scrollable).first,
        );
        expect(find.text(s.title), findsOneWidget, reason: s.id);
      }
    });

    testWidgets('is labelled DEMO', (tester) async {
      await tester.pumpApp(const GalleryScreen(), settle: false);
      expect(find.text('DEMO'), findsWidgets);
    });

    testWidgets('theme, text size and RTL toggles change the rendering', (
      tester,
    ) async {
      await tester.pumpApp(
        const GalleryScreen(),
        surfaceSize: const Size(400, 800),
        settle: false,
      );
      Brightness shown() =>
          Theme.of(tester.element(find.byType(Scaffold).first)).brightness;
      TextDirection dir() =>
          Directionality.of(tester.element(find.byType(Scaffold).first));
      double scale() =>
          MediaQuery.textScalerOf(tester.element(find.byType(Scaffold).first))
              .scale(10);

      expect(shown(), Brightness.light);
      await tester.tap(find.text('Dark'));
      await tester.pump();
      expect(shown(), Brightness.dark);

      await tester.tap(find.text('2.0x'));
      await tester.pump();
      expect(scale(), 20);

      await tester.tap(find.byType(Switch));
      await tester.pump();
      expect(dir(), TextDirection.rtl);
    });

    for (final dark in [false, true]) {
      for (final rtl in [false, true]) {
        testWidgets(
          'no overflow at 2.0x text on 320 wide (${dark ? 'dark' : 'light'}, ${rtl ? 'rtl' : 'ltr'})',
          (tester) async {
            await tester.pumpApp(
              const GalleryScreen(),
              surfaceSize: const Size(320, 640),
              settle: false,
            );
            if (dark) await tester.tap(find.text('Dark'));
            await tester.tap(find.text('2.0x'));
            if (rtl) await tester.tap(find.byType(Switch));
            await tester.pump();
            for (final s in gallerySections) {
              await tester.scrollUntilVisible(
                find.text(s.title),
                300,
                scrollable: find.byType(Scrollable).first,
              );
              await tester.pump();
            }
            await tester.drag(
              find.byType(Scrollable).first,
              const Offset(0, -3000),
            );
            await tester.pump();
            expect(tester.takeException(), isNull);
          },
        );
      }
    }
  });

  group('gallery route', () {
    testWidgets('is reachable from More in debug builds', (tester) async {
      final router = await pumpRouterApp(tester);
      await tester.tap(
        find.descendant(
          of: find.byType(NavigationBar),
          matching: find.text('More'),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Component gallery (debug)'));
      await tester.pump(const Duration(seconds: 1));
      expect(find.text('Component gallery'), findsOneWidget);
      expect(router.routerDelegate.currentConfiguration.uri.path, isNotEmpty);
    });

    testWidgets('exists only when enabled (absent in release builds)', (
      tester,
    ) async {
      final enabled = createRouter(enableGallery: true);
      final disabled = createRouter(enableGallery: false);
      addTearDown(enabled.dispose);
      addTearDown(disabled.dispose);
      bool hasGallery(GoRouter r) => r.configuration.routes
          .whereType<GoRoute>()
          .any((g) => g.path == AppRoutes.gallery);
      expect(hasGallery(enabled), isTrue);
      expect(hasGallery(disabled), isFalse);
    });

    testWidgets('a gallery link in a build without it shows not-found', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: AppRoutes.gallery,
        enableGallery: false,
      );
      expect(find.byType(GalleryScreen), findsNothing);
      expect(find.text('Page not found'), findsWidgets);
    });
  });
}

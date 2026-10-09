// ignore_for_file: invalid_use_of_internal_member
// `copyWithPrevious` is the only way to build a refreshing/failed-refresh AsyncValue in a unit test.
import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../../helpers/pump_app.dart';

Widget page(Widget child) =>
    Scaffold(body: SingleChildScrollView(child: child));

void main() {
  group('Status banners', () {
    final now = DateTime.utc(2026, 10, 9, 12);

    testWidgets('offline banner explains and offers retry', (tester) async {
      var retried = 0;
      await tester.pumpApp(page(OfflineBanner(onRetry: () => retried++)));
      expect(find.text("You're offline. Showing saved data."), findsOneWidget);
      await tester.tap(find.text('Try again'));
      expect(retried, 1);
    });

    testWidgets('no retry button without a handler', (tester) async {
      await tester.pumpApp(page(const OfflineBanner()));
      expect(find.text('Try again'), findsNothing);
    });

    testWidgets('stale banner names the age of the data', (tester) async {
      await tester.pumpApp(
        page(
          StaleDataBanner(
            asOf: now.subtract(const Duration(hours: 3)),
            now: now,
          ),
        ),
      );
      expect(find.textContaining('3 hours'), findsOneWidget);
      expect(find.textContaining('out of date'), findsOneWidget);
    });

    testWidgets('stale banner without a timestamp uses the generic text', (
      tester,
    ) async {
      await tester.pumpApp(page(const StaleDataBanner()));
      expect(find.text('These figures may be out of date.'), findsOneWidget);
    });

    testWidgets('banners are live regions so changes are announced', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(const OfflineBanner()));
      expect(
        tester.getSemantics(find.bySemanticsLabel(RegExp("offline"))),
        isSemantics(isLiveRegion: true),
      );
      handle.dispose();
    });
  });

  group('Skeleton loader', () {
    testWidgets('announces loading and hides the placeholder shapes', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(SkeletonLoader.card()), settle: false);
      expect(find.bySemanticsLabel('Loading'), findsOneWidget);
      handle.dispose();
    });

    testWidgets('shimmer animates normally', (tester) async {
      await tester.pumpApp(page(SkeletonLoader.lines()), settle: false);
      expect(find.byType(ShaderMask), findsOneWidget);
      await tester.pump(const Duration(milliseconds: 400));
      expect(tester.hasRunningAnimations, isTrue);
    });

    testWidgets(
      'reduced motion shows a static placeholder with no running animation',
      (tester) async {
        await tester.pumpApp(
          Builder(
            builder: (context) => MediaQuery(
              data: MediaQuery.of(context).copyWith(disableAnimations: true),
              child: page(SkeletonLoader.card()),
            ),
          ),
          settle: false,
        );
        await tester.pump(const Duration(milliseconds: 400));
        expect(tester.hasRunningAnimations, isFalse);
      },
    );

    testWidgets('can be switched off', (tester) async {
      await tester.pumpApp(
        page(
          const SkeletonLoader(animate: false, child: SkeletonBox(height: 20)),
        ),
      );
      expect(tester.hasRunningAnimations, isFalse);
    });

    testWidgets('disposes cleanly while animating', (tester) async {
      await tester.pumpApp(page(SkeletonLoader.card()), settle: false);
      await tester.pumpWidget(const SizedBox());
      expect(tester.takeException(), isNull);
    });
  });

  group('Empty and error states', () {
    testWidgets('empty state: default title, optional action', (tester) async {
      var tapped = 0;
      await tester.pumpApp(
        page(EmptyState(actionLabel: 'Add holding', onAction: () => tapped++)),
      );
      expect(find.text('Nothing here yet'), findsOneWidget);
      await tester.tap(find.text('Add holding'));
      expect(tapped, 1);
    });

    testWidgets('empty state without an action shows no button', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          const EmptyState(title: 'No goals', message: 'Create one to start.'),
        ),
      );
      expect(find.byType(FilledButton), findsNothing);
      expect(find.text('Create one to start.'), findsOneWidget);
    });

    testWidgets('error state: friendly text and retry, no technical detail', (
      tester,
    ) async {
      var retried = 0;
      await tester.pumpApp(page(ErrorState(onRetry: () => retried++)));
      expect(find.text('Something went wrong'), findsOneWidget);
      expect(find.textContaining('connection'), findsOneWidget);
      await tester.tap(find.text('Try again'));
      expect(retried, 1);
    });

    testWidgets('retry target is at least 48 dp', (tester) async {
      await tester.pumpApp(page(ErrorState(onRetry: () {})));
      final size = tester.getSize(
        find.ancestor(
          of: find.text('Try again'),
          matching: find.bySubtype<ButtonStyleButton>(),
        ),
      );
      expect(size.height, greaterThanOrEqualTo(48));
    });
  });

  group('AsyncValueView', () {
    Widget view(
      AsyncValue<List<int>> v, {
      VoidCallback? onRetry,
      bool empty = true,
    }) => page(
      AsyncValueView<List<int>>(
        value: v,
        isEmpty: empty ? (d) => d.isEmpty : null,
        onRetry: onRetry,
        data: (d) => Text('count=${d.length}'),
      ),
    );

    testWidgets('loading shows the skeleton', (tester) async {
      await tester.pumpApp(view(const AsyncLoading()), settle: false);
      expect(find.byType(SkeletonLoader), findsOneWidget);
    });

    testWidgets('data shows the content', (tester) async {
      await tester.pumpApp(view(const AsyncData([1, 2])));
      expect(find.text('count=2'), findsOneWidget);
    });

    testWidgets('empty data shows the empty state', (tester) async {
      await tester.pumpApp(view(const AsyncData([])));
      expect(find.byType(EmptyState), findsOneWidget);
      expect(find.textContaining('count='), findsNothing);
    });

    testWidgets('error without data shows the error state with retry', (
      tester,
    ) async {
      var retried = 0;
      await tester.pumpApp(
        view(
          AsyncError(Exception('boom'), StackTrace.empty),
          onRetry: () => retried++,
        ),
      );
      expect(find.byType(ErrorState), findsOneWidget);
      expect(
        find.textContaining('boom'),
        findsNothing,
        reason: 'raw errors are never shown to users',
      );
      await tester.tap(find.text('Try again'));
      expect(retried, 1);
    });

    testWidgets('a refresh error keeps showing the previous data', (
      tester,
    ) async {
      final value = const AsyncData<List<int>>([1, 2, 3])
          .copyWithPrevious(const AsyncLoading<List<int>>());
      await tester.pumpApp(view(value));
      expect(find.text('count=3'), findsOneWidget);
      expect(find.byType(SkeletonLoader), findsNothing);
    });

    testWidgets('a failed refresh does not replace data with an error screen', (
      tester,
    ) async {
      final value = AsyncError<List<int>>(
        Exception('x'),
        StackTrace.empty,
      ).copyWithPrevious(const AsyncData([4]));
      await tester.pumpApp(view(value));
      expect(find.text('count=1'), findsOneWidget);
      expect(find.byType(ErrorState), findsNothing);
    });

    testWidgets('custom loading and error builders are honoured', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          AsyncValueView<int>(
            value: AsyncError<int>(Exception('x'), StackTrace.empty),
            data: (d) => Text('$d'),
            errorBuilder: (e, s) => const Text('custom error'),
          ),
        ),
      );
      expect(find.text('custom error'), findsOneWidget);
    });
  });

  group(
    'Variant matrix: light/dark x LTR/RTL x text 1.0/2.0 on a 320x568 screen',
    () {
      final builders = <String, Widget Function()>{
        'currency + change': () => Column(
          children: [
            CurrencyAmount(
              money: Money.parse('1234567.89', 'USD'),
              nativeMoney: Money.parse('4534012.34', 'AED'),
            ),
            ChangeIndicator(
              percent: Decimal.parse('-12.34'),
              amount: Money.parse('-1500.00', 'USD'),
              periodLabel: 'this month',
            ),
          ],
        ),
        'risk + demo': () => const Column(
          children: [
            RiskLabel(level: RiskLevel.high),
            DemoBadge(),
            DemoBanner(),
          ],
        ),
        'disclosure': () => const DisclosurePanel(
          title: 'How is this calculated?',
          summary: 'Illustrative projection. Not a guarantee of returns.',
          details: Text(
            'Assumes a constant annual return and monthly contributions.',
          ),
          initiallyExpanded: true,
        ),
        'banners': () => Column(
          children: [
            const OfflineBanner(),
            StaleDataBanner(
              asOf: DateTime.utc(2026, 10, 9, 9),
              now: DateTime.utc(2026, 10, 9, 12),
            ),
          ],
        ),
        'empty': () => const EmptyState(actionLabel: 'Add holding'),
        'error': () => ErrorState(onRetry: () {}),
        'as of': () => DataAsOfLabel(
          asOf: DateTime.utc(2026, 10, 9, 9),
          now: DateTime.utc(2026, 10, 9, 12),
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
    },
  );
}

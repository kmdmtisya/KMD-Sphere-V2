import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/goals/application/goal_form.dart';
import 'package:wealthsphere_app/features/goals/application/goal_providers.dart';
import 'package:wealthsphere_app/features/goals/data/goal_repository.dart';
import 'package:wealthsphere_app/features/goals/domain/goal_models.dart';
import 'package:wealthsphere_app/features/goals/presentation/goal_detail_screen.dart';
import 'package:wealthsphere_app/features/goals/presentation/goal_form_screen.dart';
import 'package:wealthsphere_app/features/goals/presentation/goals_screen.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';
import '../../helpers/strict_tap_target.dart';

final DateTime fixedToday = DateTime(2026, 10, 9, 12);

List<Override> overrides() =>
    demoOverrides(extra: [goalsTodayProvider.overrideWithValue(fixedToday)]);

ProviderContainer containerOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));

Future<void> pumpScreen(
  WidgetTester tester,
  Widget screen, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
  double height = 3200,
}) => tester.pumpApp(
  screen,
  themeMode: mode,
  textScale: scale,
  textDirection: dir,
  overrides: overrides(),
  surfaceSize: Size(400, height),
);

Finder field(String label) => find.widgetWithText(TextField, label);

Future<void> accessibilityChecks(WidgetTester tester) async {
  expect(tester.takeException(), isNull);
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(const StrictTapTargetGuideline()));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
}

Future<void> fillValidForm(WidgetTester tester, {String name = 'Car'}) async {
  await tester.enterText(field('Goal name'), name);
  await tester.enterText(field('Target amount'), '20000');
  await tester.tap(find.text('Select a date'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('OK'));
  await tester.pumpAndSettle();
  await tester.enterText(field('Contribution'), '300');
  await tester.enterText(field('Base annual return (%)'), '5');
}

Future<void> tapSave(WidgetTester tester) async {
  await tester.ensureVisible(find.text('Save goal'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Save goal'));
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('Goals list', () {
    testWidgets('shows a card per goal with an estimate summary', (
      tester,
    ) async {
      await pumpScreen(tester, const GoalsScreen());
      expect(find.byType(GoalProgressCard), findsNWidgets(4));
      expect(find.text('Home deposit'), findsOneWidget);
      expect(
        find.text('3 of 4 goals on track under your assumptions'),
        findsOneWidget,
      );
      expect(find.textContaining('not guaranteed'), findsWidgets);
      expect(find.text('DEMO'), findsWidgets);
    });

    testWidgets('each status is worded as an estimate', (tester) async {
      await pumpScreen(tester, const GoalsScreen());
      expect(
        find.text('Estimate based on your assumptions. It is not guaranteed.'),
        findsNWidgets(4),
      );
      final statuses = tester
          .widgetList<GoalProgressCard>(find.byType(GoalProgressCard))
          .map((c) => c.status)
          .toList();
      expect(
        statuses.where((s) => s == GoalProgressStatus.behind),
        hasLength(1),
      );
    });

    testWidgets('cards open and the add button calls back', (tester) async {
      final opened = <String>[];
      var added = 0;
      await pumpScreen(
        tester,
        GoalsScreen(onOpen: (e) => opened.add(e.goal.id), onAdd: () => added++),
      );
      await tester.tap(find.byType(GoalProgressCard).first);
      expect(opened, hasLength(1));
      await tester.tap(find.text('Add goal'));
      expect(added, 1);
    });

    testWidgets('a goal without figures says so and shows no number', (
      tester,
    ) async {
      await pumpScreen(tester, const GoalsScreen());
      final container = containerOf(tester);
      final repo = container.read(goalRepositoryProvider);
      final input = (await repo.goal('g-home')).goal;
      await repo.update(
        'g-home',
        GoalInput(
          name: input.name,
          type: input.type,
          target: input.target,
          targetDate: input.targetDate,
          targetInTodaysMoney: false,
          assumptions: input.assumptions,
        ),
      );
      container.invalidate(goalsProvider);
      await tester.pumpAndSettle();
      expect(find.byType(GoalProgressCard), findsNWidgets(3));
      expect(
        find.textContaining("The server calculates this goal's progress"),
        findsOneWidget,
      );
      expect(
        find.text('2 of 3 goals on track under your assumptions'),
        findsOneWidget,
      );
    });

    testWidgets('failure shows an error with retry, then recovers', (
      tester,
    ) async {
      await tester.pumpApp(
        const GoalsScreen(),
        overrides: demoOverrides(
          behavior: const DemoBehavior(
            latency: Duration.zero,
            failNextCalls: 1,
          ),
        ),
        surfaceSize: const Size(400, 3200),
      );
      expect(find.byType(GoalProgressCard), findsNothing);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.byType(GoalProgressCard), findsNWidgets(4));
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpScreen(
                tester,
                GoalsScreen(onOpen: (_) {}, onAdd: () {}),
                mode: mode,
                scale: scale,
                dir: dir,
                height: 6000,
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('Goal detail', () {
    testWidgets(
      'shows progress, figures and the required contribution as an estimate',
      (tester) async {
        await pumpScreen(tester, const GoalDetailScreen(goalId: 'g-trip'));
        expect(find.byType(GoalProgressCard), findsOneWidget);
        expect(find.text('Required contribution'), findsOneWidget);
        expect(find.text('\$1,213.88 per month'), findsOneWidget);
        expect(find.textContaining('An estimate'), findsOneWidget);
        expect(find.textContaining('not guaranteed'), findsWidgets);
        expect(
          find.text('Your contribution: \$150.00 per month'),
          findsOneWidget,
        );
        expect(find.text('Still to go'), findsOneWidget);
        expect(find.text('8 months'), findsOneWidget);
      },
    );

    testWidgets('lists the three scenarios with a word as well as an icon', (
      tester,
    ) async {
      await pumpScreen(tester, const GoalDetailScreen(goalId: 'g-trip'));
      expect(
        find.text('Conservative: falls short of the target'),
        findsOneWidget,
      );
      expect(find.text('Base: falls short of the target'), findsOneWidget);
      expect(find.text('Growth: falls short of the target'), findsOneWidget);
      expect(find.textContaining('not forecasts or promises'), findsOneWidget);
    });

    testWidgets('an on-track goal shows a scenario that reaches the target', (
      tester,
    ) async {
      await pumpScreen(tester, const GoalDetailScreen(goalId: 'g-home'));
      expect(find.text('Base: reaches the target'), findsOneWidget);
    });

    testWidgets('shows the assumptions the estimates rest on', (tester) async {
      await pumpScreen(tester, const GoalDetailScreen(goalId: 'g-home'));
      expect(find.text('Your assumptions'), findsOneWidget);
      expect(find.text('Base return'), findsOneWidget);
      expect(find.text('5.00%'), findsOneWidget);
      expect(find.text('All portfolios'), findsOneWidget);
    });

    testWidgets('a changed goal says the server must calculate it', (
      tester,
    ) async {
      await pumpScreen(tester, const GoalDetailScreen(goalId: 'g-home'));
      final container = containerOf(tester);
      final repo = container.read(goalRepositoryProvider);
      final g = (await repo.goal('g-home')).goal;
      await repo.update(
        'g-home',
        GoalInput(
          name: g.name,
          type: g.type,
          target: g.target,
          targetDate: g.targetDate,
          targetInTodaysMoney: g.targetInTodaysMoney,
          assumptions: g.assumptions,
        ),
      );
      container.invalidate(goalProvider);
      await tester.pumpAndSettle();
      expect(find.byType(GoalProgressCard), findsNothing);
      expect(
        find.textContaining("Calculated by the server. The demo can't"),
        findsOneWidget,
      );
      expect(find.text('Scenarios'), findsNothing);
    });

    testWidgets('edit and ask-AI call back with the goal', (tester) async {
      Goal? edited;
      Goal? asked;
      await pumpScreen(
        tester,
        GoalDetailScreen(
          goalId: 'g-home',
          onEdit: (g) => edited = g,
          onAskAi: (g) => asked = g,
        ),
      );
      await tester.tap(find.text('Edit goal'));
      await tester.tap(find.text('Ask AI about this goal'));
      expect(edited?.id, 'g-home');
      expect(asked?.id, 'g-home');
    });

    testWidgets('an unknown goal shows an error, not a blank screen', (
      tester,
    ) async {
      await pumpScreen(tester, const GoalDetailScreen(goalId: 'nope'));
      expect(find.text('Try again'), findsOneWidget);
    });

    for (final id in ['g-home', 'g-trip']) {
      for (final mode in [ThemeMode.light, ThemeMode.dark]) {
        for (final scale in [1.0, 2.0]) {
          testWidgets(
            'detail $id meets the accessibility guidelines (${mode.name}, ${scale}x)',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpScreen(
                tester,
                GoalDetailScreen(goalId: id, onEdit: (_) {}, onAskAi: (_) {}),
                mode: mode,
                scale: scale,
                height: 6000,
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('Goal form', () {
    testWidgets('an empty form lists every missing field in plain words', (
      tester,
    ) async {
      await pumpScreen(tester, const GoalFormScreen(), height: 4000);
      await tapSave(tester);
      expect(find.text('Enter a name for the goal.'), findsOneWidget);
      expect(find.text('Choose a target date.'), findsOneWidget);
      expect(find.text('Enter a value.'), findsNWidgets(3));
      expect(find.text('Fix 5 fields to continue'), findsOneWidget);
    });

    testWidgets('no return rate is pre-filled', (tester) async {
      await pumpScreen(tester, const GoalFormScreen(), height: 4000);
      for (final label in [
        'Base annual return (%)',
        'Conservative return (%, optional)',
        'Growth return (%, optional)',
      ]) {
        expect(
          tester.widget<TextField>(field(label)).controller!.text,
          isEmpty,
        );
      }
      expect(find.textContaining('does not suggest returns'), findsOneWidget);
    });

    testWidgets(
      'limits are explained next to the field and update as you type',
      (tester) async {
        await pumpScreen(tester, const GoalFormScreen(), height: 4000);
        await tapSave(tester);
        await tester.enterText(field('Target amount'), '0');
        await tester.pumpAndSettle();
        expect(find.textContaining('Must be at least'), findsOneWidget);
        await tester.enterText(field('Target amount'), '10000000001');
        await tester.pumpAndSettle();
        expect(find.textContaining('Must be at most'), findsWidgets);
        await tester.enterText(field('Target amount'), '1000.123');
        await tester.pumpAndSettle();
        // The formatter refuses a third decimal, so the field holds 1000.12.
        expect(
          tester.widget<TextField>(field('Target amount')).controller!.text,
          '1000.12',
        );
        await tester.enterText(field('Base annual return (%)'), '51');
        await tester.pumpAndSettle();
        expect(find.textContaining('Must be at most 50'), findsOneWidget);
      },
    );

    testWidgets('conservative above base is explained', (tester) async {
      await pumpScreen(tester, const GoalFormScreen(), height: 4000);
      await tapSave(tester);
      await tester.enterText(field('Base annual return (%)'), '5');
      await tester.enterText(field('Conservative return (%, optional)'), '6');
      await tester.pumpAndSettle();
      expect(
        find.text("Conservative return can't be higher than the base return."),
        findsOneWidget,
      );
    });

    testWidgets(
      'a valid form saves, reports the goal and shows it in the list',
      (tester) async {
        GoalEntry? saved;
        await pumpScreen(
          tester,
          GoalFormScreen(onSaved: (e) => saved = e),
          height: 4000,
        );
        await fillValidForm(tester);
        await tapSave(tester);
        expect(saved, isNotNull);
        expect(saved!.goal.name, 'Car');
        expect(saved!.goal.targetDate, DateTime(2026, 10, 10));
        expect(saved!.figures, isNull);
        final all = await containerOf(tester)
            .read(goalRepositoryProvider)
            .goals();
        expect(all, hasLength(5));
      },
    );

    testWidgets('a name already used is refused on the name field', (
      tester,
    ) async {
      GoalEntry? saved;
      await pumpScreen(
        tester,
        GoalFormScreen(onSaved: (e) => saved = e),
        height: 4000,
      );
      await fillValidForm(tester, name: 'home deposit');
      await tapSave(tester);
      expect(
        find.text('You already have a goal with this name.'),
        findsOneWidget,
      );
      expect(saved, isNull);
    });

    testWidgets('editing shows the current values and saves a change', (
      tester,
    ) async {
      GoalEntry? saved;
      await pumpScreen(
        tester,
        GoalFormScreen(goalId: 'g-trip', onSaved: (e) => saved = e),
        height: 4000,
      );
      expect(
        tester.widget<TextField>(field('Goal name')).controller!.text,
        'Family travel',
      );
      expect(
        tester.widget<TextField>(field('Target amount')).controller!.text,
        '12000',
      );
      expect(
        tester
            .widget<TextField>(field('Base annual return (%)'))
            .controller!
            .text,
        '3',
      );
      await tester.enterText(field('Contribution'), '900');
      await tapSave(tester);
      expect(saved?.goal.id, 'g-trip');
      expect(saved?.goal.assumptions.contribution.amount.toString(), '900');
    });

    testWidgets('a failed save keeps the form and offers a retry', (
      tester,
    ) async {
      await pumpScreen(tester, const GoalFormScreen(), height: 4000);
      await fillValidForm(tester);
      containerOf(tester)
          .read(demoBehaviorProvider.notifier)
          .set(const DemoBehavior(latency: Duration.zero, failNextCalls: 1));
      await tapSave(tester);
      expect(
        find.text('The goal could not be saved. Try again.'),
        findsOneWidget,
      );
      expect(
        tester.widget<TextField>(field('Goal name')).controller!.text,
        'Car',
      );
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      final all = await containerOf(tester)
          .read(goalRepositoryProvider)
          .goals();
      expect(all, hasLength(5));
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'form with errors meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpScreen(
                tester,
                const GoalFormScreen(),
                mode: mode,
                scale: scale,
                dir: dir,
                height: 7000,
              );
              await tapSave(tester);
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('Routes', () {
    testWidgets(
      'the Goals tab shows the list; cards, add and edit are reachable',
      (tester) async {
        await pumpRouterApp(
          tester,
          initialLocation: '/goals',
          surfaceSize: const Size(400, 3200),
          overrides: overrides(),
        );
        expect(find.byType(GoalsScreen), findsOneWidget);

        await tester.tap(find.text('Add goal'));
        await tester.pumpAndSettle();
        expect(find.byType(GoalFormScreen), findsOneWidget);
        expect(find.text('Add goal'), findsWidgets);
        await tester.tap(find.byType(BackButton));
        await tester.pumpAndSettle();

        await tester.tap(find.byType(GoalProgressCard).first);
        await tester.pumpAndSettle();
        expect(find.byType(GoalDetailScreen), findsOneWidget);

        await tester.tap(find.text('Edit goal'));
        await tester.pumpAndSettle();
        expect(find.byType(GoalFormScreen), findsOneWidget);
        expect(find.text('Edit goal'), findsWidgets);
      },
    );

    testWidgets('"add" is not read as a goal id', (tester) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/goals/add',
        surfaceSize: const Size(400, 3200),
        overrides: overrides(),
      );
      expect(find.byType(GoalFormScreen), findsOneWidget);
      expect(find.byType(GoalDetailScreen), findsNothing);
    });

    testWidgets('a goal deep link opens it', (tester) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/goals/g-home',
        surfaceSize: const Size(400, 3200),
        overrides: overrides(),
      );
      expect(find.byType(GoalDetailScreen), findsOneWidget);
      expect(find.text('Home deposit'), findsWidgets);
    });

    testWidgets('Ask AI opens AI Wealth with the goal as context', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/goals/g-home',
        surfaceSize: const Size(400, 3200),
        overrides: overrides(),
      );
      await tester.ensureVisible(find.text('Ask AI about this goal'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ask AI about this goal'));
      await tester.pumpAndSettle();
      expect(find.textContaining('g-home'), findsWidgets);
    });
  });
}

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/connectivity/connectivity.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/ai_wealth/presentation/ai_wealth_screen.dart';
import 'package:wealthsphere_app/features/copilot/data/copilot_repository.dart';
import 'package:wealthsphere_app/features/copilot/domain/chat_models.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';

const performance = 'How is my portfolio performing?';

/// Records the scope sent with each question.
class ScopeRecorder implements CopilotRepository {
  ScopeRecorder(this._inner);

  final CopilotRepository _inner;
  final List<AiScope?> scopes = [];

  @override
  Stream<ChatEvent> ask(String question, {AiScope? scope}) {
    scopes.add(scope);
    return _inner.ask(question, scope: scope);
  }

  @override
  Future<CopilotIntro> intro() => _inner.intro();

  @override
  Future<List<String>> suggestedQuestions() => _inner.suggestedQuestions();
}

Override recordScopes(void Function(ScopeRecorder) use) =>
    copilotRepositoryProvider.overrideWith((ref) {
      final repo = ScopeRecorder(
        DemoCopilotRepository(
          ref.watch(demoAssetsProvider),
          () => ref.read(demoBehaviorProvider),
          ref.read(demoBehaviorProvider.notifier).gate,
        ),
      );
      use(repo);
      return repo;
    });

class _Offline extends ConnectivityNotifier {
  @override
  bool build() => false;
}

Future<void> pumpAi(
  WidgetTester tester, {
  AiScope? scope,
  DemoBehavior behavior = DemoBehavior.instant,
  List<Override> extra = const [],
  Size size = const Size(400, 2400),
  double textScale = 1.0,
  ThemeMode mode = ThemeMode.light,
  TextDirection dir = TextDirection.ltr,
  bool settle = true,
}) => tester.pumpApp(
  AiWealthScreen(scope: scope),
  overrides: demoOverrides(behavior: behavior, extra: extra),
  surfaceSize: size,
  textScale: textScale,
  themeMode: mode,
  textDirection: dir,
  settle: settle,
);

/// Collects screen-reader announcements.
List<String> captureAnnouncements(WidgetTester tester) {
  final messages = <String>[];
  tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<dynamic>(
    SystemChannels.accessibility,
    (message) async {
      final map = message as Map<Object?, Object?>;
      if (map['type'] == 'announce') {
        messages.add(
          (map['data']! as Map<Object?, Object?>)['message']! as String,
        );
      }
      return null;
    },
  );
  addTearDown(
    () => tester.binding.defaultBinaryMessenger
        .setMockDecodedMessageHandler<dynamic>(
          SystemChannels.accessibility,
          null,
        ),
  );
  return messages;
}

const headings = [
  'Observed data',
  'Calculated',
  'Assumptions',
  'AI interpretation',
];

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('empty state', () {
    testWidgets('intro, DEMO notice, suggestions, scope chip and footer', (
      tester,
    ) async {
      await pumpAi(tester);
      expect(
        find.text('Ask about your portfolio, risks, goals and forecasts.'),
        findsOneWidget,
      );
      expect(
        find.text('Demo responses, not connected to your data.'),
        findsOneWidget,
      );
      expect(find.byType(ActionChip), findsNWidgets(4));
      expect(find.text(performance), findsOneWidget);
      expect(find.text('Context: All portfolios'), findsOneWidget);
      expect(
        find.text(
          'Informational only, not financial advice. No trades are executed.',
        ),
        findsOneWidget,
      );
      expect(find.text('DEMO'), findsWidgets);
    });
  });

  group('answers', () {
    testWidgets(
      'a suggested question streams a four-section answer with sources',
      (tester) async {
        final announced = captureAnnouncements(tester);
        await pumpAi(tester);
        await tester.tap(find.text(performance));
        await tester.pumpAndSettle();
        expect(
          find.text(performance),
          findsOneWidget,
          reason: 'the question bubble',
        );
        for (final h in headings) {
          expect(find.text(h), findsOneWidget, reason: h);
        }
        expect(find.textContaining('total return of 14.09%'), findsOneWidget);
        expect(find.byType(EvidenceSourceChip), findsNWidgets(2));
        expect(find.byType(DataAsOfLabel), findsOneWidget);
        expect(announced, ['Answer ready']);
      },
    );

    testWidgets('progress rows show while the assistant works', (tester) async {
      await pumpAi(
        tester,
        behavior: const DemoBehavior(
          latency: Duration.zero,
          streamInterval: Duration(milliseconds: 200),
        ),
        settle: false,
      );
      await tester.pumpAndSettle(const Duration(milliseconds: 10));
      await tester.tap(find.text(performance));
      await tester.pump(const Duration(milliseconds: 250));
      expect(find.text('Fetching portfolio summary…'), findsOneWidget);
      await tester.pumpAndSettle(const Duration(milliseconds: 100));
      expect(find.text('Fetching portfolio summary…'), findsNothing);
    });

    testWidgets(
      'while streaming the composer shows Stop and the scope chip is locked',
      (tester) async {
        await pumpAi(
          tester,
          behavior: const DemoBehavior(
            latency: Duration.zero,
            streamInterval: Duration(milliseconds: 200),
          ),
          settle: false,
        );
        await tester.pumpAndSettle(const Duration(milliseconds: 10));
        await tester.tap(find.text(performance));
        await tester.pump(const Duration(milliseconds: 250));
        expect(find.byIcon(Icons.stop_rounded), findsOneWidget);
        expect(find.byIcon(Icons.arrow_upward_rounded), findsNothing);
        expect(
          tester.widget<InputChip>(find.byType(InputChip)).onPressed,
          isNull,
        );
        await tester.pumpAndSettle(const Duration(milliseconds: 100));
        expect(find.byIcon(Icons.arrow_upward_rounded), findsOneWidget);
      },
    );

    testWidgets(
      'Stop keeps what arrived, says it is incomplete and announces it',
      (tester) async {
        final announced = captureAnnouncements(tester);
        await pumpAi(
          tester,
          behavior: const DemoBehavior(
            latency: Duration.zero,
            streamInterval: Duration(milliseconds: 200),
          ),
          settle: false,
        );
        await tester.pumpAndSettle(const Duration(milliseconds: 10));
        await tester.tap(find.text(performance));
        for (var i = 0; i < 4; i++) {
          await tester.pump(const Duration(milliseconds: 200));
        }
        await tester.tap(find.byIcon(Icons.stop_rounded));
        await tester.pumpAndSettle(const Duration(milliseconds: 100));
        expect(
          find.text('Stopped. The answer may be incomplete.'),
          findsOneWidget,
        );
        final shown = headings
            .where((h) => find.text(h).evaluate().isNotEmpty)
            .length;
        expect(shown, lessThan(4));
        expect(
          find.byIcon(Icons.arrow_upward_rounded),
          findsOneWidget,
          reason: 'can ask again',
        );
        expect(announced, ['Answer stopped']);
      },
    );

    testWidgets(
      'a refusal is shown in its own style, without answer sections',
      (tester) async {
        await pumpAi(tester);
        await tester.enterText(
          find.byType(TextField),
          'Guarantee me a 20% return',
        );
        await tester.pump();
        await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
        await tester.pumpAndSettle();
        expect(find.byKey(const ValueKey('refusal')), findsOneWidget);
        expect(find.text("Can't help with that"), findsOneWidget);
        expect(
          find.textContaining("I can't guarantee returns"),
          findsOneWidget,
        );
        for (final h in headings) {
          expect(find.text(h), findsNothing);
        }
      },
    );

    testWidgets(
      'the failure script ends with its message and an inline retry',
      (tester) async {
        final announced = captureAnnouncements(tester);
        await pumpAi(tester);
        await tester.enterText(
          find.byType(TextField),
          'Show me a failing request (demo)',
        );
        await tester.pump();
        await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
        await tester.pumpAndSettle();
        expect(
          find.text(
            'The assistant could not complete this request. Please try again.',
          ),
          findsOneWidget,
        );
        expect(find.text('Try again'), findsOneWidget);
        expect(announced, ['The answer failed']);
      },
    );

    testWidgets(
      'a transport failure shows a generic message and Retry gets the answer',
      (tester) async {
        await pumpAi(tester);
        // Fail the next repository call, which is the question below.
        ProviderScope.containerOf(tester.element(find.byType(AiWealthScreen)))
            .read(demoBehaviorProvider.notifier)
            .set(DemoBehavior.instant.copyWith(failNextCalls: 1));
        await tester.tap(find.text(performance));
        await tester.pumpAndSettle();
        expect(
          find.text("The assistant couldn't answer. Try again."),
          findsOneWidget,
        );
        expect(
          find.textContaining('Demo failure'),
          findsNothing,
          reason: 'raw errors are never shown',
        );
        await tester.tap(find.text('Try again'));
        await tester.pumpAndSettle();
        expect(
          find.text("The assistant couldn't answer. Try again."),
          findsNothing,
        );
        expect(find.text('Observed data'), findsOneWidget);
        expect(
          find.text(performance),
          findsOneWidget,
          reason: 'the retried turn replaces the failed one',
        );
      },
    );

    testWidgets('an unscripted question gets the fixture reply', (
      tester,
    ) async {
      await pumpAi(tester);
      await tester.enterText(
        find.byType(TextField),
        'Which stock should I buy?',
      );
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pumpAndSettle();
      expect(
        find.text('Demo mode can answer the suggested questions only.'),
        findsOneWidget,
      );
    });

    testWidgets('several turns stay in the conversation', (tester) async {
      await pumpAi(tester);
      await tester.tap(find.text(performance));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField),
        'What are the biggest risks in my portfolio?',
      );
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      await tester.pumpAndSettle();
      expect(find.text('Observed data'), findsNWidgets(2));
    });
  });

  group('scope', () {
    testWidgets(
      'a portfolio scope from the route shows its name and is sent with the question',
      (tester) async {
        late ScopeRecorder repo;
        await pumpAi(
          tester,
          scope: const AiScope(AiScopeKind.portfolio, 'p-growth'),
          extra: [recordScopes((r) => repo = r)],
        );
        expect(find.text('Context: Growth'), findsOneWidget);
        await tester.tap(find.text(performance));
        await tester.pumpAndSettle();
        expect(repo.scopes, [const AiScope(AiScopeKind.portfolio, 'p-growth')]);
      },
    );

    testWidgets('forecast and goal scopes are labelled', (tester) async {
      await pumpAi(
        tester,
        scope: const AiScope(AiScopeKind.forecast, 'current'),
      );
      expect(find.text('Context: This forecast'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      await pumpAi(tester, scope: const AiScope(AiScopeKind.goal, 'g-home'));
      expect(find.text('Context: Goal g-home'), findsOneWidget);
    });

    testWidgets('the scope can be changed from the sheet', (tester) async {
      late ScopeRecorder repo;
      await pumpAi(tester, extra: [recordScopes((r) => repo = r)]);
      await tester.tap(find.text('Context: All portfolios'));
      await tester.pumpAndSettle();
      expect(find.text('Ask about'), findsOneWidget);
      await tester.tap(find.text('Retirement'));
      await tester.pumpAndSettle();
      expect(find.text('Context: Retirement'), findsOneWidget);
      await tester.tap(find.text(performance));
      await tester.pumpAndSettle();
      expect(
        repo.scopes.single,
        const AiScope(AiScopeKind.portfolio, 'p-retire'),
      );
    });

    testWidgets('the scope can be removed', (tester) async {
      late ScopeRecorder repo;
      await pumpAi(
        tester,
        scope: const AiScope(AiScopeKind.portfolio, 'p-income'),
        extra: [recordScopes((r) => repo = r)],
      );
      await tester.tap(find.byTooltip('Remove context'));
      await tester.pumpAndSettle();
      expect(find.text('Context: All portfolios'), findsOneWidget);
      await tester.tap(find.text(performance));
      await tester.pumpAndSettle();
      expect(repo.scopes.single, isNull);
    });

    testWidgets('the consolidated portfolio scope reads as all portfolios', (
      tester,
    ) async {
      await pumpAi(
        tester,
        scope: const AiScope(AiScopeKind.portfolio, 'consolidated'),
      );
      expect(find.text('Context: All portfolios'), findsOneWidget);
    });
  });

  group('offline', () {
    testWidgets('shows the offline banner and disables asking', (tester) async {
      await pumpAi(tester, extra: [onlineProvider.overrideWith(_Offline.new)]);
      expect(find.byType(OfflineBanner), findsOneWidget);
      expect(
        find.text("You're offline. Reconnect to ask a question."),
        findsOneWidget,
      );
      expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);
      for (final chip in tester.widgetList<ActionChip>(
        find.byType(ActionChip),
      )) {
        expect(chip.onPressed, isNull);
      }
    });

    testWidgets('going offline mid-conversation disables retry and composer', (
      tester,
    ) async {
      await pumpAi(tester);
      ProviderScope.containerOf(tester.element(find.byType(AiWealthScreen)))
          .read(demoBehaviorProvider.notifier)
          .set(DemoBehavior.instant.copyWith(failNextCalls: 1));
      await tester.tap(find.text(performance));
      await tester.pumpAndSettle();
      expect(
        find.text('Try again'),
        findsOneWidget,
        reason: 'retry exists while online',
      );
      final container = ProviderScope.containerOf(
        tester.element(find.byType(AiWealthScreen)),
      );
      container.read(onlineProvider.notifier).setOnline(online: false);
      await tester.pumpAndSettle();
      expect(find.text('Try again'), findsNothing);
      expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);
    });
  });

  group('accessibility and layout', () {
    testWidgets('the question bubble is announced as the user speaking', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpAi(tester);
      await tester.tap(find.text(performance));
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel('You: $performance'), findsOneWidget);
      handle.dispose();
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
        for (final scale in [1.0, 2.0]) {
          testWidgets(
            '320 wide, ${mode.name}, ${dir.name}, ${scale}x: no overflow with an answer and a refusal',
            (tester) async {
              await pumpAi(
                tester,
                size: const Size(320, 4000),
                mode: mode,
                dir: dir,
                textScale: scale,
                scope: const AiScope(AiScopeKind.portfolio, 'p-retire'),
              );
              expect(tester.takeException(), isNull);
              await tester.tap(find.text(performance));
              await tester.pumpAndSettle();
              await tester.enterText(
                find.byType(TextField),
                'Guarantee me a 20% return',
              );
              await tester.pump();
              await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
              await tester.pumpAndSettle();
              expect(tester.takeException(), isNull);
            },
          );
        }
      }
    }
  });

  test('no assistant text is written in Dart (it all comes from the repository or l10n)', () {
    final files = Directory('lib/features/ai_wealth')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'));
    // A string literal with three or more words would be hard-coded copy.
    final prose = RegExp(
      r"""(?<!import )['"][A-Za-z][^'"\n]*\s\w+\s\w+[^'"\n]*['"]""",
    );
    for (final f in files) {
      for (final line in f.readAsLinesSync()) {
        final code = line.trimLeft();
        if (code.startsWith('//') ||
            code.startsWith('///') ||
            code.startsWith('import ')) {
          continue;
        }
        expect(prose.hasMatch(code), isFalse, reason: '${f.path}: $code');
      }
    }
  });
}

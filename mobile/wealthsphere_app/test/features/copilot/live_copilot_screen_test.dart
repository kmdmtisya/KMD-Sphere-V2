import 'package:dio/dio.dart' show DioExceptionType;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/connectivity/connectivity.dart';
import 'package:wealthsphere_app/features/ai_wealth/presentation/ai_wealth_screen.dart';
import 'package:wealthsphere_app/features/copilot/data/copilot_repository.dart';
import 'package:wealthsphere_app/features/copilot/data/live_copilot_repository.dart';
import 'package:wealthsphere_app/features/portfolios/application/portfolio_providers.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/chat_frames.dart';
import '../../helpers/demo_overrides.dart';
import '../../helpers/fake_api.dart';
import '../../helpers/pump_app.dart';

const chat = 'POST /api/v1/ai/chat';
const list = 'GET /api/v1/ai/conversations';
const netWorth = 'What is my net worth?';

class _Offline extends ConnectivityNotifier {
  @override
  bool build() => false;
}

RawBody answerStream() => RawBody([
  frame('tool', {
    'type': 'tool',
    'name': 'get_net_worth',
    'status': 'running',
    'error_code': null,
  }),
  frame('source', {
    'type': 'source',
    'tool': 'get_net_worth',
    'as_of': '2026-10-12T09:00:00Z',
    'complete': true,
  }),
  frame('done', done(structured: answer())),
]);

Map<String, Object?> summary(String id, String title) => {
  'id': id,
  'title': title,
  'portfolio_id': null,
  'created_at': '2026-10-12T08:00:00Z',
  'updated_at': '2026-10-12T09:00:00Z',
};

Map<String, Object?> detail(String id, String title) => {
  ...summary(id, title),
  'messages': [
    {
      'id': 'm1',
      'position': 1,
      'role': 'user',
      'content': 'Earlier question',
      'structured': null,
      'model': null,
      'created_at': '2026-10-12T08:00:00Z',
    },
    {
      'id': 'm2',
      'position': 2,
      'role': 'assistant',
      'content': 'Observed ...',
      'structured': answer(),
      'model': 'fake-1',
      'created_at': '2026-10-12T08:00:01Z',
    },
  ],
  'tool_calls': <Object?>[],
};

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  late FakeApi api;

  setUp(() => api = FakeApi());

  Future<void> pumpLive(
    WidgetTester tester, {
    AiScope? scope,
    List<Override> extra = const [],
    double textScale = 1.0,
  }) => tester.pumpApp(
    AiWealthScreen(scope: scope),
    overrides: demoOverrides(
      extra: [
        liveModeOverride(),
        copilotRepositoryProvider.overrideWithValue(
          LiveCopilotRepository(api.dio()),
        ),
        portfolioListProvider.overrideWith(
          (ref) async => const [
            PortfolioRef(id: 'p1', name: 'Retirement', baseCurrency: 'USD'),
          ],
        ),
        ...extra,
      ],
    ),
    surfaceSize: const Size(400, 2400),
    textScale: textScale,
  );

  Future<void> ask(WidgetTester tester, String question) async {
    await tester.enterText(find.byType(TextField), question);
    await tester.pump(); // the send button follows the text
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
  }

  group('live empty state', () {
    testWidgets('own introduction and suggestions, no DEMO, history offered', (
      tester,
    ) async {
      await pumpLive(tester);
      expect(find.textContaining('Answers use your own data'), findsOneWidget);
      expect(find.text('DEMO'), findsNothing);
      expect(find.textContaining('Demo responses'), findsNothing);
      expect(find.byType(ActionChip), findsNWidgets(4));
      expect(find.text(netWorth), findsOneWidget);
      expect(find.byTooltip('Conversations'), findsOneWidget);
      expect(find.byTooltip('New conversation'), findsNothing);
    });
  });

  group('an answer', () {
    testWidgets('shows the sections, the server notice and named sources', (
      tester,
    ) async {
      api.on(chat, (_) => (200, answerStream()));
      await pumpLive(tester);
      await tester.tap(find.text(netWorth));
      await tester.pumpAndSettle();

      for (final h in [
        'Observed data',
        'Calculated',
        'Assumptions',
        'AI interpretation',
        'Please note',
      ]) {
        expect(find.text(h), findsOneWidget, reason: h);
      }
      expect(find.text('Your net worth was retrieved.'), findsOneWidget);
      expect(
        find.text('Forecasts are illustrations, not guaranteed returns.'),
        findsOneWidget,
      );
      // The chip names the data in words, not the tool id.
      expect(find.textContaining('Net worth'), findsWidgets);
      expect(find.textContaining('get_net_worth'), findsNothing);
      expect(find.byType(EvidenceSourceChip), findsOneWidget);
      expect(find.byType(DataAsOfLabel), findsOneWidget);
      expect(find.text('DEMO'), findsNothing);
      expect(find.byTooltip('New conversation'), findsOneWidget);
    });

    testWidgets('the next question continues the stored conversation', (
      tester,
    ) async {
      api.on(chat, (_) => (200, answerStream()));
      await pumpLive(tester);
      await ask(tester, 'First');
      await ask(tester, 'Second');
      final bodies = [for (final c in api.calls) c.body as Map];
      expect(bodies[0].containsKey('conversation_id'), isFalse);
      expect(bodies[1]['conversation_id'], 'c1');
    });

    testWidgets('the scope chip is sent and shows the portfolio name', (
      tester,
    ) async {
      api.on(chat, (_) => (200, answerStream()));
      await pumpLive(tester, scope: const AiScope(AiScopeKind.portfolio, 'p1'));
      expect(find.text('Context: Retirement'), findsOneWidget);
      await ask(tester, 'Hi');
      expect((api.calls.single.body! as Map)['scope'], {'portfolio_id': 'p1'});
    });

    testWidgets('a scope change starts a new conversation', (tester) async {
      api.on(chat, (_) => (200, answerStream()));
      await pumpLive(tester, scope: const AiScope(AiScopeKind.portfolio, 'p1'));
      await ask(tester, 'First');
      await tester.tap(find.byType(InputChip));
      await tester.pumpAndSettle();
      expect(find.textContaining('stays limited'), findsOneWidget);
      await tester.tap(find.text('All portfolios'));
      await tester.pumpAndSettle();
      await ask(tester, 'Second');
      final second = api.calls.last.body! as Map;
      expect(second.containsKey('conversation_id'), isFalse);
      expect(second.containsKey('scope'), isFalse);
    });

    testWidgets('a refusal looks different from an answer', (tester) async {
      api.on(
        chat,
        (_) => (
          200,
          RawBody([
            frame('token', {'type': 'token', 'text': 'I cannot place orders.'}),
            frame('done', done(structured: {'refusal': 'trade_execution'})),
          ]),
        ),
      );
      await pumpLive(tester);
      await ask(tester, 'Place an order for me');
      expect(find.byKey(const ValueKey('refusal')), findsOneWidget);
      expect(find.text('I cannot place orders.'), findsOneWidget);
      expect(find.text('Observed data'), findsNothing);
    });

    testWidgets('the server\'s own error text is shown with a retry', (
      tester,
    ) async {
      api.on(
        chat,
        (_) => (
          200,
          RawBody([
            frame('error', {
              'type': 'error',
              'code': 'invalid_answer',
              'message': 'The assistant could not produce a reliable answer.',
            }),
          ]),
        ),
      );
      await pumpLive(tester);
      await ask(tester, 'Hi');
      expect(
        find.text('The assistant could not produce a reliable answer.'),
        findsOneWidget,
      );
      api.on(chat, (_) => (200, answerStream()));
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.text('Observed data'), findsOneWidget);
      expect(find.text('Try again'), findsNothing);
    });

    for (final (status, text) in [
      (429, "You have reached today's limit of questions. Try again later."),
      (503, 'The assistant is unavailable right now. Try again shortly.'),
      (500, 'The assistant is unavailable right now. Try again shortly.'),
    ]) {
      testWidgets('HTTP $status says what happened', (tester) async {
        api.json(chat, {'title': 'x', 'status': status}, status: status);
        await pumpLive(tester);
        await ask(tester, 'Hi');
        expect(find.text(text), findsOneWidget);
        expect(find.textContaining('503'), findsNothing);
      });
    }

    testWidgets('a dropped connection shows the generic failure', (
      tester,
    ) async {
      api.on(chat, (_) => DioExceptionType.connectionError);
      await pumpLive(tester);
      await ask(tester, 'Hi');
      expect(
        find.text("The assistant couldn't answer. Try again."),
        findsOneWidget,
      );
    });

    testWidgets('offline, asking is disabled', (tester) async {
      await pumpLive(
        tester,
        extra: [onlineProvider.overrideWith(_Offline.new)],
      );
      expect(find.byType(OfflineBanner), findsOneWidget);
      expect(
        find.text("You're offline. Reconnect to ask a question."),
        findsOneWidget,
      );
    });
  });

  group('conversation history', () {
    testWidgets('lists conversations, opens one and continues it', (
      tester,
    ) async {
      api
        ..json(list, [summary('c1', 'Net worth'), summary('c2', 'Goals')])
        ..json('GET /api/v1/ai/conversations/c1', detail('c1', 'Net worth'))
        ..on(chat, (_) => (200, answerStream()));
      await pumpLive(tester);
      await tester.tap(find.byTooltip('Conversations'));
      await tester.pumpAndSettle();
      expect(find.text('Net worth'), findsOneWidget);
      expect(find.text('Goals'), findsOneWidget);
      expect(
        find.textContaining('Deleted after 90 days'),
        findsOneWidget,
        reason: 'the retention is stated',
      );

      await tester.tap(find.text('Net worth'));
      await tester.pumpAndSettle();
      expect(find.text('Earlier question'), findsOneWidget);
      expect(find.text('Your net worth was retrieved.'), findsOneWidget);

      await ask(tester, 'And now?');
      expect((api.calls.last.body! as Map)['conversation_id'], 'c1');
    });

    testWidgets('an empty list says so', (tester) async {
      api.json(list, <Object?>[]);
      await pumpLive(tester);
      await tester.tap(find.byTooltip('Conversations'));
      await tester.pumpAndSettle();
      expect(find.text('No saved conversations yet.'), findsOneWidget);
      expect(find.text('Delete all'), findsNothing);
    });

    testWidgets('a failed list can be retried', (tester) async {
      api.json(list, {'title': 'x', 'status': 503}, status: 503);
      await pumpLive(tester);
      await tester.tap(find.byTooltip('Conversations'));
      await tester.pumpAndSettle();
      expect(find.text('Try again'), findsOneWidget);
      api.json(list, [summary('c1', 'Net worth')]);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.text('Net worth'), findsOneWidget);
    });

    testWidgets('deleting one conversation removes it from the list', (
      tester,
    ) async {
      var remaining = [summary('c1', 'Net worth'), summary('c2', 'Goals')];
      api
        ..on(list, (_) => (200, remaining))
        ..on('DELETE /api/v1/ai/conversations/c1', (_) {
          remaining = [summary('c2', 'Goals')];
          return (204, null);
        });
      await pumpLive(tester);
      await tester.tap(find.byTooltip('Conversations'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Delete conversation').first);
      await tester.pumpAndSettle();
      expect(find.text('Net worth'), findsNothing);
      expect(find.text('Goals'), findsOneWidget);
    });

    testWidgets('deleting the open conversation clears the screen', (
      tester,
    ) async {
      api
        ..on(list, (_) => (200, [summary('c1', 'Net worth')]))
        ..json('GET /api/v1/ai/conversations/c1', detail('c1', 'Net worth'))
        ..json('DELETE /api/v1/ai/conversations/c1', null, status: 204);
      await pumpLive(tester);
      await tester.tap(find.byTooltip('Conversations'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Net worth'));
      await tester.pumpAndSettle();
      expect(find.text('Earlier question'), findsOneWidget);
      await tester.tap(find.byTooltip('Conversations'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Delete conversation'));
      await tester.pumpAndSettle();
      await tester.tapAt(const Offset(10, 10)); // close the sheet
      await tester.pumpAndSettle();
      expect(find.text('Earlier question'), findsNothing);
    });

    testWidgets('delete all asks first, then deletes', (tester) async {
      api
        ..on(list, (_) => (200, [summary('c1', 'Net worth')]))
        ..json('DELETE /api/v1/ai/conversations', null, status: 204);
      await pumpLive(tester);
      await tester.tap(find.byTooltip('Conversations'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete all'));
      await tester.pumpAndSettle();
      expect(find.text('Delete all conversations?'), findsOneWidget);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(api.callsTo('DELETE', '/api/v1/ai/conversations'), isEmpty);

      await tester.tap(find.text('Delete all'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.descendant(
          of: find.byType(AlertDialog),
          matching: find.text('Delete all'),
        ),
      );
      await tester.pumpAndSettle();
      expect(api.callsTo('DELETE', '/api/v1/ai/conversations'), hasLength(1));
    });

    testWidgets('a conversation that cannot be opened says so', (tester) async {
      api
        ..json(list, [summary('c1', 'Net worth')])
        ..json('GET /api/v1/ai/conversations/c1', {'status': 404}, status: 404);
      await pumpLive(tester);
      await tester.tap(find.byTooltip('Conversations'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Net worth'));
      await tester.pumpAndSettle();
      expect(
        find.text('The conversation could not be opened. Try again.'),
        findsOneWidget,
      );
    });

    testWidgets('demo mode offers no history', (tester) async {
      await tester.pumpApp(
        const AiWealthScreen(),
        overrides: demoOverrides(),
        surfaceSize: const Size(400, 2400),
      );
      expect(find.byTooltip('Conversations'), findsNothing);
      expect(find.text('DEMO'), findsWidgets);
    });
  });

  group('accessibility', () {
    testWidgets('an answer meets the guidelines at large text', (tester) async {
      final handle = tester.ensureSemantics();
      api.on(chat, (_) => (200, answerStream()));
      await pumpLive(tester, textScale: 2.0);
      await ask(tester, 'Hi');
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      handle.dispose();
    });
  });
}

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';
import 'package:wealthsphere_app/features/copilot/data/live_copilot_repository.dart';
import 'package:wealthsphere_app/features/copilot/domain/chat_models.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../helpers/chat_frames.dart';
import '../../helpers/fake_api.dart';

const chat = 'POST /api/v1/ai/chat';

void main() {
  late FakeApi api;
  late LiveCopilotRepository repo;

  setUp(() {
    api = FakeApi();
    repo = LiveCopilotRepository(api.dio());
  });

  Future<List<ChatEvent>> ask(
    String question, {
    AiScope? scope,
    String? conversationId,
  }) =>
      repo.ask(question, scope: scope, conversationId: conversationId).toList();

  group('the answer stream', () {
    test(
      'tools, sources, then the four sections and the notice, then done',
      () async {
        api.on(
          chat,
          (_) => (
            200,
            RawBody([
              frame('tool', {
                'type': 'tool',
                'name': 'get_net_worth',
                'status': 'running',
                'error_code': null,
              }),
              frame('tool', {
                'type': 'tool',
                'name': 'get_net_worth',
                'status': 'ok',
                'error_code': null,
              }),
              frame('source', {
                'type': 'source',
                'tool': 'get_net_worth',
                'as_of': '2026-10-12T09:00:00Z',
                'complete': true,
              }),
              frame('token', {'type': 'token', 'text': 'Observed - ignored'}),
              frame('done', done(structured: answer())),
            ]),
          ),
        );
        final events = await ask('What is my net worth?');

        expect(events[0], isA<ToolProgressEvent>());
        expect((events[0] as ToolProgressEvent).tool, 'get_net_worth');
        final source = (events[1] as SourceEvent).source;
        expect(source.label, 'get_net_worth');
        expect(source.provider, 'WealthSphere');
        expect(source.asOf, DateTime.utc(2026, 10, 12, 9));
        final sections = events.whereType<SectionEvent>().map((e) => e.section);
        expect(
          [for (final s in sections) (s.kind, s.text)],
          [
            (SectionKind.observed, 'Your net worth was retrieved.'),
            (SectionKind.calculated, 'Assets minus liabilities.'),
            (SectionKind.assumption, 'Values are in USD.'),
            (SectionKind.interpretation, 'A snapshot, not a guarantee.'),
            (
              SectionKind.notice,
              'Forecasts are illustrations, not guaranteed returns.',
            ),
          ],
        );
        expect((events.last as DoneEvent).conversationId, 'c1');
        expect(events, hasLength(8), reason: 'a finished tool adds no event');
      },
    );

    test('a refusal is a refusal event carrying the server text', () async {
      api.on(
        chat,
        (_) => (
          200,
          RawBody([
            frame('token', {'type': 'token', 'text': 'I cannot place orders '}),
            frame('token', {'type': 'token', 'text': 'or move money.'}),
            frame('done', done(structured: {'refusal': 'trade_execution'})),
          ]),
        ),
      );
      final events = await ask('Place a buy order');
      expect(events.first, isA<RefusalEvent>());
      expect(
        (events.first as RefusalEvent).text,
        'I cannot place orders or move money.',
      );
      expect(events.last, isA<DoneEvent>());
      expect(events.whereType<SectionEvent>(), isEmpty);
    });

    test('an error event carries the fixed server message', () async {
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
      final events = await ask('Hi');
      expect(events.single, isA<ErrorEvent>());
      expect(
        (events.single as ErrorEvent).text,
        'The assistant could not produce a reliable answer.',
      );
    });

    test('a done without sections falls back to the streamed text', () async {
      api.on(
        chat,
        (_) => (
          200,
          RawBody([
            frame('token', {'type': 'token', 'text': 'Plain words.'}),
            frame('done', done()),
          ]),
        ),
      );
      final events = await ask('Hi');
      expect(
        (events.first as SectionEvent).section.kind,
        SectionKind.interpretation,
      );
      expect((events.first as SectionEvent).section.text, 'Plain words.');
    });

    test('frames split across chunks and unknown events are handled', () async {
      final text =
          frame('source', {
            'type': 'source',
            'tool': 'get_net_worth',
            'as_of': '2026-10-12T09:00:00Z',
            'complete': true,
          }) +
          frame('future_event', {'type': 'future_event'}) +
          frame('done', done(structured: answer()));
      api.on(
        chat,
        (_) => (
          200,
          RawBody([
            for (var i = 0; i < text.length; i += 7)
              text.substring(i, i + 7 > text.length ? text.length : i + 7),
          ]),
        ),
      );
      final events = await ask('Hi');
      expect(events.first, isA<SourceEvent>());
      expect(events.last, isA<DoneEvent>());
    });

    test('a source without a time is not shown as evidence', () async {
      api.on(
        chat,
        (_) => (
          200,
          RawBody([
            frame('source', {
              'type': 'source',
              'tool': 'get_net_worth',
              'as_of': null,
            }),
            frame('done', done(structured: answer())),
          ]),
        ),
      );
      expect((await ask('Hi')).whereType<SourceEvent>(), isEmpty);
    });

    test(
      'a stream that ends early fails instead of looking complete',
      () async {
        api.on(
          chat,
          (_) => (
            200,
            RawBody([
              frame('tool', {
                'type': 'tool',
                'name': 'get_net_worth',
                'status': 'running',
                'error_code': null,
              }),
            ]),
          ),
        );
        await expectLater(
          repo.ask('Hi').toList(),
          throwsA(
            isA<ApiException>().having(
              (e) => e.kind,
              'kind',
              ApiErrorKind.network,
            ),
          ),
        );
      },
    );

    test(
      'a malformed event is an invalid response, never wrong text',
      () async {
        api.on(
          chat,
          (_) => (
            200,
            RawBody([
              frame('done', {'type': 'done'}),
            ]),
          ),
        );
        await expectLater(
          repo.ask('Hi').toList(),
          throwsA(
            isA<ApiException>().having(
              (e) => e.kind,
              'kind',
              ApiErrorKind.invalidResponse,
            ),
          ),
        );
      },
    );
  });

  group('the request', () {
    setUp(() {
      api.on(
        chat,
        (_) => (200, RawBody([frame('done', done(structured: answer()))])),
      );
    });

    test(
      'sends the question, asks for an event stream and never a user id',
      () async {
        await ask('What is my net worth?');
        final call = api.callsTo('POST', '/api/v1/ai/chat').single;
        expect(call.body, {'message': 'What is my net worth?'});
        expect(call.header('accept'), 'text/event-stream');
        expect(
          call.header('x-correlation-id'),
          isNull,
        ); // added by the real client
      },
    );

    test('a portfolio scope and a conversation id are sent', () async {
      await ask(
        'Hi',
        scope: const AiScope(AiScopeKind.portfolio, 'p1'),
        conversationId: 'c9',
      );
      expect(api.calls.single.body, {
        'message': 'Hi',
        'conversation_id': 'c9',
        'scope': {'portfolio_id': 'p1'},
      });
    });

    test('the consolidated view, a forecast or a goal narrow nothing on the server', () async {
      for (final scope in [
        const AiScope(AiScopeKind.portfolio, PortfolioRef.consolidatedId),
        const AiScope(AiScopeKind.forecast, 'f1'),
        const AiScope(AiScopeKind.goal, 'g1'),
      ]) {
        api.calls.clear();
        await ask('Hi', scope: scope);
        expect(
          (api.calls.single.body! as Map).containsKey('scope'),
          isFalse,
          reason: '$scope',
        );
      }
    });
  });

  group('failures before the stream', () {
    for (final (status, kind) in [
      (429, ApiErrorKind.rateLimited),
      (503, ApiErrorKind.server),
      (404, ApiErrorKind.notFound),
      (422, ApiErrorKind.validation),
      (401, ApiErrorKind.unauthenticated),
    ]) {
      test('HTTP $status is $kind', () async {
        api.json(chat, {'title': 'Nope', 'status': status}, status: status);
        await expectLater(
          repo.ask('Hi').toList(),
          throwsA(isA<ApiException>().having((e) => e.kind, 'kind', kind)),
        );
      });
    }

    test('a dropped connection is a network failure', () async {
      api.on(chat, (_) => DioExceptionType.connectionError);
      await expectLater(
        repo.ask('Hi').toList(),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.network,
          ),
        ),
      );
    });
  });

  group('stored conversations', () {
    Map<String, Object?> summary(String id, {String? portfolio}) => {
      'id': id,
      'title': 'Net worth',
      'portfolio_id': portfolio,
      'created_at': '2026-10-12T08:00:00Z',
      'updated_at': '2026-10-12T09:00:00Z',
    };

    test('lists, reads and deletes', () async {
      api
        ..json('GET /api/v1/ai/conversations', [summary('c1'), summary('c2')])
        ..json('GET /api/v1/ai/conversations/c1', {
          ...summary('c1', portfolio: 'p1'),
          'messages': [
            {
              'id': 'm1',
              'position': 1,
              'role': 'user',
              'content': 'What is my net worth?',
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
            {
              'id': 'm3',
              'position': 3,
              'role': 'user',
              'content': 'Place an order',
              'structured': null,
              'model': null,
              'created_at': '2026-10-12T08:01:00Z',
            },
            {
              'id': 'm4',
              'position': 4,
              'role': 'assistant',
              'content': 'I cannot place orders.',
              'structured': {'refusal': 'trade_execution'},
              'model': null,
              'created_at': '2026-10-12T08:01:01Z',
            },
            {
              'id': 'm5',
              'position': 5,
              'role': 'user',
              'content': 'And then?',
              'structured': null,
              'model': null,
              'created_at': '2026-10-12T08:02:00Z',
            },
          ],
          'tool_calls': <Object?>[],
        })
        ..json('DELETE /api/v1/ai/conversations/c1', null, status: 204)
        ..json('DELETE /api/v1/ai/conversations', null, status: 204);

      final list = await repo.conversations();
      expect([for (final c in list) c.id], ['c1', 'c2']);
      expect(list.first.title, 'Net worth');
      expect(list.first.updatedAt, DateTime.utc(2026, 10, 12, 9));

      final turns = (await repo.conversation('c1')).toTurns();
      expect(turns, hasLength(3));
      expect(turns[0].question, 'What is my net worth?');
      expect(turns[0].sections, hasLength(5));
      expect(turns[0].done, isTrue);
      expect(turns[1].refusal, 'I cannot place orders.');
      expect(turns[2].question, 'And then?');
      expect(
        turns[2].sections,
        isEmpty,
        reason: 'an unanswered question is kept',
      );

      await repo.deleteConversation('c1');
      await repo.deleteAllConversations();
      expect(
        api.callsTo('DELETE', '/api/v1/ai/conversations/c1'),
        hasLength(1),
      );
      expect(api.callsTo('DELETE', '/api/v1/ai/conversations'), hasLength(1));
    });

    test('another user\'s conversation is just not found', () async {
      api.json('GET /api/v1/ai/conversations/c9', {
        'title': 'Not Found',
        'status': 404,
      }, status: 404);
      await expectLater(
        repo.conversation('c9'),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.notFound,
          ),
        ),
      );
    });
  });

  test('live mode brings its own introduction and suggestions', () async {
    expect(repo.supportsHistory, isTrue);
    expect(await repo.suggestedQuestions(), isEmpty);
    expect((await repo.intro()).intro, isEmpty);
  });
}

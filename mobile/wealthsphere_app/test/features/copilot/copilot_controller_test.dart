import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';
import 'package:wealthsphere_app/features/ai_wealth/application/copilot_controller.dart';
import 'package:wealthsphere_app/features/copilot/data/copilot_repository.dart';
import 'package:wealthsphere_app/features/copilot/domain/chat_models.dart';
import 'package:wealthsphere_app/features/copilot/domain/conversation_models.dart';

/// Answers each question from a queue and remembers what it was asked.
class ScriptedCopilot implements CopilotRepository {
  final List<({String question, AiScope? scope, String? conversationId})>
  asked = [];
  final List<Stream<ChatEvent> Function()> script = [];

  @override
  Stream<ChatEvent> ask(
    String question, {
    AiScope? scope,
    String? conversationId,
  }) {
    asked.add((
      question: question,
      scope: scope,
      conversationId: conversationId,
    ));
    return script.removeAt(0)();
  }

  @override
  bool get supportsHistory => true;
  @override
  Future<List<ConversationSummary>> conversations() async => const [];
  @override
  Future<ConversationDetail> conversation(String id) =>
      throw UnimplementedError();
  @override
  Future<void> deleteConversation(String id) async {}
  @override
  Future<void> deleteAllConversations() async {}
  @override
  Future<List<String>> suggestedQuestions() async => const [];
  @override
  Future<CopilotIntro> intro() async =>
      const CopilotIntro(intro: '', notice: '');
}

Stream<ChatEvent> answered(String conversation, {String text = 'Fine.'}) =>
    Stream.fromIterable([
      const ToolProgressEvent('', tool: 'get_net_worth'),
      SectionEvent(AnswerSection(kind: SectionKind.interpretation, text: text)),
      DoneEvent(conversationId: conversation),
    ]);

const portfolio = AiScope(AiScopeKind.portfolio, 'p1');
const other = AiScope(AiScopeKind.portfolio, 'p2');

void main() {
  late ScriptedCopilot repo;
  late ProviderContainer container;
  late CopilotController controller;

  CopilotState state() => container.read(copilotControllerProvider);

  setUp(() {
    repo = ScriptedCopilot();
    container = ProviderContainer(
      overrides: [copilotRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);
    controller = container.read(copilotControllerProvider.notifier);
  });

  Future<void> settle() => Future<void>.delayed(Duration.zero);

  void ask(String q, {AiScope? scope}) => controller.ask(
    q,
    scope: scope,
    failureMessage: 'generic',
    rateLimitedMessage: 'limit',
    unavailableMessage: 'down',
  );

  group('conversations', () {
    test(
      'the next question continues the conversation the server created',
      () async {
        repo.script.addAll([() => answered('c1'), () => answered('c1')]);
        ask('First', scope: portfolio);
        await settle();
        expect(state().conversationId, 'c1');
        ask('Second', scope: portfolio);
        await settle();
        expect(repo.asked.map((a) => a.conversationId), [null, 'c1']);
        expect(state().turns, hasLength(2));
      },
    );

    test('a different scope starts a new conversation (the server fixes the scope)', () async {
      repo.script.addAll([() => answered('c1'), () => answered('c2')]);
      ask('First', scope: portfolio);
      await settle();
      ask('Second', scope: other);
      await settle();
      expect(repo.asked.last.conversationId, isNull);
      expect(state().conversationId, 'c2');
      expect(state().conversationScope, other);
    });

    test('removing the scope also starts a new conversation', () async {
      repo.script.addAll([() => answered('c1'), () => answered('c2')]);
      ask('First', scope: portfolio);
      await settle();
      ask('Second');
      await settle();
      expect(repo.asked.last.conversationId, isNull);
    });

    test('opening a stored conversation shows it and continues it', () async {
      controller.open(
        conversationId: 'c7',
        scope: portfolio,
        turns: [ChatTurn(question: 'Old', done: true)],
      );
      expect(state().turns.single.question, 'Old');
      repo.script.add(() => answered('c7'));
      ask('New', scope: portfolio);
      await settle();
      expect(repo.asked.single.conversationId, 'c7');
    });

    test(
      'clearing and forgetting a deleted conversation start fresh',
      () async {
        controller.open(
          conversationId: 'c7',
          turns: [ChatTurn(question: 'Old', done: true)],
        );
        controller.forget(
          'c8',
        ); // another conversation was deleted: nothing changes
        expect(state().turns, isNotEmpty);
        controller.forget('c7');
        expect(state().turns, isEmpty);
        expect(state().conversationId, isNull);
        controller.open(conversationId: 'c9', turns: const []);
        controller.clear();
        expect(state().conversationId, isNull);
      },
    );
  });

  group('failures', () {
    Stream<ChatEvent> failing(Object error) => Stream<ChatEvent>.error(error);

    for (final (error, message) in <(Object, String)>[
      (const ApiException(ApiErrorKind.rateLimited), 'limit'),
      (const ApiException(ApiErrorKind.server), 'down'),
      (const ApiException(ApiErrorKind.network), 'generic'),
      (const ApiException(ApiErrorKind.validation), 'generic'),
      (StateError('boom'), 'generic'),
    ]) {
      test('$error shows "$message", never the raw error', () async {
        repo.script.add(() => failing(error));
        ask('Hi');
        await settle();
        expect(state().turns.single.error, message);
        expect(state().streaming, isFalse);
      });
    }

    test('a failed question can be asked again in place', () async {
      repo.script.addAll([
        () => failing(const ApiException(ApiErrorKind.server)),
        () => answered('c1', text: 'Now it works.'),
      ]);
      ask('Hi');
      await settle();
      controller.retry(0, failureMessage: 'generic');
      await settle();
      expect(state().turns, hasLength(1));
      expect(state().turns.single.error, isNull);
      expect(state().turns.single.sections.single.text, 'Now it works.');
    });

    test('an error event ends the turn with the server message', () async {
      repo.script.add(
        () => Stream.fromIterable([const ErrorEvent('Not reliable.')]),
      );
      ask('Hi');
      await settle();
      expect(state().turns.single.error, 'Not reliable.');
      expect(state().streaming, isFalse);
    });

    test('a refusal ends the turn as a refusal', () async {
      repo.script.add(
        () => Stream.fromIterable(const [
          RefusalEvent('I cannot do that.', conversationId: 'c1'),
          DoneEvent(conversationId: 'c1'),
        ]),
      );
      ask('Hi');
      await settle();
      expect(state().turns.single.refusal, 'I cannot do that.');
      expect(state().conversationId, 'c1');
    });
  });

  test('only one answer streams at a time, and it can be stopped', () async {
    final hold = StreamController<ChatEvent>();
    repo.script.add(() => hold.stream);
    ask('First');
    ask('Second'); // ignored while streaming
    expect(state().turns, hasLength(1));
    expect(state().streaming, isTrue);
    controller.stop();
    expect(state().streaming, isFalse);
    expect(state().turns.single.stopped, isTrue);
    await hold.close();
  });
}

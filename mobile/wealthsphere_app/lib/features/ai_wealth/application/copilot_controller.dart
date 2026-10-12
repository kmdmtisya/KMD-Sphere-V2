import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/app_routes.dart';
import '../../../core/network/api_exception.dart';
import '../../copilot/data/copilot_repository.dart';
import '../../copilot/domain/chat_models.dart';

/// The conversation on screen. Live conversations are stored on the server (the repository's
/// history); this holds what is being shown and which stored conversation the next question
/// continues.
@immutable
class CopilotState {
  CopilotState({
    List<ChatTurn> turns = const [],
    this.streaming = false,
    this.conversationId,
    this.conversationScope,
  }) : turns = List.unmodifiable(turns);

  final List<ChatTurn> turns;
  final bool streaming;

  /// The stored conversation the next question continues (live only); null starts a new one.
  final String? conversationId;

  /// The scope that stored conversation was started with. The server fixes it for the life of
  /// the conversation, so asking with another scope starts a new conversation.
  final AiScope? conversationScope;

  CopilotState copyWith({
    List<ChatTurn>? turns,
    bool? streaming,
    String? conversationId,
    AiScope? conversationScope,
    bool forgetConversation = false,
  }) => CopilotState(
    turns: turns ?? this.turns,
    streaming: streaming ?? this.streaming,
    conversationId: forgetConversation
        ? null
        : conversationId ?? this.conversationId,
    conversationScope: forgetConversation
        ? null
        : conversationScope ?? this.conversationScope,
  );
}

/// The words shown when a question fails; the raw error is never shown.
@immutable
class AiFailureTexts {
  const AiFailureTexts({
    required this.generic,
    String? rateLimited,
    String? unavailable,
  }) : rateLimited = rateLimited ?? generic,
       unavailable = unavailable ?? generic;

  final String generic;

  /// The daily question limit was reached (HTTP 429).
  final String rateLimited;

  /// The assistant is not available (HTTP 5xx).
  final String unavailable;

  String of(Object error) {
    if (error is ApiException) {
      return switch (error.kind) {
        ApiErrorKind.rateLimited => rateLimited,
        ApiErrorKind.server => unavailable,
        _ => generic,
      };
    }
    return generic;
  }
}

/// Sends questions to the [CopilotRepository] and folds the streamed events into turns.
class CopilotController extends Notifier<CopilotState> {
  StreamSubscription<ChatEvent>? _subscription;

  @override
  CopilotState build() {
    ref.onDispose(() => _subscription?.cancel());
    return CopilotState();
  }

  /// Asks [question] with the given [scope]. Ignored while another answer is streaming.
  void ask(
    String question, {
    AiScope? scope,
    required String failureMessage,
    String? rateLimitedMessage,
    String? unavailableMessage,
  }) {
    if (state.streaming) return;
    final index = state.turns.length;
    state = state.copyWith(
      turns: [
        ...state.turns,
        ChatTurn(question: question),
      ],
      streaming: true,
    );
    _listen(
      index,
      question,
      scope,
      AiFailureTexts(
        generic: failureMessage,
        rateLimited: rateLimitedMessage,
        unavailable: unavailableMessage,
      ),
    );
  }

  /// Asks the question of the turn at [index] again, replacing that turn.
  void retry(
    int index, {
    AiScope? scope,
    required String failureMessage,
    String? rateLimitedMessage,
    String? unavailableMessage,
  }) {
    if (state.streaming || index < 0 || index >= state.turns.length) return;
    final question = state.turns[index].question;
    final turns = [...state.turns]..[index] = ChatTurn(question: question);
    state = state.copyWith(turns: turns, streaming: true);
    _listen(
      index,
      question,
      scope,
      AiFailureTexts(
        generic: failureMessage,
        rateLimited: rateLimitedMessage,
        unavailable: unavailableMessage,
      ),
    );
  }

  /// Stops the answer being streamed; what has arrived is kept and marked as stopped.
  void stop() {
    if (!state.streaming) return;
    unawaited(_subscription?.cancel());
    _subscription = null;
    final turns = [...state.turns];
    turns[turns.length - 1] = turns.last.stop();
    state = state.copyWith(turns: turns, streaming: false);
  }

  void _listen(
    int index,
    String question,
    AiScope? scope,
    AiFailureTexts failures,
  ) {
    void update(ChatTurn Function(ChatTurn) change, {bool? streaming}) {
      if (index >= state.turns.length) return;
      final turns = [...state.turns]..[index] = change(state.turns[index]);
      state = state.copyWith(turns: turns, streaming: streaming);
    }

    // The server fixes a conversation's scope; a different scope is a new conversation.
    final continuing =
        state.conversationId != null && state.conversationScope == scope;
    if (!continuing && state.conversationId != null) {
      state = state.copyWith(forgetConversation: true);
    }

    _subscription = ref
        .read(copilotRepositoryProvider)
        .ask(
          question,
          scope: scope,
          conversationId: continuing ? state.conversationId : null,
        )
        .listen(
          (event) {
            final stored = switch (event) {
              DoneEvent(:final conversationId) => conversationId,
              RefusalEvent(:final conversationId) => conversationId,
              _ => null,
            };
            if (stored != null) {
              state = state.copyWith(
                conversationId: stored,
                conversationScope: scope,
              );
            }
            update((t) => t.apply(event));
            if (state.turns[index].done) {
              _subscription?.cancel();
              _subscription = null;
              update((t) => t, streaming: false);
            }
          },
          onError: (Object error) {
            _subscription = null;
            update((t) => t.fail(failures.of(error)), streaming: false);
          },
          onDone: () {
            _subscription = null;
            // A stream that ends without `done` is complete as far as it went.
            if (state.streaming) {
              update(
                (t) => t.done ? t : t.apply(const DoneEvent()),
                streaming: false,
              );
            }
          },
        );
  }

  /// Shows a stored conversation and continues it with the next question.
  void open({
    required String conversationId,
    required List<ChatTurn> turns,
    AiScope? scope,
  }) {
    unawaited(_subscription?.cancel());
    _subscription = null;
    state = CopilotState(
      turns: turns,
      conversationId: conversationId,
      conversationScope: scope,
    );
  }

  /// Starts a new, empty conversation.
  void clear() {
    unawaited(_subscription?.cancel());
    _subscription = null;
    state = CopilotState();
  }

  /// Forgets the stored conversation the screen is showing (it was deleted).
  void forget(String conversationId) {
    if (state.conversationId == conversationId) clear();
  }
}

final copilotControllerProvider =
    NotifierProvider<CopilotController, CopilotState>(CopilotController.new);

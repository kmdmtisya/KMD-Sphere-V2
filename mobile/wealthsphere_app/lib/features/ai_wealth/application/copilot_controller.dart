import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/app_routes.dart';
import '../../copilot/data/copilot_repository.dart';
import '../../copilot/domain/chat_models.dart';

/// The conversation, held in memory only: financial chat is not stored on the device in this
/// phase.
@immutable
class CopilotState {
  CopilotState({List<ChatTurn> turns = const [], this.streaming = false})
    : turns = List.unmodifiable(turns);

  final List<ChatTurn> turns;
  final bool streaming;

  CopilotState copyWith({List<ChatTurn>? turns, bool? streaming}) =>
      CopilotState(
        turns: turns ?? this.turns,
        streaming: streaming ?? this.streaming,
      );
}

/// Sends questions to the [CopilotRepository] and folds the streamed events into turns.
///
/// [failureMessage] is the user-facing text used when the stream itself fails (a transport
/// error); the raw error is never shown.
class CopilotController extends Notifier<CopilotState> {
  StreamSubscription<ChatEvent>? _subscription;

  @override
  CopilotState build() {
    ref.onDispose(() => _subscription?.cancel());
    return CopilotState();
  }

  /// Asks [question] with the given [scope]. Ignored while another answer is streaming.
  void ask(String question, {AiScope? scope, required String failureMessage}) {
    if (state.streaming) return;
    final index = state.turns.length;
    state = state.copyWith(
      turns: [
        ...state.turns,
        ChatTurn(question: question),
      ],
      streaming: true,
    );
    _listen(index, question, scope, failureMessage);
  }

  /// Asks the question of the turn at [index] again, replacing that turn.
  void retry(int index, {AiScope? scope, required String failureMessage}) {
    if (state.streaming || index < 0 || index >= state.turns.length) return;
    final question = state.turns[index].question;
    final turns = [...state.turns]..[index] = ChatTurn(question: question);
    state = state.copyWith(turns: turns, streaming: true);
    _listen(index, question, scope, failureMessage);
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
    String failureMessage,
  ) {
    void update(ChatTurn Function(ChatTurn) change, {bool? streaming}) {
      if (index >= state.turns.length) return;
      final turns = [...state.turns]..[index] = change(state.turns[index]);
      state = state.copyWith(turns: turns, streaming: streaming);
    }

    _subscription = ref
        .read(copilotRepositoryProvider)
        .ask(question, scope: scope)
        .listen(
          (event) {
            update((t) => t.apply(event));
            if (state.turns[index].done) {
              _subscription?.cancel();
              _subscription = null;
              update((t) => t, streaming: false);
            }
          },
          onError: (Object _) {
            _subscription = null;
            update((t) => t.fail(failureMessage), streaming: false);
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

  /// Starts a new, empty conversation.
  void clear() {
    unawaited(_subscription?.cancel());
    _subscription = null;
    state = CopilotState();
  }
}

final copilotControllerProvider =
    NotifierProvider<CopilotController, CopilotState>(CopilotController.new);

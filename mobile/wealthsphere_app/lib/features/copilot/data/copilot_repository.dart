import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/app_routes.dart';
import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../domain/chat_models.dart';

/// The AI Wealth Copilot. Answers are streamed as typed events.
abstract interface class CopilotRepository {
  /// Questions offered as chips on the empty state.
  Future<List<String>> suggestedQuestions();

  /// The intro and the "demo responses" notice shown above the conversation.
  Future<CopilotIntro> intro();

  /// Streams the answer to [question]. [scope] is the portfolio, forecast or goal the chat was
  /// opened for, if any (already validated by [AiScope.tryParse]).
  Stream<ChatEvent> ask(String question, {AiScope? scope});
}

class CopilotIntro {
  const CopilotIntro({required this.intro, required this.notice});

  final String intro;
  final String notice;
}

/// Plays the scripted conversations in `assets/demo/copilot.json`. No advice is written in Dart:
/// every word the assistant "says" comes from the fixture. Questions without a script get the
/// fixture's "demo mode can answer the suggested questions only" reply.
class DemoCopilotRepository implements CopilotRepository {
  DemoCopilotRepository(this._assets, this._behavior, this._gate);

  final DemoAssets _assets;
  final DemoBehavior Function() _behavior;
  final Future<void> Function() _gate;

  Future<JsonReader> _doc() async =>
      JsonReader(await _assets.load('copilot.json'));

  @override
  Future<List<String>> suggestedQuestions() async {
    return (await _doc()).strings('suggested');
  }

  @override
  Future<CopilotIntro> intro() async {
    final doc = await _doc();
    return CopilotIntro(
      intro: doc.string('intro'),
      notice: doc.string('notice'),
    );
  }

  @override
  Stream<ChatEvent> ask(String question, {AiScope? scope}) async* {
    // Same gate as every repository call: waits for the configured latency and honours failure
    // injection. A failure before the first event surfaces as a stream error, like a network error.
    await _gate();
    final doc = await _doc();
    final scripts = doc.list('scripts', (r) => r);
    final normalized = question.trim().toLowerCase();
    JsonReader? match;
    for (final s in scripts) {
      if (s.string('question').toLowerCase() == normalized) {
        match = s;
        break;
      }
    }

    final events = match == null
        ? [
            ChatEvent.fromJson(
              JsonReader({
                'type': 'section',
                'kind': 'interpretation',
                'text': doc.string('unsupported_reply'),
              }),
            ),
            const DoneEvent(),
          ]
        : match.list('events', ChatEvent.fromJson);

    final interval = _behavior().streamInterval;
    for (final event in events) {
      if (interval > Duration.zero) await Future<void>.delayed(interval);
      yield event;
    }
  }
}

final copilotRepositoryProvider = Provider<CopilotRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      final behavior = ref.read(demoBehaviorProvider.notifier);
      return DemoCopilotRepository(
        ref.watch(demoAssetsProvider),
        () => ref.read(demoBehaviorProvider),
        behavior.gate,
      );
  }
});

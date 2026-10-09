import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';
import '../../../shared/domain/wealth_models.dart';

/// The four kinds of statement an AI answer is made of. Keeping them apart is a product rule:
/// facts, calculations, assumptions and AI interpretation must never be blended.
enum SectionKind {
  observed,
  calculated,
  assumption,
  interpretation;

  static SectionKind parse(String text, String path) => switch (text) {
    'observed' => observed,
    'calculated' => calculated,
    'assumption' => assumption,
    'interpretation' => interpretation,
    _ => throw FormatException('Unknown answer section kind "$text" at $path'),
  };
}

@immutable
class AnswerSection {
  const AnswerSection({required this.kind, required this.text});

  final SectionKind kind;
  final String text;
}

/// One event of a streamed chat answer (server-sent events: tool, section, source, refusal, done,
/// error). `section` and `refusal` extend the base event set in docs/api-conventions.md and are
/// confirmed in P10.
sealed class ChatEvent {
  const ChatEvent();

  factory ChatEvent.fromJson(JsonReader r) => switch (r.string('type')) {
    'tool' => ToolProgressEvent(r.string('text')),
    'section' => SectionEvent(
      AnswerSection(
        kind: SectionKind.parse(r.string('kind'), r.path),
        text: r.string('text'),
      ),
    ),
    'source' => SourceEvent(
      EvidenceSourceDto(
        label: r.string('label'),
        provider: r.string('provider'),
        asOf: r.timestamp('as_of'),
      ),
    ),
    'refusal' => RefusalEvent(r.string('text')),
    'done' => const DoneEvent(),
    'error' => ErrorEvent(r.string('text')),
    final other => throw FormatException(
      'Unknown chat event type "$other" at ${r.path}.type',
    ),
  };
}

/// "Fetching portfolio summary…" style progress while the assistant works.
class ToolProgressEvent extends ChatEvent {
  const ToolProgressEvent(this.text);
  final String text;
}

class SectionEvent extends ChatEvent {
  const SectionEvent(this.section);
  final AnswerSection section;
}

class SourceEvent extends ChatEvent {
  const SourceEvent(this.source);
  final EvidenceSourceDto source;
}

/// The assistant declined (for example a request for a guaranteed return).
class RefusalEvent extends ChatEvent {
  const RefusalEvent(this.text);
  final String text;
}

class DoneEvent extends ChatEvent {
  const DoneEvent();
}

class ErrorEvent extends ChatEvent {
  const ErrorEvent(this.text);
  final String text;
}

/// A finished or in-progress turn of the conversation, as the UI assembles it from events.
@immutable
class ChatTurn {
  ChatTurn({
    required this.question,
    List<ToolProgressEvent> progress = const [],
    List<AnswerSection> sections = const [],
    List<EvidenceSourceDto> sources = const [],
    this.refusal,
    this.error,
    this.done = false,
    this.stopped = false,
  }) : progress = List.unmodifiable(progress),
       sections = List.unmodifiable(sections),
       sources = List.unmodifiable(sources);

  final String question;
  final List<ToolProgressEvent> progress;
  final List<AnswerSection> sections;
  final List<EvidenceSourceDto> sources;
  final String? refusal;
  final String? error;
  final bool done;

  /// The user stopped the answer before it finished.
  final bool stopped;

  bool get failed => error != null;
  bool get refused => refusal != null;

  /// A copy with [event] applied. Pure, so a stream can be folded into a turn.
  ChatTurn apply(ChatEvent event) => switch (event) {
    ToolProgressEvent() => _copy(progress: [...progress, event]),
    SectionEvent(:final section) => _copy(sections: [...sections, section]),
    SourceEvent(:final source) => _copy(sources: [...sources, source]),
    RefusalEvent(:final text) => _copy(refusal: text, done: true),
    ErrorEvent(:final text) => _copy(error: text, done: true),
    DoneEvent() => _copy(done: true),
  };

  /// A copy marked as stopped by the user (whatever arrived so far is kept).
  ChatTurn stop() => _copy(done: true, stopped: true);

  /// A copy marked as failed with [message] (a transport error, not an assistant answer).
  ChatTurn fail(String message) => _copy(error: message, done: true);

  ChatTurn _copy({
    List<ToolProgressEvent>? progress,
    List<AnswerSection>? sections,
    List<EvidenceSourceDto>? sources,
    String? refusal,
    String? error,
    bool? done,
    bool? stopped,
  }) => ChatTurn(
    question: question,
    progress: progress ?? this.progress,
    sections: sections ?? this.sections,
    sources: sources ?? this.sources,
    refusal: refusal ?? this.refusal,
    error: error ?? this.error,
    done: done ?? this.done,
    stopped: stopped ?? this.stopped,
  );
}

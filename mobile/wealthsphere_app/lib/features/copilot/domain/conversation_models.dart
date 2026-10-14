import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';
import 'chat_models.dart';

/// A stored conversation in the list (`GET /api/v1/ai/conversations`).
@immutable
class ConversationSummary {
  const ConversationSummary({
    required this.id,
    required this.title,
    required this.portfolioId,
    required this.updatedAt,
  });

  factory ConversationSummary.fromJson(JsonReader r) => ConversationSummary(
    id: r.string('id'),
    title: r.stringOrNull('title'),
    portfolioId: r.stringOrNull('portfolio_id'),
    updatedAt: r.timestamp('updated_at'),
  );

  final String id;
  final String? title;

  /// The portfolio the conversation was limited to, if any.
  final String? portfolioId;
  final DateTime updatedAt;
}

/// One stored message. [structured] is the validated answer of an assistant message.
@immutable
class StoredMessage {
  const StoredMessage({
    required this.isUser,
    required this.content,
    this.structured,
  });

  factory StoredMessage.fromJson(JsonReader r) => StoredMessage(
    isUser: r.enumByName('role', _Role.values) == _Role.user,
    content: r.string('content'),
    structured: r.has('structured') ? r.object('structured') : null,
  );

  final bool isUser;
  final String content;
  final JsonReader? structured;
}

enum _Role { user, assistant }

/// A stored conversation with its messages, oldest first.
@immutable
class ConversationDetail {
  ConversationDetail({
    required this.summary,
    required List<StoredMessage> messages,
  }) : messages = List.unmodifiable(messages);

  factory ConversationDetail.fromJson(JsonReader r) => ConversationDetail(
    summary: ConversationSummary.fromJson(r),
    messages: r.list('messages', StoredMessage.fromJson),
  );

  final ConversationSummary summary;
  final List<StoredMessage> messages;

  /// The conversation as turns of question and answer. A question without an answer (the answer
  /// was refused or never produced) is kept as an unanswered turn; an assistant message with no
  /// question before it is skipped.
  List<ChatTurn> toTurns() {
    final turns = <ChatTurn>[];
    String? question;
    for (final m in messages) {
      if (m.isUser) {
        if (question != null) {
          turns.add(ChatTurn(question: question, done: true));
        }
        question = m.content;
        continue;
      }
      if (question == null) continue;
      turns.add(answerTurn(question, m));
      question = null;
    }
    if (question != null) turns.add(ChatTurn(question: question, done: true));
    return turns;
  }
}

/// The turn for [question] answered by [message].
ChatTurn answerTurn(String question, StoredMessage message) {
  final structured = message.structured;
  if (structured != null && structured.has('refusal')) {
    return ChatTurn(question: question, refusal: message.content, done: true);
  }
  final sections = structured == null
      ? [AnswerSection(kind: SectionKind.interpretation, text: message.content)]
      : sectionsFromStructured(structured);
  return ChatTurn(question: question, sections: sections, done: true);
}

/// The four sections of a validated answer, then the server's own notices.
List<AnswerSection> sectionsFromStructured(JsonReader s) {
  List<String> cited(String key) =>
      s.has(key) ? s.list(key, (i) => i.string('text')) : const <String>[];
  List<String> plain(String key) => s.has(key) ? s.strings(key) : const [];
  return [
    for (final t in cited('observed'))
      AnswerSection(kind: SectionKind.observed, text: t),
    for (final t in cited('calculated'))
      AnswerSection(kind: SectionKind.calculated, text: t),
    for (final t in plain('assumptions'))
      AnswerSection(kind: SectionKind.assumption, text: t),
    if (s.has('interpretation') && s.string('interpretation').isNotEmpty)
      AnswerSection(
        kind: SectionKind.interpretation,
        text: s.string('interpretation'),
      ),
    for (final t in plain('caveats'))
      AnswerSection(kind: SectionKind.notice, text: t),
    if (s.has('sources'))
      for (final line in s.list('sources', sourceLine))
        AnswerSection(kind: SectionKind.source, text: line),
  ];
}

/// One server-built source as a line: "get_forecast · as of 2026-10-09T08:00:00Z · simulated ·
/// model lightgbm v14 · generated 2026-10-09T08:00:00Z".
String sourceLine(JsonReader r) {
  final parts = <String>[r.string('tool')];
  final asOf = r.stringOrNull('as_of');
  if (asOf != null) parts.add('as of $asOf');
  if (r.has('data_types')) {
    final types = r.strings('data_types');
    if (types.isNotEmpty) parts.add(types.join(', '));
  }
  final model = r.stringOrNull('model');
  if (model != null) parts.add('model $model');
  final generated = r.stringOrNull('generated_at');
  if (generated != null) parts.add('generated $generated');
  return parts.join(' · ');
}

import 'dart:convert';

import 'package:dio/dio.dart';

import '../../../app/app_routes.dart';
import '../../../core/data/json_reader.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/domain/wealth_models.dart';
import '../domain/chat_models.dart';
import '../domain/conversation_models.dart';
import 'copilot_repository.dart';
import 'sse.dart';

/// The Copilot over the WealthSphere API (`POST /api/v1/ai/chat`, server-sent events).
///
/// The server checks every answer before it sends any of it, so the events are: which tool is
/// running (`tool`), the data an answer rests on (`source`), the answer text (`token`), and a
/// closing `done` that carries the validated answer in its four sections. This class turns them
/// into the [ChatEvent]s the screen already shows: progress, then sources, then the sections (or
/// a refusal), then done. The text of `token` events is only the fallback for a `done` without
/// sections. Nothing here writes or changes what the assistant says.
class LiveCopilotRepository extends LiveRepository
    implements CopilotRepository {
  const LiveCopilotRepository(super.dio);

  static const _chatPath = '/api/v1/ai/chat';
  static const _conversations = '/api/v1/ai/conversations';

  /// The server holds the connection while the model writes the answer.
  static const _patience = Duration(seconds: 90);

  // Live mode shows the app's own wording for the introduction and suggestions.
  @override
  Future<List<String>> suggestedQuestions() async => const [];

  @override
  Future<CopilotIntro> intro() async =>
      const CopilotIntro(intro: '', notice: '');

  @override
  bool get supportsHistory => true;

  @override
  Stream<ChatEvent> ask(
    String question, {
    AiScope? scope,
    String? conversationId,
  }) async* {
    final Response<ResponseBody> response;
    try {
      response = await dio.post<ResponseBody>(
        _chatPath,
        data: chatBody(question, scope: scope, conversationId: conversationId),
        options: Options(
          responseType: ResponseType.stream,
          receiveTimeout: _patience,
          headers: {'Accept': 'text/event-stream'},
        ),
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
    final body = response.data;
    if (body == null) {
      throw const ApiException(ApiErrorKind.invalidResponse);
    }

    final text = StringBuffer();
    var finished = false;
    try {
      await for (final frame in parseSse(body.stream)) {
        final events = mapFrame(frame, text);
        for (final event in events) {
          yield event;
        }
        if (frame.event == 'done' || frame.event == 'error') {
          finished = true;
          break;
        }
      }
    } on FormatException catch (e) {
      throw ApiException(ApiErrorKind.invalidResponse, detail: e.message);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
    // A stream that ends without `done` or `error` was cut off: the caller shows a failure.
    if (!finished) throw const ApiException(ApiErrorKind.network);
  }

  /// The request body. Only a portfolio scope reaches the server (it enforces it); the
  /// consolidated view, a forecast or a goal narrow nothing on the server.
  static Map<String, Object?> chatBody(
    String question, {
    AiScope? scope,
    String? conversationId,
  }) => {
    'message': question,
    'conversation_id': ?conversationId,
    if (scope != null &&
        scope.kind == AiScopeKind.portfolio &&
        scope.id != PortfolioRef.consolidatedId)
      'scope': {'portfolio_id': scope.id},
  };

  /// The events one frame stands for. [text] collects the `token` text of the answer.
  static List<ChatEvent> mapFrame(SseFrame frame, StringBuffer text) {
    final Object? decoded = jsonDecode(frame.data);
    final r = JsonReader(decoded);
    switch (frame.event) {
      case 'tool':
        // Only the start is shown: a failed tool is explained by the answer's own notice.
        return r.string('status') == 'running'
            ? [ToolProgressEvent('', tool: r.string('name'))]
            : const [];
      case 'source':
        if (!r.has('as_of')) return const [];
        return [
          SourceEvent(
            EvidenceSourceDto(
              label: r.string('tool'),
              provider: 'WealthSphere',
              asOf: r.timestamp('as_of'),
            ),
          ),
        ];
      case 'token':
        text.write(r.string('text'));
        return const [];
      case 'error':
        return [ErrorEvent(r.string('message'))];
      case 'done':
        return _finish(r, text.toString());
      default:
        return const []; // an event type from a newer server is ignored
    }
  }

  static List<ChatEvent> _finish(JsonReader done, String text) {
    final id = done.string('conversation_id');
    final structured = done.has('structured')
        ? done.object('structured')
        : null;
    if (structured != null && structured.has('refusal')) {
      return [
        RefusalEvent(text, conversationId: id),
        DoneEvent(conversationId: id),
      ];
    }
    final sections = structured == null
        ? <AnswerSection>[]
        : sectionsFromStructured(structured);
    return [
      if (sections.isNotEmpty)
        for (final s in sections) SectionEvent(s)
      else if (text.isNotEmpty)
        SectionEvent(
          AnswerSection(kind: SectionKind.interpretation, text: text),
        ),
      DoneEvent(conversationId: id),
    ];
  }

  @override
  Future<List<ConversationSummary>> conversations() =>
      getList(_conversations, ConversationSummary.fromJson);

  @override
  Future<ConversationDetail> conversation(String id) =>
      getObject('$_conversations/$id', ConversationDetail.fromJson);

  @override
  Future<void> deleteConversation(String id) =>
      sendEmpty('DELETE', '$_conversations/$id');

  @override
  Future<void> deleteAllConversations() => sendEmpty('DELETE', _conversations);
}

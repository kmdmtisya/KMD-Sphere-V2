import 'dart:convert';

import 'package:flutter/foundation.dart';

/// One server-sent event: its `event:` name and its `data:` text.
@immutable
class SseFrame {
  const SseFrame(this.event, this.data);

  final String event;
  final String data;

  @override
  bool operator ==(Object other) =>
      other is SseFrame && other.event == event && other.data == data;

  @override
  int get hashCode => Object.hash(event, data);
}

/// Reads server-sent events from raw response bytes.
///
/// Frames end at a blank line; chunk boundaries may fall anywhere (inside a frame, a line or a
/// multi-byte character). Lines starting with `:` are comments, `\r\n` is accepted, and several
/// `data:` lines of one frame are joined with a newline. A frame without data is dropped; one
/// without a name is `message`. An incomplete frame at the end of the stream is dropped: the
/// server always ends a frame with a blank line, so a cut-off one is a broken connection.
Stream<SseFrame> parseSse(Stream<List<int>> bytes) async* {
  var buffer = '';
  await for (final text in bytes.cast<List<int>>().transform(utf8.decoder)) {
    buffer += text.replaceAll('\r\n', '\n');
    int end;
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      final block = buffer.substring(0, end);
      buffer = buffer.substring(end + 2);
      final frame = _frame(block);
      if (frame != null) yield frame;
    }
  }
}

SseFrame? _frame(String block) {
  var event = 'message';
  final data = <String>[];
  for (final line in block.split('\n')) {
    if (line.isEmpty || line.startsWith(':')) continue;
    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1);
    switch (field) {
      case 'event':
        event = value;
      case 'data':
        data.add(value);
    }
  }
  return data.isEmpty ? null : SseFrame(event, data.join('\n'));
}

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/features/copilot/data/sse.dart';

Stream<List<int>> chunks(List<String> parts) =>
    Stream.fromIterable([for (final p in parts) utf8.encode(p)]);

Future<List<SseFrame>> read(List<String> parts) =>
    parseSse(chunks(parts)).toList();

void main() {
  group('server-sent events', () {
    test('reads frames with a name and a data line', () async {
      final frames = await read([
        'event: tool\ndata: {"a":1}\n\nevent: done\ndata: {"b":2}\n\n',
      ]);
      expect(frames, const [
        SseFrame('tool', '{"a":1}'),
        SseFrame('done', '{"b":2}'),
      ]);
    });

    test('a frame split across chunks is put back together', () async {
      final frames = await read([
        'event: to',
        'ken\nda',
        'ta: {"text":"hel',
        'lo"}\n',
        '\nevent: done\ndata: {}\n\n',
      ]);
      expect(frames.map((f) => f.event), ['token', 'done']);
      expect(frames.first.data, '{"text":"hello"}');
    });

    test('a multi-byte character split between chunks survives', () async {
      final bytes = utf8.encode('event: token\ndata: {"text":"€5"}\n\n');
      final cut = bytes.indexOf(0xE2) + 1; // inside the euro sign
      final frames = await parseSse(
        Stream.fromIterable([bytes.sublist(0, cut), bytes.sublist(cut)]),
      ).toList();
      expect(frames.single.data, '{"text":"€5"}');
    });

    test('accepts CRLF, comments and several data lines', () async {
      final frames = await read([
        ': keep-alive\r\nevent: token\r\ndata: one\r\ndata: two\r\n\r\n',
      ]);
      expect(frames.single, const SseFrame('token', 'one\ntwo'));
    });

    test(
      'a frame without data is dropped and one without a name is a message',
      () async {
        final frames = await read(['event: noop\n\ndata: plain\n\n']);
        expect(frames.single, const SseFrame('message', 'plain'));
      },
    );

    test('a frame cut off before its blank line is not delivered', () async {
      final frames = await read([
        'event: done\ndata: {}\n\nevent: token\ndata: {',
      ]);
      expect(frames.map((f) => f.event), ['done']);
    });

    test('an empty stream gives no frames', () async {
      expect(await read(const []), isEmpty);
    });
  });
}

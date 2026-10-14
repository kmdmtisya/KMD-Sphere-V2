import 'dart:async';
import 'dart:convert';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/features/forex/data/forex_stream.dart';
import 'package:wealthsphere_app/features/forex/domain/forex_models.dart';

/// The quote stream's resilience (P13-T11.9; QG-19.3, QG-19.5): the token travels in the first
/// frame (never the URL), pairs are subscribed again after every reconnect, a dropped or silent
/// connection reconnects with backoff, the server's close codes are honoured, and pause/resume
/// follow the app's lifecycle.
class FakeSocket implements ForexSocket {
  final _frames = StreamController<Object?>();
  final sent = <Map<String, dynamic>>[];
  int? _code;
  bool closed = false;

  @override
  Stream<Object?> get frames => _frames.stream;

  @override
  void send(String text) => sent.add(jsonDecode(text) as Map<String, dynamic>);

  @override
  Future<void> close(int code) async {
    closed = true;
    _code ??= code;
    await _frames.close();
  }

  @override
  int? get closeCode => _code;

  void server(Map<String, Object?> frame) => _frames.add(jsonEncode(frame));

  /// The server closes with [code].
  void drop([int? code]) {
    _code = code;
    unawaited(_frames.close());
  }
}

Map<String, Object?> quote(String instrument, String mid) => {
  'type': 'quote',
  'instrument': instrument,
  'provider': 'fake',
  'bid': mid,
  'ask': mid,
  'mid': mid,
  'ts_provider': '2026-10-09T08:00:00Z',
  'age_seconds': 1,
  'data_type': 'simulated',
  'freshness': 'fresh',
  'feed_status': 'connected',
};

class Harness {
  final sockets = <FakeSocket>[];
  final uris = <Uri>[];
  String? token = 'access-token';

  late final client = ForexStreamClient(
    uri: Uri.parse('wss://api.test/api/v1/forex/stream'),
    token: () async => token,
    connect: (uri) async {
      uris.add(uri);
      final s = FakeSocket();
      sockets.add(s);
      return s;
    },
  );

  FakeSocket get last => sockets.last;
}

void main() {
  test('the stream endpoint follows the API base URL', () {
    expect(
      streamUri('https://api.example.com').toString(),
      'wss://api.example.com/api/v1/forex/stream',
    );
    expect(streamUri('http://10.0.2.2:8000/').scheme, 'ws');
  });

  test('authenticates in the first frame, then subscribes on ready', () {
    fakeAsync((async) {
      final h = Harness();
      final quotes = <ForexQuote>[];
      h.client.quotes.listen(quotes.add);
      h.client.follow({'EUR_USD', 'GBP_USD'});
      unawaited(h.client.start());
      async.flushMicrotasks();
      expect(h.uris.single.query, isEmpty); // the token is never in the URL
      expect(h.last.sent.first, {'type': 'auth', 'token': 'access-token'});
      h.last.server({'type': 'ready', 'max_instruments': 20, 'notice': 'x'});
      async.flushMicrotasks();
      expect(h.client.state, StreamState.live);
      expect(h.last.sent[1], {
        'type': 'subscribe',
        'instruments': ['EUR_USD', 'GBP_USD'],
      });
      h.last.server(quote('EUR_USD', '1.0861'));
      async.flushMicrotasks();
      expect(quotes.single.mid.toString(), '1.0861');
      expect(quotes.single.kind, PriceKind.simulated);
      h.client.follow({'EUR_USD'});
      expect(h.last.sent.last, {
        'type': 'unsubscribe',
        'instruments': ['GBP_USD'],
      });
      unawaited(h.client.dispose());
      async.flushMicrotasks();
    });
  });

  test('a dropped connection reconnects with backoff and subscribes again', () {
    fakeAsync((async) {
      final h = Harness();
      h.client.follow({'EUR_USD'});
      unawaited(h.client.start());
      async.flushMicrotasks();
      h.last.server({'type': 'ready'});
      async.flushMicrotasks();
      h.last.drop(1006);
      async.flushMicrotasks();
      expect(h.client.state, StreamState.reconnecting);
      expect(h.sockets, hasLength(1));
      async.elapse(const Duration(milliseconds: 999));
      expect(h.sockets, hasLength(1)); // waits the first backoff (1 s)
      async.elapse(const Duration(milliseconds: 2));
      expect(h.sockets, hasLength(2));
      h.last.server({'type': 'ready'});
      async.flushMicrotasks();
      expect(h.client.state, StreamState.live);
      expect(h.last.sent.last, {
        'type': 'subscribe',
        'instruments': ['EUR_USD'],
      });
      // Failures in a row back off further: 1 s, 2 s, 4 s.
      h.last.drop(1006);
      async.flushMicrotasks();
      async.elapse(const Duration(seconds: 1, milliseconds: 1));
      expect(h.sockets, hasLength(3));
      h.last.drop(1006);
      async.flushMicrotasks();
      async.elapse(const Duration(seconds: 1, milliseconds: 1));
      expect(h.sockets, hasLength(3));
      async.elapse(const Duration(seconds: 1));
      expect(h.sockets, hasLength(4));
      unawaited(h.client.dispose());
      async.flushMicrotasks();
    });
  });

  test('silence is treated as a dropped connection', () {
    fakeAsync((async) {
      final h = Harness();
      unawaited(h.client.start());
      async.flushMicrotasks();
      h.last.server({'type': 'ready'});
      async.flushMicrotasks();
      async.elapse(const Duration(seconds: 10));
      h.last.server({'type': 'heartbeat', 'ts': 'x'}); // re-arms the watchdog
      async.flushMicrotasks();
      async.elapse(const Duration(seconds: 14));
      expect(h.sockets, hasLength(1));
      async.elapse(const Duration(seconds: 2));
      expect(h.sockets.first.closed, isTrue);
      expect(h.client.state, StreamState.reconnecting);
      async.elapse(const Duration(seconds: 2));
      expect(h.sockets, hasLength(2));
      unawaited(h.client.dispose());
      async.flushMicrotasks();
    });
  });

  test(
    'close codes: 4401 reconnects at once, 4404 stops, 4429 waits longest',
    () {
      fakeAsync((async) {
        final h = Harness();
        unawaited(h.client.start());
        async.flushMicrotasks();
        h.token = 'fresh-token';
        h.last.drop(4401);
        async.flushMicrotasks();
        expect(h.sockets, hasLength(2));
        expect(h.last.sent.first['token'], 'fresh-token');
        h.last.drop(4429);
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 29));
        expect(h.sockets, hasLength(2));
        async.elapse(const Duration(seconds: 2));
        expect(h.sockets, hasLength(3));
        h.last.drop(4404);
        async.flushMicrotasks();
        expect(h.client.state, StreamState.stopped);
        async.elapse(const Duration(minutes: 5));
        expect(h.sockets, hasLength(3)); // forex is off: no retry
        unawaited(h.client.dispose());
        async.flushMicrotasks();
      });
    },
  );

  test('pause closes and stops retrying; resume reconnects at once', () {
    fakeAsync((async) {
      final h = Harness();
      unawaited(h.client.start());
      async.flushMicrotasks();
      h.last.server({'type': 'ready'});
      async.flushMicrotasks();
      unawaited(h.client.pause());
      async.flushMicrotasks();
      expect(h.client.state, StreamState.paused);
      expect(h.last.closed, isTrue);
      async.elapse(const Duration(minutes: 2));
      expect(h.sockets, hasLength(1));
      unawaited(h.client.resume());
      async.flushMicrotasks();
      expect(h.sockets, hasLength(2));
      unawaited(h.client.dispose());
      async.flushMicrotasks();
    });
  });

  test('signed out: no connection is attempted', () {
    fakeAsync((async) {
      final h = Harness()..token = null;
      unawaited(h.client.start());
      async.flushMicrotasks();
      expect(h.sockets, isEmpty);
      expect(h.client.state, StreamState.stopped);
    });
  });

  test('the DEMO stream replays only the followed pairs and pauses', () {
    fakeAsync((async) {
      final frames = [
        for (final (i, _) in [('EUR_USD', '1.1'), ('GBP_USD', '1.2')])
          ForexQuote(
            instrument: i,
            freshness: QuoteFreshness.fresh,
            kind: PriceKind.simulated,
            mid: null,
            bid: null,
            ask: null,
          ),
      ];
      final demo = DemoForexStream(frames, every: const Duration(seconds: 1));
      final got = <String>[];
      demo.quotes.listen((q) => got.add(q.instrument));
      demo.follow({'GBP_USD'});
      unawaited(demo.start());
      async.elapse(const Duration(seconds: 3));
      expect(got, everyElement('GBP_USD'));
      expect(got, hasLength(3));
      unawaited(demo.pause());
      async.elapse(const Duration(seconds: 5));
      expect(got, hasLength(3));
      unawaited(demo.dispose());
      async.flushMicrotasks();
    });
  });
}

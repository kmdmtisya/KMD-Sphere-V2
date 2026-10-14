import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../../../core/data/json_reader.dart';
import '../domain/forex_models.dart';

/// The live quote stream (P13-T11.9) over `WS /api/v1/forex/stream`.
///
/// Protocol (backend `stream_api.py`): the first frame is `{"type": "auth", "token": ...}` (the
/// token never goes in the URL), then `subscribe`; the server sends `ready`, `subscribed` (with a
/// snapshot), `quote`, `status`, `heartbeat`, `pong` and `error` frames.
///
/// Resilience:
/// - a dropped connection reconnects with exponential backoff (1, 2, 4 ... 30 s) and subscribes
///   again to every pair still wanted;
/// - no frame for [silence] (three missed heartbeats) counts as a drop;
/// - close codes: 4401 (token expired) reconnects at once with a fresh token, 4404 (forex switched
///   off) stops, 4429 (too many connections or messages) waits the longest backoff;
/// - [pause] (app in the background, or offline) closes the socket and [resume] reconnects at
///   once; nothing is retried while paused.
/// Prices from the stream are shown with their freshness and data type: none is presented as an
/// executable quote.
enum StreamState { idle, connecting, live, reconnecting, paused, stopped }

/// A connected socket. An interface so tests can drive the client without a network.
abstract interface class ForexSocket {
  Stream<Object?> get frames;
  void send(String text);
  Future<void> close(int code);
  int? get closeCode;
}

typedef SocketConnector = Future<ForexSocket> Function(Uri uri);

class _IoSocket implements ForexSocket {
  _IoSocket(this._socket);

  final WebSocket _socket;

  @override
  Stream<Object?> get frames => _socket;

  @override
  void send(String text) => _socket.add(text);

  @override
  Future<void> close(int code) => _socket.close(code);

  @override
  int? get closeCode => _socket.closeCode;
}

Future<ForexSocket> connectIo(Uri uri) async =>
    _IoSocket(await WebSocket.connect(uri.toString()));

/// The stream endpoint for an API base URL: https -> wss, http -> ws.
Uri streamUri(String apiBaseUrl) {
  final base = Uri.parse(apiBaseUrl);
  return base.replace(
    scheme: base.scheme == 'https' ? 'wss' : 'ws',
    path: '${base.path.replaceAll(RegExp(r'/$'), '')}/api/v1/forex/stream',
  );
}

/// What the screens use: the live client or the DEMO replay.
abstract interface class ForexQuoteStream {
  Stream<ForexQuote> get quotes;
  Stream<StreamState> get states;
  StreamState get state;
  void follow(Set<String> instruments);
  Future<void> start();
  Future<void> pause();
  Future<void> resume();
  Future<void> dispose();
}

class ForexStreamClient implements ForexQuoteStream {
  ForexStreamClient({
    required this.uri,
    required this.token,
    required this.connect,
    this.silence = const Duration(seconds: 15),
    Duration Function(int attempt)? backoff,
  }) : _backoff = backoff ?? defaultBackoff;

  final Uri uri;
  final Future<String?> Function() token;
  final SocketConnector connect;
  final Duration silence;
  final Duration Function(int attempt) _backoff;

  static Duration defaultBackoff(int attempt) =>
      Duration(seconds: attempt >= 5 ? 30 : 1 << attempt);

  static const maxBackoff = Duration(seconds: 30);

  final _quotes = StreamController<ForexQuote>.broadcast();
  final _states = StreamController<StreamState>.broadcast();
  final _feed = StreamController<String>.broadcast();

  ForexSocket? _socket;
  StreamSubscription<Object?>? _frames;
  Timer? _retry;
  Timer? _watchdog;
  Set<String> _wanted = {};
  StreamState _state = StreamState.idle;
  int _attempt = 0;

  /// Prices as they arrive: the subscription's snapshots, then each update.
  @override
  Stream<ForexQuote> get quotes => _quotes.stream;

  /// The connection's state, for the screen's banner.
  @override
  Stream<StreamState> get states => _states.stream;

  /// The feed's status as the server reports it (connected, degraded, disconnected).
  Stream<String> get feedStatus => _feed.stream;

  @override
  StreamState get state => _state;

  /// The pairs to follow. Sent at once when live; remembered for every reconnect.
  @override
  void follow(Set<String> instruments) {
    final added = instruments.difference(_wanted);
    final removed = _wanted.difference(instruments);
    _wanted = {...instruments};
    if (_state != StreamState.live) return;
    if (removed.isNotEmpty) {
      _send({'type': 'unsubscribe', 'instruments': removed.toList()..sort()});
    }
    if (added.isNotEmpty) {
      _send({'type': 'subscribe', 'instruments': added.toList()..sort()});
    }
  }

  /// Opens the connection (no-op when already open or stopped for good).
  @override
  Future<void> start() async {
    if (_state == StreamState.connecting ||
        _state == StreamState.live ||
        _state == StreamState.stopped) {
      return;
    }
    await _open();
  }

  /// The app went to the background or offline: close and wait for [resume].
  @override
  Future<void> pause() async {
    if (_state == StreamState.stopped) return;
    _setState(StreamState.paused);
    await _drop(1000);
  }

  /// Back in the foreground or online: reconnect at once.
  @override
  Future<void> resume() async {
    if (_state != StreamState.paused) return;
    _attempt = 0;
    await _open();
  }

  @override
  Future<void> dispose() async {
    _setState(StreamState.stopped);
    await _drop(1000);
    await _quotes.close();
    await _states.close();
    await _feed.close();
  }

  Future<void> _open() async {
    _retry?.cancel();
    _setState(
      _attempt == 0 ? StreamState.connecting : StreamState.reconnecting,
    );
    try {
      final access = await token();
      if (access == null) {
        _setState(StreamState.stopped);
        return;
      }
      final socket = await connect(uri);
      if (_state == StreamState.paused || _state == StreamState.stopped) {
        await socket.close(1000);
        return;
      }
      _socket = socket;
      _frames = socket.frames.listen(
        _onFrame,
        onDone: () => _onClosed(socket.closeCode),
        onError: (Object _) => _onClosed(null),
        cancelOnError: true,
      );
      _send({'type': 'auth', 'token': access});
      _arm();
    } on Object {
      _scheduleRetry();
    }
  }

  void _onFrame(Object? raw) {
    _arm();
    if (raw is! String) return;
    final Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return;
    }
    if (decoded is! Map<String, dynamic>) return;
    final frame = JsonReader(decoded);
    switch (decoded['type']) {
      case 'ready':
        _attempt = 0;
        _setState(StreamState.live);
        if (_wanted.isNotEmpty) {
          _send({'type': 'subscribe', 'instruments': _wanted.toList()..sort()});
        }
      case 'subscribed':
        for (final q in frame.list('items', ForexQuote.fromJson)) {
          _quotes.add(q);
        }
      case 'quote':
        _quotes.add(ForexQuote.fromJson(frame));
      case 'status':
        _feed.add(frame.string('feed_status'));
      default:
        break; // heartbeat, pong, error: the watchdog has been re-armed
    }
  }

  void _onClosed(int? code) {
    _frames = null;
    _socket = null;
    _watchdog?.cancel();
    if (_state == StreamState.paused || _state == StreamState.stopped) return;
    switch (code) {
      case 4404:
        _setState(StreamState.stopped); // forex switched off on the server
      case 4401:
        _attempt = 0;
        unawaited(_open()); // a fresh token is fetched on open
      case 4429:
        _attempt = 5;
        _scheduleRetry();
      default:
        _scheduleRetry();
    }
  }

  void _scheduleRetry() {
    if (_state == StreamState.paused || _state == StreamState.stopped) return;
    _setState(StreamState.reconnecting);
    final wait = _backoff(_attempt);
    _attempt += 1;
    _retry?.cancel();
    _retry = Timer(wait, () => unawaited(_open()));
  }

  /// No frame for [silence]: the connection is treated as dropped.
  void _arm() {
    _watchdog?.cancel();
    _watchdog = Timer(silence, () {
      final socket = _socket;
      _socket = null;
      unawaited(_frames?.cancel());
      _frames = null;
      unawaited(socket?.close(4000));
      _scheduleRetry();
    });
  }

  /// Closes the current socket. Never waits on the frame subscription's cancellation, and waits
  /// at most [closeWait] for the close handshake, so pausing or disposing cannot hang.
  Future<void> _drop(int code) async {
    _retry?.cancel();
    _watchdog?.cancel();
    final socket = _socket;
    _socket = null;
    final frames = _frames;
    _frames = null;
    unawaited(frames?.cancel());
    await socket?.close(code).timeout(closeWait, onTimeout: () {});
  }

  static const closeWait = Duration(seconds: 2);

  void _send(Map<String, Object?> message) =>
      _socket?.send(jsonEncode(message));

  void _setState(StreamState next) {
    if (_state == next) return;
    _state = next;
    if (!_states.isClosed) _states.add(next);
  }
}

/// DEMO: replays the fixture's simulated quote frames in a loop, one per [every], for the pairs
/// followed. Labelled DEMO and simulated wherever it is shown.
class DemoForexStream implements ForexQuoteStream {
  DemoForexStream(this._frames, {this.every = const Duration(seconds: 2)});

  final List<ForexQuote> _frames;
  final Duration every;
  final _quotes = StreamController<ForexQuote>.broadcast();
  final _states = StreamController<StreamState>.broadcast();
  Timer? _timer;
  Set<String> _wanted = {};
  int _next = 0;
  StreamState _state = StreamState.idle;

  @override
  Stream<ForexQuote> get quotes => _quotes.stream;

  @override
  Stream<StreamState> get states => _states.stream;

  @override
  StreamState get state => _state;

  @override
  void follow(Set<String> instruments) => _wanted = {...instruments};

  @override
  Future<void> start() async {
    if (_state == StreamState.live || _frames.isEmpty) return;
    _set(StreamState.live);
    _timer = Timer.periodic(every, (_) {
      for (var i = 0; i < _frames.length; i++) {
        final frame = _frames[_next++ % _frames.length];
        if (_wanted.isEmpty || _wanted.contains(frame.instrument)) {
          _quotes.add(frame);
          return;
        }
      }
    });
  }

  @override
  Future<void> pause() async {
    _timer?.cancel();
    _set(StreamState.paused);
  }

  @override
  Future<void> resume() async {
    if (_state == StreamState.paused) {
      _set(StreamState.idle);
      await start();
    }
  }

  @override
  Future<void> dispose() async {
    _timer?.cancel();
    _set(StreamState.stopped);
    await _quotes.close();
    await _states.close();
  }

  void _set(StreamState next) {
    _state = next;
    if (!_states.isClosed) _states.add(next);
  }
}

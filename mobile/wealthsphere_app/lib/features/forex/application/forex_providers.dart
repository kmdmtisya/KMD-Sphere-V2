import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/auth/token_manager.dart';
import '../../../core/config/app_config.dart';
import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../../../core/network/api_exception.dart';
import '../data/forex_repository.dart';
import '../data/forex_stream.dart';
import '../domain/forex_models.dart';

/// Whether the forex section exists (P13-T11.1). DEMO: always (labelled DEMO). Live: only when
/// the server has the forex module switched on; it answers 404 otherwise (DEC-23), and the app
/// then shows no forex entry at all.
final forexAvailableProvider = FutureProvider<bool>((ref) async {
  if (ref.watch(dataSourceModeProvider) == DataSourceMode.demo) return true;
  try {
    await ref.watch(forexRepositoryProvider).quotes();
    return true;
  } on ApiException catch (e) {
    if (e.kind == ApiErrorKind.notFound) return false;
    rethrow;
  }
});

final quoteBoardProvider = FutureProvider<QuoteBoard>(
  (ref) => ref.watch(forexRepositoryProvider).quotes(),
);

/// The live stream: the WebSocket client in live mode, the fixture's replay in DEMO.
final forexStreamProvider = Provider<ForexQuoteStream>((ref) {
  final ForexQuoteStream stream;
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      final assets = ref.watch(demoAssetsProvider);
      final frames = <ForexQuote>[];
      stream = DemoForexStream(frames);
      unawaited(
        assets
            .load('forex.json')
            .then(
              (doc) => frames.addAll(
                JsonReader(doc).list('stream_frames', ForexQuote.fromJson),
              ),
            ),
      );
    case DataSourceMode.live:
      final tokens = ref.watch(tokenManagerProvider);
      stream = ForexStreamClient(
        uri: streamUri(ref.watch(appConfigProvider).apiBaseUrl),
        token: tokens.validAccessToken,
        connect: connectIo,
      );
  }
  ref.onDispose(stream.dispose);
  return stream;
});

/// The connection state for the banner on the live-markets list.
final streamStateProvider = StreamProvider<StreamState>(
  (ref) => ref.watch(forexStreamProvider).states,
);

/// The latest price of each pair: the board's snapshot, then the stream's updates.
///
/// Updates are applied at most every [flushEvery] (QG-19.2): a fast stream batches into one
/// rebuild, so a chart or list never redraws for every tick.
class LiveQuotesNotifier extends Notifier<Map<String, ForexQuote>> {
  static const flushEvery = Duration(milliseconds: 250);

  final Map<String, ForexQuote> _pending = {};
  Timer? _flush;

  @override
  Map<String, ForexQuote> build() {
    final stream = ref.watch(forexStreamProvider);
    final sub = stream.quotes.listen(_onQuote);
    ref.onDispose(() {
      unawaited(sub.cancel());
      _flush?.cancel();
    });
    final board = ref.watch(quoteBoardProvider).value;
    if (board != null) {
      stream.follow({for (final q in board.items) q.instrument});
      unawaited(stream.start());
      return {for (final q in board.items) q.instrument: q};
    }
    return const {};
  }

  void _onQuote(ForexQuote quote) {
    _pending[quote.instrument] = quote;
    _flush ??= Timer(flushEvery, () {
      _flush = null;
      if (_pending.isEmpty) return;
      state = {...state, ..._pending};
      _pending.clear();
    });
  }
}

final liveQuotesProvider =
    NotifierProvider<LiveQuotesNotifier, Map<String, ForexQuote>>(
      LiveQuotesNotifier.new,
    );

typedef PairFrame = ({String instrument, String timeframe});

final candlesProvider = FutureProvider.family<List<ForexCandle>, PairFrame>(
  (ref, k) =>
      ref.watch(forexRepositoryProvider).candles(k.instrument, k.timeframe),
);

final indicatorsProvider =
    FutureProvider.family<List<IndicatorValue>, PairFrame>(
      (ref, k) => ref
          .watch(forexRepositoryProvider)
          .indicators(k.instrument, k.timeframe),
    );

final levelsProvider = FutureProvider.family<List<ForexLevel>, PairFrame>(
  (ref, k) =>
      ref.watch(forexRepositoryProvider).levels(k.instrument, k.timeframe),
);

typedef PairHorizon = ({String instrument, String horizon});

final forexForecastProvider = FutureProvider.family<ForexForecast, PairHorizon>(
  (ref, k) =>
      ref.watch(forexRepositoryProvider).forecast(k.instrument, k.horizon),
);

typedef RankingFilter = ({
  String timeframe,
  String? setup,
  String? risk,
  String? tier,
});

final rankingProvider = FutureProvider.family<ForexRanking, RankingFilter>(
  (ref, f) => ref
      .watch(forexRepositoryProvider)
      .opportunities(
        timeframe: f.timeframe,
        setup: f.setup,
        risk: f.risk,
        tier: f.tier,
      ),
);

final forexCalendarProvider = FutureProvider<List<ForexEvent>>(
  (ref) => ref.watch(forexRepositoryProvider).calendar(),
);

final backtestsProvider =
    FutureProvider.family<List<ForexBacktestSummary>, String>(
      (ref, instrument) =>
          ref.watch(forexRepositoryProvider).backtests(instrument),
    );

final paperAccountsProvider = FutureProvider<List<PaperAccount>>(
  (ref) => ref.watch(forexRepositoryProvider).paperAccounts(),
);

final paperPositionsProvider =
    FutureProvider.family<List<PaperPosition>, String>(
      (ref, accountId) =>
          ref.watch(forexRepositoryProvider).paperPositions(accountId),
    );

final journalProvider = FutureProvider.family<List<JournalEntry>, String>(
  (ref, accountId) => ref.watch(forexRepositoryProvider).journal(accountId),
);

final paperPerformanceProvider =
    FutureProvider.family<PaperPerformance, String>(
      (ref, accountId) =>
          ref.watch(forexRepositoryProvider).paperPerformance(accountId),
    );

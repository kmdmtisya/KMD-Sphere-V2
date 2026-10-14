import 'package:decimal/decimal.dart';

import '../../../core/data/json_reader.dart';
import '../../../core/network/live_repository.dart';
import '../domain/forex_models.dart';
import 'forex_repository.dart';

/// The forex API (P13-T02 to T09). The server computes every figure; this class only asks and
/// parses. Time windows are chosen here (how much history to show), never prices or results.
class LiveForexRepository extends LiveRepository implements ForexRepository {
  const LiveForexRepository(super.dio, {DateTime Function()? clock})
    : _clock = clock ?? _utcNow;

  final DateTime Function() _clock;

  static DateTime _utcNow() => DateTime.now().toUtc();
  static const _base = '/api/v1/forex';
  static const _paper = '$_base/paper/accounts';

  /// How far back a chart reaches: about 120 bars of the timeframe, allowing for weekends.
  static Duration window(String timeframe) => switch (timeframe) {
    '5m' => const Duration(hours: 14),
    '15m' => const Duration(days: 2),
    '1H' => const Duration(days: 7),
    '4H' => const Duration(days: 28),
    _ => const Duration(days: 170),
  };

  Map<String, Object?> _range(String timeframe) {
    final end = _clock();
    return {
      'start': end.subtract(window(timeframe)).toIso8601String(),
      'end': end.toIso8601String(),
    };
  }

  @override
  Future<QuoteBoard> quotes() =>
      getObject('$_base/quotes', QuoteBoard.fromJson);

  @override
  Future<List<ForexCandle>> candles(String instrument, String timeframe) =>
      getObject(
        '$_base/candles',
        (j) => j.list('items', ForexCandle.fromJson),
        query: {
          'instrument': instrument,
          'timeframe': timeframe,
          ..._range(timeframe),
        },
      );

  static const _indicators = [
    'rsi:14',
    'atr:14',
    'adx:14',
    'ema:20',
    'ema:50',
    'macd:12,26,9',
  ];

  @override
  Future<List<IndicatorValue>> indicators(
    String instrument,
    String timeframe,
  ) => getObject(
    '$_base/indicators',
    (j) => [
      for (final s in j.list('series', (r) => r))
        for (final out in s.object('outputs').keys)
          IndicatorValue(
            out == 'value' ? s.string('name') : '${s.string('name')}.$out',
            _last(s.object('outputs'), out),
          ),
    ],
    query: {
      'instrument': instrument,
      'timeframe': timeframe,
      'indicator': _indicators,
      ..._range(timeframe),
    },
  );

  /// The last defined value of an output series (the server's number, unchanged).
  static Decimal? _last(JsonReader outputs, String key) {
    final values = outputs.decimalsOrNull(key);
    for (final v in values.reversed) {
      if (v != null) return v;
    }
    return null;
  }

  @override
  Future<List<ForexLevel>> levels(String instrument, String timeframe) =>
      getObject(
        '$_base/structure',
        (j) => j.list('levels', ForexLevel.fromJson),
        query: {
          'instrument': instrument,
          'timeframe': timeframe,
          ..._range(timeframe),
        },
      );

  @override
  Future<ForexForecast> forecast(String instrument, String horizon) =>
      getObject(
        '$_base/forecasts',
        ForexForecast.fromJson,
        query: {'instrument': instrument, 'horizon': horizon},
      );

  @override
  Future<ForexRanking> opportunities({
    String timeframe = '1H',
    String? setup,
    String? risk,
    String? tier,
  }) => getObject(
    '$_base/opportunities',
    ForexRanking.fromJson,
    query: {
      'timeframe': timeframe,
      'setup': ?setup,
      'risk': ?risk,
      'tier': ?tier,
    },
  );

  @override
  Future<List<ForexEvent>> calendar() {
    final now = _clock();
    return getObject(
      '$_base/calendar',
      (j) => j.list('items', ForexEvent.fromJson),
      query: {
        'start': now.subtract(const Duration(hours: 6)).toIso8601String(),
        'end': now.add(const Duration(days: 7)).toIso8601String(),
      },
    );
  }

  @override
  Future<ForexRiskResult> calculateRisk(Map<String, Object?> request) => send(
    'POST',
    '$_base/risk/calculate',
    ForexRiskResult.fromJson,
    body: request,
  );

  @override
  Future<List<ForexBacktestSummary>> backtests(String instrument) => getObject(
    '$_base/backtests',
    (j) => j.list('items', ForexBacktestSummary.fromJson),
    query: {'instrument': instrument, 'timeframe': '1H'},
  );

  @override
  Future<List<PaperAccount>> paperAccounts() =>
      getObject(_paper, (j) => j.list('items', PaperAccount.fromJson));

  @override
  Future<PaperAccount> openPaperAccount(String name, String currency) => send(
    'POST',
    _paper,
    PaperAccount.fromJson,
    body: {'name': name, 'currency': currency},
  );

  @override
  Future<List<PaperPosition>> paperPositions(
    String accountId, {
    String? status,
  }) => getObject(
    '$_paper/${Uri.encodeComponent(accountId)}/positions',
    (j) => j.list('items', PaperPosition.fromJson),
    query: {'status': ?status},
  );

  @override
  Future<PaperOrderResult> placePaperOrder(
    String accountId,
    PaperOrderRequest order,
  ) => send(
    'POST',
    '$_paper/${Uri.encodeComponent(accountId)}/orders',
    PaperOrderResult.fromJson,
    body: order.toJson(),
  );

  @override
  Future<PaperPosition> closePaperPosition(
    String accountId,
    String positionId,
  ) => send(
    'POST',
    '$_paper/${Uri.encodeComponent(accountId)}/positions/${Uri.encodeComponent(positionId)}/close',
    PaperPosition.fromJson,
  );

  @override
  Future<List<JournalEntry>> journal(String accountId) => getObject(
    '$_paper/${Uri.encodeComponent(accountId)}/journal',
    (j) => j.list('items', JournalEntry.fromJson),
  );

  @override
  Future<JournalEntry> addJournalEntry(
    String accountId,
    String note,
    List<String> tags,
  ) => send(
    'POST',
    '$_paper/${Uri.encodeComponent(accountId)}/journal',
    JournalEntry.fromJson,
    body: {'note': note, 'tags': tags},
  );

  @override
  Future<PaperPerformance> paperPerformance(String accountId) => getObject(
    '$_paper/${Uri.encodeComponent(accountId)}/analytics',
    PaperPerformance.fromJson,
  );
}

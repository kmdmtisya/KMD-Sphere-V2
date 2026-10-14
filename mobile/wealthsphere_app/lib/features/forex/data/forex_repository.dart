import 'package:decimal/decimal.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../../../core/network/api_client.dart';
import '../domain/forex_models.dart';
import 'live_forex_repository.dart';

/// The forex section's data (P13-T11). Live mode reads the forex API (switched on only in
/// development until DEC-19 and DEC-20 allow more); DEMO mode reads `assets/demo/forex.json`.
/// Every figure is the server's or the fixture's; nothing is computed here.
abstract interface class ForexRepository {
  Future<QuoteBoard> quotes();
  Future<List<ForexCandle>> candles(String instrument, String timeframe);
  Future<List<IndicatorValue>> indicators(String instrument, String timeframe);
  Future<List<ForexLevel>> levels(String instrument, String timeframe);
  Future<ForexForecast> forecast(String instrument, String horizon);
  Future<ForexRanking> opportunities({
    String timeframe,
    String? setup,
    String? risk,
    String? tier,
  });
  Future<List<ForexEvent>> calendar();
  Future<ForexRiskResult> calculateRisk(Map<String, Object?> request);
  Future<List<ForexBacktestSummary>> backtests(String instrument);
  Future<List<PaperAccount>> paperAccounts();
  Future<PaperAccount> openPaperAccount(String name, String currency);
  Future<List<PaperPosition>> paperPositions(
    String accountId, {
    String? status,
  });
  Future<PaperOrderResult> placePaperOrder(
    String accountId,
    PaperOrderRequest order,
  );
  Future<PaperPosition> closePaperPosition(String accountId, String positionId);
  Future<List<JournalEntry>> journal(String accountId);
  Future<JournalEntry> addJournalEntry(
    String accountId,
    String note,
    List<String> tags,
  );
  Future<PaperPerformance> paperPerformance(String accountId);
}

/// DEMO: the fixture's illustrative data, labelled DEMO everywhere it is shown. Paper orders and
/// journal entries are kept in memory for the session only, and a DEMO order never "fills": the
/// fixture's positions are what the demo shows.
class DemoForexRepository implements ForexRepository {
  DemoForexRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;
  final List<JournalEntry> _notes = [];

  Future<JsonReader> _doc() async {
    await _gate();
    return JsonReader(await _assets.load('forex.json'));
  }

  @override
  Future<QuoteBoard> quotes() async =>
      QuoteBoard.fromJson((await _doc()).object('quotes'));

  @override
  Future<List<ForexCandle>> candles(String instrument, String timeframe) async {
    final doc = (await _doc()).object('candles');
    if (!doc.has(instrument)) return const [];
    return doc.list(instrument, ForexCandle.fromJson);
  }

  @override
  Future<List<IndicatorValue>> indicators(
    String instrument,
    String timeframe,
  ) async {
    final doc = (await _doc()).object('indicators');
    if (!doc.has(instrument)) return const [];
    return doc.list(
      instrument,
      (r) => IndicatorValue(
        r.string('name'),
        r.has('value') ? r.decimal('value') : null,
      ),
    );
  }

  @override
  Future<List<ForexLevel>> levels(String instrument, String timeframe) async {
    final doc = (await _doc()).object('levels');
    if (!doc.has(instrument)) return const [];
    return doc.list(instrument, ForexLevel.fromJson);
  }

  @override
  Future<ForexForecast> forecast(String instrument, String horizon) async {
    final doc = (await _doc()).object('forecasts');
    final key = '$instrument:$horizon';
    if (!doc.has(key)) {
      return ForexForecast.fromJson(
        JsonReader({
          'horizon': horizon,
          'status': 'unavailable',
          'reason': 'no DEMO forecast for this pair and horizon',
          'notice': (await _doc()).string('forecast_notice'),
        }),
      );
    }
    return ForexForecast.fromJson(doc.object(key));
  }

  @override
  Future<ForexRanking> opportunities({
    String timeframe = '1H',
    String? setup,
    String? risk,
    String? tier,
  }) async {
    final all = ForexRanking.fromJson((await _doc()).object('ranking'));
    bool keep(ForexOpportunity o) =>
        (setup == null || o.type == setup) &&
        (risk == null || o.risk == risk) &&
        (tier == null || o.tier == tier);
    return ForexRanking(
      items: all.items.where(keep).toList(),
      excluded: all.excluded,
      notice: all.notice,
    );
  }

  @override
  Future<List<ForexEvent>> calendar() async =>
      (await _doc()).list('calendar', ForexEvent.fromJson);

  @override
  Future<ForexRiskResult> calculateRisk(Map<String, Object?> request) async {
    // DEMO: the one worked example in the fixture, whatever was entered (labelled DEMO).
    return ForexRiskResult.fromJson((await _doc()).object('risk_example'));
  }

  @override
  Future<List<ForexBacktestSummary>> backtests(String instrument) async =>
      (await _doc())
          .list('backtests', ForexBacktestSummary.fromJson)
          .where((b) => b.instrument == instrument)
          .toList();

  @override
  Future<List<PaperAccount>> paperAccounts() async =>
      (await _doc()).list('paper_accounts', PaperAccount.fromJson);

  @override
  Future<PaperAccount> openPaperAccount(String name, String currency) async =>
      throw const DemoDataException(
        'Paper accounts cannot be opened in DEMO mode.',
      );

  @override
  Future<List<PaperPosition>> paperPositions(
    String accountId, {
    String? status,
  }) async {
    final all = (await _doc()).list('paper_positions', PaperPosition.fromJson);
    return [
      for (final p in all)
        if (status == null || (status == 'open') == p.open) p,
    ];
  }

  @override
  Future<PaperOrderResult> placePaperOrder(
    String accountId,
    PaperOrderRequest order,
  ) async => throw const DemoDataException(
    'Paper orders are not simulated in DEMO mode.',
  );

  @override
  Future<PaperPosition> closePaperPosition(
    String accountId,
    String positionId,
  ) async => throw const DemoDataException(
    'Paper positions are not changed in DEMO mode.',
  );

  @override
  Future<List<JournalEntry>> journal(String accountId) async => [
    ..._notes.reversed,
    ...(await _doc()).list('journal', JournalEntry.fromJson),
  ];

  @override
  Future<JournalEntry> addJournalEntry(
    String accountId,
    String note,
    List<String> tags,
  ) async {
    await _gate();
    final entry = JournalEntry(
      id: 'demo-note-${_notes.length + 1}',
      note: note,
      tags: tags,
      createdAt: DateTime.now().toUtc(),
    );
    _notes.add(entry);
    return entry;
  }

  @override
  Future<PaperPerformance> paperPerformance(String accountId) async =>
      PaperPerformance.fromJson((await _doc()).object('paper_performance'));
}

final forexRepositoryProvider = Provider<ForexRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoForexRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
    case DataSourceMode.live:
      return LiveForexRepository(ref.watch(apiClientProvider));
  }
});

/// Decimal from a text field: null when it is not a plain decimal number.
Decimal? parseDecimalInput(String text) {
  final t = text.trim();
  if (!RegExp(r'^\d+(\.\d+)?$').hasMatch(t)) return null;
  return Decimal.tryParse(t);
}

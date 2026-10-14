import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';

/// The forex section's view of the server's data (P13-T11). Parsed only: every price, figure and
/// label is the server's (or the DEMO fixture's); the app computes none of them (CLAUDE.md).

/// How usable a price is. Only `fresh` is shown as current; nothing here is an executable quote.
enum QuoteFreshness {
  fresh,
  stale,
  unavailable;

  static QuoteFreshness parse(String text) => switch (text) {
    'fresh' => fresh,
    'stale' => stale,
    _ => unavailable,
  };
}

/// What kind of price it is. Only a tradable quote is executable, and WealthSphere executes
/// nothing; the others are always labelled.
enum PriceKind {
  tradable,
  indicative,
  delayed,
  simulated,
  unknown;

  static PriceKind parse(String? text) => switch (text) {
    'tradable_quote' => tradable,
    'indicative_rate' => indicative,
    'delayed' => delayed,
    'simulated' => simulated,
    _ => unknown,
  };
}

@immutable
class ForexQuote {
  const ForexQuote({
    required this.instrument,
    required this.freshness,
    required this.kind,
    this.bid,
    this.ask,
    this.mid,
    this.quoteTime,
    this.ageSeconds,
  });

  factory ForexQuote.fromJson(JsonReader j) => ForexQuote(
    instrument: j.string('instrument'),
    freshness: QuoteFreshness.parse(j.string('freshness')),
    kind: PriceKind.parse(j.stringOrNull('data_type')),
    bid: j.has('bid') ? j.decimal('bid') : null,
    ask: j.has('ask') ? j.decimal('ask') : null,
    mid: j.has('mid') ? j.decimal('mid') : null,
    quoteTime: j.has('ts_provider') ? j.timestamp('ts_provider') : null,
    ageSeconds: j.has('age_seconds') ? j.integer('age_seconds') : null,
  );

  final String instrument;
  final QuoteFreshness freshness;
  final PriceKind kind;
  final Decimal? bid;
  final Decimal? ask;
  final Decimal? mid;
  final DateTime? quoteTime;
  final int? ageSeconds;

  /// "EUR_USD" -> "EUR/USD".
  String get label => instrument.replaceAll('_', '/');

  ForexQuote copyWith({QuoteFreshness? freshness}) => ForexQuote(
    instrument: instrument,
    freshness: freshness ?? this.freshness,
    kind: kind,
    bid: bid,
    ask: ask,
    mid: mid,
    quoteTime: quoteTime,
    ageSeconds: ageSeconds,
  );
}

/// The quote board: the feed's status and a price per pair.
@immutable
class QuoteBoard {
  const QuoteBoard({
    required this.feedStatus,
    required this.items,
    required this.notice,
  });

  factory QuoteBoard.fromJson(JsonReader j) => QuoteBoard(
    feedStatus: j.string('feed_status'),
    items: j.list('items', ForexQuote.fromJson),
    notice: j.string('notice'),
  );

  final String feedStatus;
  final List<ForexQuote> items;
  final String notice;
}

@immutable
class ForexCandle {
  const ForexCandle({
    required this.start,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
  });

  factory ForexCandle.fromJson(JsonReader j) => ForexCandle(
    start: j.timestamp('ts'),
    open: j.decimal('open'),
    high: j.decimal('high'),
    low: j.decimal('low'),
    close: j.decimal('close'),
  );

  final DateTime start;
  final Decimal open;
  final Decimal high;
  final Decimal low;
  final Decimal close;
}

/// A named indicator value at the last closed bar, as the server computed it.
@immutable
class IndicatorValue {
  const IndicatorValue(this.name, this.value);

  final String name;
  final Decimal? value;
}

@immutable
class ForexLevel {
  const ForexLevel({
    required this.price,
    required this.role,
    required this.touches,
  });

  factory ForexLevel.fromJson(JsonReader j) => ForexLevel(
    price: j.decimal('price'),
    role: j.string('role'),
    touches: j.integer('touches'),
  );

  final Decimal price;
  final String role;
  final int touches;
}

/// A published model forecast. Never "what will happen": a probability with its calibration
/// label and an interval.
@immutable
class ForexForecast {
  const ForexForecast({
    required this.horizon,
    required this.available,
    this.reason,
    this.probUp,
    this.probabilityLabel,
    this.priceMedian,
    this.low80,
    this.high80,
    this.generatedAt,
    this.modelName,
    this.modelVersion,
    this.statement,
    this.dataTypes = const [],
    required this.notice,
  });

  factory ForexForecast.fromJson(JsonReader j) {
    final values = j.has('forecast') ? j.object('forecast') : null;
    final model = j.has('model') ? j.object('model') : null;
    return ForexForecast(
      horizon: j.string('horizon'),
      available: j.string('status') == 'available',
      reason: j.stringOrNull('reason'),
      probUp: values?.decimal('prob_up'),
      probabilityLabel: values?.string('probability_label'),
      priceMedian: values?.decimal('price_median'),
      low80: values?.object('price_interval_80').decimal('low'),
      high80: values?.object('price_interval_80').decimal('high'),
      generatedAt: values?.timestamp('generated_at'),
      modelName: model?.string('name'),
      modelVersion: model?.string('version'),
      statement: model?.string('statement'),
      dataTypes: values?.strings('data_types') ?? const [],
      notice: j.string('notice'),
    );
  }

  final String horizon;
  final bool available;
  final String? reason;
  final Decimal? probUp;
  final String? probabilityLabel;
  final Decimal? priceMedian;
  final Decimal? low80;
  final Decimal? high80;
  final DateTime? generatedAt;
  final String? modelName;
  final String? modelVersion;
  final String? statement;
  final List<String> dataTypes;
  final String notice;

  bool get calibrated => probabilityLabel == 'Calibrated';
}

/// One research candidate of the Opportunity Ranking. Not a recommendation.
@immutable
class ForexOpportunity {
  const ForexOpportunity({
    required this.rank,
    required this.instrument,
    required this.tier,
    required this.label,
    required this.condition,
    required this.type,
    required this.scenario,
    required this.risk,
    required this.score,
    required this.entry,
    required this.stop,
    required this.target,
    required this.riskReward,
    required this.levelsAsOf,
    required this.factors,
    required this.risks,
    required this.assumptions,
    required this.adjustments,
    required this.spreadPips,
    required this.dataTypes,
    this.forecastLabel,
  });

  factory ForexOpportunity.fromJson(JsonReader j) {
    final levels = j.object('levels');
    final forecast = j.has('forecast') ? j.object('forecast') : null;
    return ForexOpportunity(
      rank: j.has('rank') ? j.integer('rank') : null,
      instrument: j.string('instrument'),
      tier: j.string('tier'),
      label: j.string('label'),
      condition: j.string('market_condition'),
      type: j.string('opportunity_type'),
      scenario: j.string('scenario'),
      risk: j.string('risk'),
      score: j.decimal('score'),
      entry: levels.decimal('entry'),
      stop: levels.decimal('stop'),
      target: levels.decimal('target'),
      riskReward: levels.decimal('risk_reward'),
      levelsAsOf: levels.timestamp('as_of'),
      factors: j.list('factors', ForexFactor.fromJson),
      risks: j.strings('risks'),
      assumptions: j.strings('assumptions'),
      adjustments: j.strings('adjustments'),
      spreadPips: j.object('costs').has('spread_pips')
          ? j.object('costs').decimal('spread_pips')
          : null,
      dataTypes: j.object('freshness').strings('data_types'),
      forecastLabel: forecast?.string('calibration'),
    );
  }

  final int? rank;
  final String instrument;
  final String tier;
  final String label;
  final String condition;
  final String type;
  final String scenario;
  final String risk;
  final Decimal score;
  final Decimal entry;
  final Decimal stop;
  final Decimal target;
  final Decimal riskReward;
  final DateTime levelsAsOf;
  final List<ForexFactor> factors;
  final List<String> risks;
  final List<String> assumptions;
  final List<String> adjustments;
  final Decimal? spreadPips;
  final List<String> dataTypes;
  final String? forecastLabel;

  String get pair => instrument.replaceAll('_', '/');
}

@immutable
class ForexFactor {
  const ForexFactor({
    required this.name,
    required this.contribution,
    required this.detail,
  });

  factory ForexFactor.fromJson(JsonReader j) => ForexFactor(
    name: j.string('name'),
    contribution: j.decimal('contribution'),
    detail: j.string('detail'),
  );

  final String name;
  final Decimal contribution;
  final String detail;
}

@immutable
class ForexRanking {
  const ForexRanking({
    required this.items,
    required this.excluded,
    required this.notice,
  });

  factory ForexRanking.fromJson(JsonReader j) => ForexRanking(
    items: j.list('items', ForexOpportunity.fromJson),
    excluded: j.list('excluded', ForexOpportunity.fromJson),
    notice: j.string('notice'),
  );

  final List<ForexOpportunity> items;
  final List<ForexOpportunity> excluded;
  final String notice;
}

@immutable
class ForexEvent {
  const ForexEvent({
    required this.id,
    required this.name,
    required this.currencies,
    required this.importance,
    required this.scheduledAt,
    required this.demo,
    this.actual,
    this.previous,
    this.forecast,
    this.unit,
  });

  factory ForexEvent.fromJson(JsonReader j) {
    final confirmed = j.object('confirmed');
    final expectation = j.object('expectation');
    return ForexEvent(
      id: j.string('id'),
      name: j.string('name'),
      currencies: j.strings('currencies'),
      importance: j.string('importance'),
      scheduledAt: j.timestamp('scheduled_at'),
      demo: j.boolean('is_demo'),
      actual: confirmed.stringOrNull('actual'),
      previous: confirmed.stringOrNull('previous'),
      forecast: expectation.stringOrNull('forecast'),
      unit: confirmed.stringOrNull('unit'),
    );
  }

  final String id;
  final String name;
  final List<String> currencies;
  final String importance;
  final DateTime scheduledAt;
  final bool demo;
  final String? actual;
  final String? previous;

  /// A consensus expectation: never a fact.
  final String? forecast;
  final String? unit;
}

/// The risk calculator's answer (server-computed).
@immutable
class ForexRiskResult {
  const ForexRiskResult({
    required this.lots,
    required this.units,
    required this.sizeStatus,
    required this.pipValuePerLot,
    required this.riskAmount,
    required this.lossAfterCosts,
    required this.profitAfterCosts,
    required this.riskRewardAfterCosts,
    required this.costsTotal,
    required this.margin,
    required this.leverage,
    required this.accountCurrency,
    required this.conversionPath,
    required this.warnings,
    required this.disclosures,
  });

  factory ForexRiskResult.fromJson(JsonReader j) {
    final outcome = j.object('outcome');
    return ForexRiskResult(
      lots: j.object('size').decimal('lots'),
      units: j.object('size').decimal('units'),
      sizeStatus: j.object('size').string('status'),
      pipValuePerLot: j.object('pip_value').decimal('per_lot_account_currency'),
      riskAmount: outcome.decimal('risk_amount'),
      lossAfterCosts: outcome.decimal('loss_after_costs'),
      profitAfterCosts: outcome.has('profit_after_costs')
          ? outcome.decimal('profit_after_costs')
          : null,
      riskRewardAfterCosts: outcome.has('risk_reward_after_costs')
          ? outcome.decimal('risk_reward_after_costs')
          : null,
      costsTotal: j.object('costs').decimal('total'),
      margin: j.object('margin').decimal('margin'),
      leverage: j.object('margin').decimal('position_leverage'),
      accountCurrency: j.string('account_currency'),
      conversionPath: j.object('conversion').string('path'),
      warnings: j.strings('warnings'),
      disclosures: j.strings('disclosures'),
    );
  }

  final Decimal lots;
  final Decimal units;
  final String sizeStatus;
  final Decimal pipValuePerLot;
  final Decimal riskAmount;
  final Decimal lossAfterCosts;
  final Decimal? profitAfterCosts;
  final Decimal? riskRewardAfterCosts;
  final Decimal costsTotal;
  final Decimal margin;
  final Decimal leverage;
  final String accountCurrency;
  final String conversionPath;
  final List<String> warnings;
  final List<String> disclosures;
}

@immutable
class ForexBacktestSummary {
  const ForexBacktestSummary({
    required this.instrument,
    required this.rule,
    required this.trades,
    required this.oosReturn,
    required this.profitFactor,
    required this.auditPassed,
    required this.periodStart,
    required this.periodEnd,
    required this.dataTypes,
  });

  factory ForexBacktestSummary.fromJson(JsonReader j) => ForexBacktestSummary(
    instrument: j.string('instrument'),
    rule: j.string('rule'),
    trades: j.integer('out_of_sample_trades'),
    oosReturn: j.decimal('out_of_sample_return'),
    profitFactor: j.has('out_of_sample_profit_factor')
        ? j.decimal('out_of_sample_profit_factor')
        : null,
    auditPassed: j.boolean('leakage_audit_passed'),
    periodStart: j.timestamp('period_start'),
    periodEnd: j.timestamp('period_end'),
    dataTypes: j.strings('data_types'),
  );

  final String instrument;
  final String rule;
  final int trades;

  /// A fraction (0.05 is 5%), net of costs.
  final Decimal oosReturn;
  final Decimal? profitFactor;
  final bool auditPassed;
  final DateTime periodStart;
  final DateTime periodEnd;
  final List<String> dataTypes;
}

/// A PAPER TRADING account: virtual money only.
@immutable
class PaperAccount {
  const PaperAccount({
    required this.id,
    required this.name,
    required this.currency,
    required this.active,
    required this.startingBalance,
    required this.startingBalanceIsDefault,
    required this.balance,
    required this.equity,
    required this.unrealised,
    required this.usedMargin,
    required this.freeMargin,
    required this.openPositions,
    required this.pendingOrders,
    required this.warnings,
    this.marginLevel,
  });

  factory PaperAccount.fromJson(JsonReader j) => PaperAccount(
    id: j.string('id'),
    name: j.string('name'),
    currency: j.string('currency'),
    active: j.string('status') == 'active',
    startingBalance: j.decimal('starting_balance'),
    startingBalanceIsDefault: j.boolean('starting_balance_is_default'),
    balance: j.decimal('balance'),
    equity: j.decimal('equity'),
    unrealised: j.decimal('unrealised_pnl'),
    usedMargin: j.decimal('used_margin'),
    freeMargin: j.decimal('free_margin'),
    openPositions: j.integer('open_positions'),
    pendingOrders: j.integer('pending_orders'),
    warnings: j.strings('warnings'),
    marginLevel: j.has('margin_level_percent')
        ? j.decimal('margin_level_percent')
        : null,
  );

  final String id;
  final String name;
  final String currency;
  final bool active;
  final Decimal startingBalance;
  final bool startingBalanceIsDefault;
  final Decimal balance;
  final Decimal equity;
  final Decimal unrealised;
  final Decimal usedMargin;
  final Decimal freeMargin;
  final int openPositions;
  final int pendingOrders;
  final List<String> warnings;
  final Decimal? marginLevel;
}

@immutable
class PaperPosition {
  const PaperPosition({
    required this.id,
    required this.instrument,
    required this.long,
    required this.lots,
    required this.open,
    required this.entryPrice,
    required this.entryAt,
    required this.stop,
    required this.kind,
    this.target,
    this.currentPrice,
    this.unrealised,
    this.exitPrice,
    this.exitAt,
    this.exitReason,
    this.realised,
    this.costs,
    this.strategyTag,
  });

  factory PaperPosition.fromJson(JsonReader j) => PaperPosition(
    id: j.string('id'),
    instrument: j.string('instrument'),
    long: j.string('side') == 'long',
    lots: j.decimal('lots'),
    open: j.string('status') == 'open',
    entryPrice: j.decimal('entry_price'),
    entryAt: j.timestamp('entry_at'),
    stop: j.decimal('stop'),
    kind: PriceKind.parse(j.string('data_type')),
    target: j.has('target') ? j.decimal('target') : null,
    currentPrice: j.has('current_price') ? j.decimal('current_price') : null,
    unrealised: j.has('unrealised_pnl') ? j.decimal('unrealised_pnl') : null,
    exitPrice: j.has('exit_price') ? j.decimal('exit_price') : null,
    exitAt: j.has('exit_at') ? j.timestamp('exit_at') : null,
    exitReason: j.stringOrNull('exit_reason'),
    realised: j.has('realised_pnl') ? j.decimal('realised_pnl') : null,
    costs: j.has('costs') ? j.decimal('costs') : null,
    strategyTag: j.stringOrNull('strategy_tag'),
  );

  final String id;
  final String instrument;
  final bool long;
  final Decimal lots;
  final bool open;
  final Decimal entryPrice;
  final DateTime entryAt;
  final Decimal stop;
  final PriceKind kind;
  final Decimal? target;
  final Decimal? currentPrice;
  final Decimal? unrealised;
  final Decimal? exitPrice;
  final DateTime? exitAt;
  final String? exitReason;
  final Decimal? realised;
  final Decimal? costs;
  final String? strategyTag;

  String get pair => instrument.replaceAll('_', '/');
}

@immutable
class PaperOrderRequest {
  const PaperOrderRequest({
    required this.instrument,
    required this.long,
    required this.lots,
    required this.stop,
    this.target,
    this.limitPrice,
    this.strategyTag,
  });

  final String instrument;
  final bool long;
  final Decimal lots;
  final Decimal stop;
  final Decimal? target;
  final Decimal? limitPrice;
  final String? strategyTag;

  Map<String, Object?> toJson() => {
    'instrument': instrument,
    'side': long ? 'long' : 'short',
    'order_type': limitPrice == null ? 'market' : 'limit',
    'lots': lots.toString(),
    'stop': stop.toString(),
    'target': ?target?.toString(),
    'limit_price': ?limitPrice?.toString(),
    'strategy_tag': ?strategyTag,
  };
}

@immutable
class PaperOrderResult {
  const PaperOrderResult({
    required this.filled,
    required this.warnings,
    required this.disclosures,
    this.position,
  });

  factory PaperOrderResult.fromJson(JsonReader j) => PaperOrderResult(
    filled: j.object('order').string('status') == 'filled',
    warnings: j.strings('warnings'),
    disclosures: j.strings('disclosures'),
    position: j.has('position')
        ? PaperPosition.fromJson(j.object('position'))
        : null,
  );

  final bool filled;
  final List<String> warnings;
  final List<String> disclosures;
  final PaperPosition? position;
}

@immutable
class JournalEntry {
  const JournalEntry({
    required this.id,
    required this.note,
    required this.tags,
    required this.createdAt,
    this.positionId,
  });

  factory JournalEntry.fromJson(JsonReader j) => JournalEntry(
    id: j.string('id'),
    note: j.string('note'),
    tags: j.strings('tags'),
    createdAt: j.timestamp('created_at'),
    positionId: j.stringOrNull('position_id'),
  );

  final String id;
  final String note;
  final List<String> tags;
  final DateTime createdAt;
  final String? positionId;
}

@immutable
class PaperPerformance {
  const PaperPerformance({
    required this.trades,
    required this.netPnl,
    required this.maxDrawdown,
    required this.returnOnStart,
    required this.currency,
    required this.seriesNote,
    this.winRate,
    this.profitFactor,
  });

  factory PaperPerformance.fromJson(JsonReader j) {
    final overall = j.object('overall');
    return PaperPerformance(
      trades: overall.integer('trades'),
      netPnl: overall.decimal('net_pnl'),
      maxDrawdown: j.decimal('max_drawdown'),
      returnOnStart: j.decimal('return_on_starting_balance'),
      currency: j.string('currency'),
      seriesNote: j.string('series_note'),
      winRate: overall.has('win_rate') ? overall.decimal('win_rate') : null,
      profitFactor: overall.has('profit_factor')
          ? overall.decimal('profit_factor')
          : null,
    );
  }

  final int trades;
  final Decimal netPnl;
  final Decimal maxDrawdown;
  final Decimal returnOnStart;
  final String currency;
  final String seriesNote;
  final Decimal? winRate;
  final Decimal? profitFactor;
}

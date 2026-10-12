import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';
import '../../../shared/design_system/components/evidence_source_chip.dart';
import '../../../shared/design_system/formatting/money.dart';

EvidenceSource _source(JsonReader r, DateTime asOf) => EvidenceSource(
  label: r.string('label'),
  provider: r.string('provider'),
  asOf: asOf,
);

/// A labelled fact such as "Expense ratio: 0.20%", ready-made text from the backend.
@immutable
class InvestmentFact {
  const InvestmentFact(this.label, this.value);

  factory InvestmentFact.fromJson(JsonReader r) =>
      InvestmentFact(r.string('label'), r.string('value'));

  final String label;
  final String value;
}

/// Facts that share one source and one as-of time.
@immutable
class SourcedFacts {
  const SourcedFacts({required this.items, required this.source});

  factory SourcedFacts.fromJson(JsonReader r) {
    final asOf = r.timestamp('as_of');
    return SourcedFacts(
      items: r.list('items', InvestmentFact.fromJson),
      source: _source(r.object('source'), asOf),
    );
  }

  final List<InvestmentFact> items;
  final EvidenceSource source;
}

@immutable
class IncomeEvent {
  const IncomeEvent({
    required this.date,
    required this.kind,
    required this.amount,
  });

  factory IncomeEvent.fromJson(JsonReader r) {
    final day = r.date('date');
    return IncomeEvent(
      date: DateTime(day.year, day.month, day.day),
      kind: r.string('kind'),
      amount: r.money('amount'),
    );
  }

  final DateTime date;
  final String kind;
  final Money amount;
}

/// What the investment has paid out. The yield is the backend's figure; nothing is projected.
@immutable
class IncomeInfo {
  const IncomeInfo({
    required this.yieldPercent,
    required this.frequency,
    required this.events,
    required this.source,
  });

  factory IncomeInfo.fromJson(JsonReader r) => IncomeInfo(
    yieldPercent: r.decimal('yield_percent'),
    frequency: r.string('frequency'),
    events: r.list('events', IncomeEvent.fromJson),
    source: _source(r.object('source'), r.timestamp('as_of')),
  );

  final Decimal yieldPercent;
  final String frequency;
  final List<IncomeEvent> events;
  final EvidenceSource source;
}

/// The holding in this investment, as calculated by the backend.
@immutable
class PositionInfo {
  const PositionInfo({
    required this.quantity,
    required this.averageCost,
    required this.costBasis,
    required this.value,
    required this.nativeValue,
    required this.unrealisedPl,
    required this.unrealisedPlPercent,
    required this.asOf,
    this.portfolioName,
  });

  factory PositionInfo.fromJson(JsonReader r) => PositionInfo(
    quantity: r.decimal('quantity'),
    averageCost: r.money('average_cost'),
    costBasis: r.money('cost_basis'),
    value: r.money('value'),
    nativeValue: r.money('native_value'),
    unrealisedPl: r.money('unrealised_pl'),
    unrealisedPlPercent: r.decimal('unrealised_pl_percent'),
    asOf: r.timestamp('as_of'),
  );

  final Decimal quantity;

  /// Null when nothing has been bought yet.
  final Money? averageCost;
  final Money costBasis;

  /// In the portfolio currency, and in the asset's own currency.
  /// Null when the position is unpriced (shown as "No value yet", never zero).
  final Money? value;
  final Money? nativeValue;

  /// Null when the backend does not supply it; never worked out in the app.
  final Money? unrealisedPl;
  final Decimal? unrealisedPlPercent;
  final DateTime? asOf;

  /// The portfolio holding this position (live data, where one asset can sit in several).
  final String? portfolioName;
}

@immutable
class ResearchNote {
  const ResearchNote({
    required this.title,
    required this.summary,
    required this.source,
  });

  factory ResearchNote.fromJson(JsonReader r) => ResearchNote(
    title: r.string('title'),
    summary: r.string('summary'),
    source: _source(r.object('source'), r.timestamp('as_of')),
  );

  final String title;
  final String summary;
  final EvidenceSource source;
}

/// Everything the detail screen shows about one investment.
@immutable
class InvestmentDetail {
  const InvestmentDetail({
    required this.symbol,
    required this.name,
    required this.assetClass,
    required this.currency,
    required this.price,
    required this.changePercent,
    required this.priceSource,
    required this.fundamentals,
    required this.income,
    required this.positions,
    required this.research,
  });

  factory InvestmentDetail.fromJson(JsonReader r) {
    final price = r.object('price');
    final priceAsOf = price.timestamp('as_of');
    return InvestmentDetail(
      symbol: r.string('symbol'),
      name: r.string('name'),
      assetClass: r.string('asset_class'),
      currency: r.string('currency'),
      price: price.money('value'),
      changePercent: price.decimal('change_percent'),
      priceSource: _source(price.object('source'), priceAsOf),
      fundamentals: SourcedFacts.fromJson(r.object('fundamentals')),
      income: r.has('income') ? IncomeInfo.fromJson(r.object('income')) : null,
      positions: [PositionInfo.fromJson(r.object('position'))],
      research: r.list('research', ResearchNote.fromJson),
    );
  }

  /// Null for user-defined assets without a ticker.
  final String? symbol;
  final String name;
  final String assetClass;

  /// The asset's own currency.
  final String currency;

  /// The latest price per unit, in [currency].
  /// Null until a market price exists for the asset (never invented).
  final Money? price;
  final Decimal? changePercent;
  final EvidenceSource? priceSource;

  /// Null when no provider supplies fundamentals for the asset.
  final SourcedFacts? fundamentals;
  final IncomeInfo? income;

  /// One per portfolio that holds the asset; empty when none does.
  final List<PositionInfo> positions;
  final List<ResearchNote> research;
}

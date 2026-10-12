import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';
import '../../../shared/design_system/components/transaction_tile.dart';
import '../../../shared/design_system/formatting/money.dart';

DateTime _day(DateTime utcMidnight) =>
    DateTime(utcMidnight.year, utcMidnight.month, utcMidnight.day);

@immutable
class NetWorthItem {
  const NetWorthItem({
    required this.label,
    required this.kind,
    required this.value,
    this.sharePercent,
  });

  factory NetWorthItem.fromJson(JsonReader r) => NetWorthItem(
    label: r.string('label'),
    kind: r.string('kind'),
    value: r.money('value'),
    sharePercent: r.has('share_percent') ? r.decimal('share_percent') : null,
  );

  final String label;

  /// `investments`, `cash`, `property`, `loan`, ... (the backend's category).
  final String kind;
  final Money value;

  /// Share of total assets, from the server (assets only).
  final Decimal? sharePercent;
}

@immutable
class NetWorthSection {
  const NetWorthSection({required this.total, required this.items});

  factory NetWorthSection.fromJson(JsonReader r) => NetWorthSection(
    total: r.money('total'),
    items: r.list('items', NetWorthItem.fromJson),
  );

  final Money total;
  final List<NetWorthItem> items;
}

/// Net worth and what it is made of. All figures are the backend's.
@immutable
class NetWorthDetail {
  const NetWorthDetail({
    required this.netWorth,
    required this.assets,
    required this.liabilities,
    required this.asOf,
    this.complete = true,
  });

  factory NetWorthDetail.fromJson(JsonReader r) => NetWorthDetail(
    netWorth: r.money('net_worth'),
    assets: NetWorthSection.fromJson(r.object('assets')),
    liabilities: NetWorthSection.fromJson(r.object('liabilities')),
    asOf: r.timestamp('as_of'),
  );

  final Money netWorth;
  final NetWorthSection assets;
  final NetWorthSection liabilities;
  final DateTime asOf;

  /// False when some assets are unpriced or amounts could not be converted.
  final bool complete;
}

@immutable
class IncomeSource {
  const IncomeSource({
    required this.label,
    required this.yearly,
    required this.sharePercent,
  });

  factory IncomeSource.fromJson(JsonReader r) => IncomeSource(
    label: r.string('label'),
    yearly: r.money('yearly'),
    sharePercent: r.decimal('share_percent'),
  );

  final String label;
  final Money yearly;

  /// Null when the server gives no share (it is not worked out in the app).
  final Decimal? sharePercent;
}

@immutable
class IncomePayment {
  const IncomePayment({
    required this.date,
    required this.kind,
    required this.assetName,
    required this.amount,
    this.transactionKind,
  });

  factory IncomePayment.fromJson(JsonReader r) => IncomePayment(
    date: _day(r.date('date')),
    kind: r.string('kind'),
    assetName: r.string('asset_name'),
    amount: r.money('amount'),
  );

  final DateTime date;

  /// Display text in DEMO data; empty in live data, where [transactionKind] is set instead.
  final String kind;
  final TransactionKind? transactionKind;
  final String assetName;
  final Money amount;
}

/// Income received, by source, with the latest payments. It is a record of the past, not a forecast.
@immutable
class IncomeDetail {
  const IncomeDetail({
    required this.monthly,
    required this.yearly,
    required this.bySource,
    required this.recent,
    required this.asOf,
    this.complete = true,
  });

  factory IncomeDetail.fromJson(JsonReader r) => IncomeDetail(
    monthly: r.money('monthly'),
    yearly: r.money('yearly'),
    bySource: r.list('by_source', IncomeSource.fromJson),
    recent: r.list('recent', IncomePayment.fromJson),
    asOf: r.timestamp('as_of'),
  );

  final Money monthly;
  final Money yearly;
  final List<IncomeSource> bySource;
  final List<IncomePayment> recent;
  final DateTime asOf;

  /// False when income in some currency could not be converted.
  final bool complete;
}

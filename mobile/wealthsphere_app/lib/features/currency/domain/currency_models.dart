import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../core/data/json_reader.dart';
import '../../../shared/design_system/formatting/money.dart';

/// A currency figures can be reported in (`GET /api/v1/currencies`).
@immutable
class SupportedCurrency {
  const SupportedCurrency({
    required this.code,
    required this.name,
    required this.symbol,
    required this.decimalPlaces,
  });

  factory SupportedCurrency.fromJson(JsonReader r) => SupportedCurrency(
    code: r.string('code'),
    name: r.string('name'),
    symbol: r.string('symbol'),
    decimalPlaces: r.integer('decimal_places'),
  );

  final String code;
  final String name;
  final String symbol;
  final int decimalPlaces;

  /// Whether [query] matches the code or the name (case-insensitive).
  bool matches(String query) {
    final q = query.trim().toLowerCase();
    return q.isEmpty ||
        code.toLowerCase().contains(q) ||
        name.toLowerCase().contains(q);
  }
}

/// The user's reporting currency, stored on the server so every device shows the same one.
@immutable
class CurrencyPreferences {
  CurrencyPreferences({
    required this.reportingCurrency,
    required List<String> recentCurrencies,
    required this.isDefault,
  }) : recentCurrencies = List.unmodifiable(recentCurrencies);

  factory CurrencyPreferences.fromJson(JsonReader r) => CurrencyPreferences(
    reportingCurrency: r.string('reporting_currency'),
    recentCurrencies: r.strings('recent_currencies'),
    isDefault: r.boolean('is_default'),
  );

  final String reportingCurrency;
  final List<String> recentCurrencies;

  /// True until the user chooses (the server then uses the profile's base currency).
  final bool isDefault;
}

/// A rate's freshness, as the server labels it. Cached data is never shown as current.
enum FxRateStatus {
  current,
  cached,
  stale,
  unavailable;

  /// Worse statuses sort later.
  static FxRateStatus worst(Iterable<FxRateStatus> statuses) =>
      statuses.fold(FxRateStatus.current, (a, b) => a.index >= b.index ? a : b);
}

/// One currency against the pivot: 1 pivot = [rate] [currency].
@immutable
class FxRateLine {
  const FxRateLine({
    required this.currency,
    required this.status,
    this.rate,
    this.provider,
    this.rateTimestamp,
    this.retrievedAt,
  });

  factory FxRateLine.fromJson(JsonReader r) => FxRateLine(
    currency: r.string('currency'),
    status: r.enumByName('status', FxRateStatus.values),
    rate: r.has('rate') ? r.decimal('rate') : null,
    provider: r.stringOrNull('provider'),
    rateTimestamp: r.has('rate_timestamp')
        ? r.timestamp('rate_timestamp')
        : null,
    retrievedAt: r.has('retrieved_at') ? r.timestamp('retrieved_at') : null,
  );

  final String currency;
  final FxRateStatus status;
  final Decimal? rate;
  final String? provider;
  final DateTime? rateTimestamp;
  final DateTime? retrievedAt;
}

/// The reporting-currency rates and how fresh they are (`GET /api/v1/fx/status`).
@immutable
class FxStatus {
  FxStatus({
    required this.pivotCurrency,
    required this.checkedAt,
    required List<FxRateLine> rates,
  }) : rates = List.unmodifiable(rates);

  factory FxStatus.fromJson(JsonReader r) => FxStatus(
    pivotCurrency: r.string('pivot_currency'),
    checkedAt: r.timestamp('checked_at'),
    rates: r.list('rates', FxRateLine.fromJson),
  );

  final String pivotCurrency;
  final DateTime checkedAt;
  final List<FxRateLine> rates;

  /// The worst status of the rates that exist; unavailable when none does.
  FxRateStatus get overall {
    final known = [
      for (final r in rates)
        if (r.status != FxRateStatus.unavailable) r.status,
    ];
    return known.isEmpty ? FxRateStatus.unavailable : FxRateStatus.worst(known);
  }

  /// Who published the rates shown, each once, in name order.
  List<String> get providers =>
      {for (final r in rates) ?r.provider}.toList()..sort();

  /// When the newest rate was fetched.
  DateTime? get lastUpdated {
    final times = [
      for (final r in rates)
        if (r.retrievedAt != null) r.retrievedAt!,
    ];
    return times.isEmpty ? null : times.reduce((a, b) => a.isAfter(b) ? a : b);
  }
}

/// A conversion by the server (`POST /api/v1/fx/convert`). The app never multiplies amounts by
/// rates itself.
@immutable
class Conversion {
  Conversion({
    required this.source,
    required this.converted,
    required this.rate,
    required List<String>? path,
    required this.status,
    required this.rateTimestamp,
    required List<String> providers,
    required this.notice,
  }) : path = path == null ? null : List.unmodifiable(path),
       providers = List.unmodifiable(providers);

  factory Conversion.fromJson(JsonReader r, {String? notice}) => Conversion(
    source: r.money('source'),
    converted: r.money('converted'),
    rate: r.decimal('rate'),
    path: r.has('path') ? r.strings('path') : null,
    status: r.enumByName('status', FxRateStatus.values),
    rateTimestamp: r.has('rate_timestamp')
        ? r.timestamp('rate_timestamp')
        : null,
    providers: r.strings('providers'),
    notice: r.stringOrNull('notice') ?? notice ?? '',
  );

  final Money source;
  final Money converted;

  /// 1 unit of the source currency in the target currency.
  final Decimal rate;
  final List<String>? path;
  final FxRateStatus status;
  final DateTime? rateTimestamp;
  final List<String> providers;
  final String notice;
}

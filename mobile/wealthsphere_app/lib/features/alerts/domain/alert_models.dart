import 'package:decimal/decimal.dart';
import 'package:flutter/foundation.dart';

import '../../../shared/design_system/formatting/money.dart';

/// An investment the user follows, with the latest stored price (never live, never invented).
@immutable
class WatchItem {
  const WatchItem({
    required this.assetKey,
    required this.name,
    this.symbol,
    this.price,
    this.priceAsOf,
    this.provider,
    this.stale = false,
  });

  /// What the investment screen is opened with: the asset id (live) or the symbol (DEMO).
  final String assetKey;
  final String? symbol;
  final String name;

  /// Null when no price is stored for the asset: shown as "No market price yet".
  final Money? price;
  final DateTime? priceAsOf;
  final String? provider;

  /// Older than its freshness window: shown, and labelled out of date.
  final bool stale;
}

enum AlertType {
  priceAbove('price_above'),
  priceBelow('price_below'),
  allocationAbove('allocation_above');

  const AlertType(this.apiName);

  final String apiName;

  static AlertType parse(String apiName) => values.firstWhere(
    (t) => t.apiName == apiName,
    orElse: () => throw FormatException('Unknown alert type "$apiName"'),
  );
}

enum AlertStatus {
  active,
  triggered,
  paused;

  static AlertStatus parse(String name) => values.firstWhere(
    (s) => s.name == name,
    orElse: () => throw FormatException('Unknown alert status "$name"'),
  );
}

/// An alert the user set. It fires once (one event) and then waits to be re-armed.
@immutable
class PriceAlert {
  const PriceAlert({
    required this.id,
    required this.type,
    required this.status,
    required this.createdAt,
    this.assetKey,
    this.assetName,
    this.assetSymbol,
    this.thresholdPrice,
    this.assetClass,
    this.thresholdPercent,
    this.triggeredAt,
    this.note,
  });

  final String id;
  final AlertType type;
  final AlertStatus status;
  final DateTime createdAt;
  final String? assetKey;
  final String? assetName;
  final String? assetSymbol;

  /// Price alerts: in the asset's own currency.
  final Money? thresholdPrice;

  /// Allocation alerts: the asset class and its share of the portfolio, in percent.
  final String? assetClass;
  final Decimal? thresholdPercent;
  final DateTime? triggeredAt;
  final String? note;
}

/// What the user wants to be told about. Turning one off stops those alerts being checked.
@immutable
class AlertPreferences {
  const AlertPreferences({
    this.alertsEnabled = true,
    this.priceAlertsEnabled = true,
    this.allocationAlertsEnabled = true,
  });

  final bool alertsEnabled;
  final bool priceAlertsEnabled;
  final bool allocationAlertsEnabled;

  AlertPreferences copyWith({
    bool? alertsEnabled,
    bool? priceAlertsEnabled,
    bool? allocationAlertsEnabled,
  }) => AlertPreferences(
    alertsEnabled: alertsEnabled ?? this.alertsEnabled,
    priceAlertsEnabled: priceAlertsEnabled ?? this.priceAlertsEnabled,
    allocationAlertsEnabled:
        allocationAlertsEnabled ?? this.allocationAlertsEnabled,
  );

  @override
  bool operator ==(Object other) =>
      other is AlertPreferences &&
      other.alertsEnabled == alertsEnabled &&
      other.priceAlertsEnabled == priceAlertsEnabled &&
      other.allocationAlertsEnabled == allocationAlertsEnabled;

  @override
  int get hashCode =>
      Object.hash(alertsEnabled, priceAlertsEnabled, allocationAlertsEnabled);
}

/// An alert that fired: what the server observed and when.
@immutable
class AlertEvent {
  const AlertEvent({
    required this.id,
    required this.alertId,
    required this.type,
    required this.observedValue,
    required this.observedAsOf,
    required this.triggeredAt,
    this.seenAt,
  });

  final String id;
  final String alertId;
  final AlertType type;

  /// The price (price alerts) or the class's share in percent (allocation alerts).
  final Decimal observedValue;
  final DateTime observedAsOf;
  final DateTime triggeredAt;
  final DateTime? seenAt;

  bool get seen => seenAt != null;
}

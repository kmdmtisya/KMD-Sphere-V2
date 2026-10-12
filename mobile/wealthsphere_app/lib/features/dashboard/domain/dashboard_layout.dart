import 'dart:convert';

import 'package:flutter/foundation.dart';

/// The sections of the Home dashboard, in their default order.
enum DashboardSection { wealthSummary, metrics, insight, goals }

/// Which dashboard sections are shown and in what order (personalisation, stored on the device).
@immutable
class DashboardLayout {
  DashboardLayout({
    required List<DashboardSection> order,
    required Set<DashboardSection> hidden,
  }) : order = List.unmodifiable(order),
       hidden = Set.unmodifiable(hidden);

  /// Every section, visible, in the default order.
  factory DashboardLayout.initial() =>
      DashboardLayout(order: DashboardSection.values, hidden: const {});

  /// Reads stored JSON defensively: unknown sections are dropped, missing ones are appended, and
  /// anything unparseable falls back to the default layout instead of crashing the app.
  factory DashboardLayout.fromJsonString(String? text) {
    if (text == null || text.isEmpty) return DashboardLayout.initial();
    try {
      final decoded = jsonDecode(text);
      if (decoded is! Map<String, dynamic>) return DashboardLayout.initial();
      return DashboardLayout.fromNames(
        order: [for (final n in (decoded['order'] as List? ?? const [])) '$n'],
        hidden: [
          for (final n in (decoded['hidden'] as List? ?? const [])) '$n',
        ],
      );
    } on Object {
      return DashboardLayout.initial();
    }
  }

  /// Builds a layout from section names (as stored on the device and in the account): unknown
  /// names are dropped and missing sections are appended.
  factory DashboardLayout.fromNames({
    required List<String> order,
    required List<String> hidden,
  }) {
    final byName = {for (final s in DashboardSection.values) s.name: s};
    final sections = <DashboardSection>[for (final n in order) ?byName[n]];
    for (final s in DashboardSection.values) {
      if (!sections.contains(s)) sections.add(s);
    }
    return DashboardLayout(
      order: sections.toSet().toList(),
      hidden: {for (final n in hidden) ?byName[n]},
    );
  }

  final List<DashboardSection> order;
  final Set<DashboardSection> hidden;

  List<DashboardSection> get visible => [
    for (final s in order)
      if (!hidden.contains(s)) s,
  ];

  /// Moves [section] by [delta] positions (negative = up). Out-of-range moves are ignored.
  DashboardLayout move(DashboardSection section, int delta) {
    final from = order.indexOf(section);
    final to = from + delta;
    if (from < 0 || to < 0 || to >= order.length) return this;
    final next = [...order]..removeAt(from);
    next.insert(to, section);
    return DashboardLayout(order: next, hidden: hidden);
  }

  DashboardLayout withVisibility(
    DashboardSection section, {
    required bool visible,
  }) => DashboardLayout(
    order: order,
    hidden: visible ? ({...hidden}..remove(section)) : {...hidden, section},
  );

  String toJsonString() => jsonEncode({
    'order': [for (final s in order) s.name],
    'hidden': [for (final s in hidden) s.name],
  });

  @override
  bool operator ==(Object other) =>
      other is DashboardLayout &&
      listEquals(other.order, order) &&
      setEquals(other.hidden, hidden);

  @override
  int get hashCode =>
      Object.hash(Object.hashAll(order), Object.hashAll(hidden));
}

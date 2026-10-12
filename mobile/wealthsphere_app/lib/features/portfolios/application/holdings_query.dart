import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/domain/wealth_models.dart';

enum HoldingSort { valueDesc, valueAsc, nameAsc, changeDesc, changeAsc }

/// What the user asked of the holdings list: a search text, one asset class (or all) and a sort.
/// Filtering and sorting only arrange figures the backend already computed.
class HoldingsQuery {
  const HoldingsQuery({
    this.search = '',
    this.assetClass,
    this.sort = HoldingSort.valueDesc,
  });

  final String search;

  /// The asset class to show, or null for all.
  final String? assetClass;
  final HoldingSort sort;

  bool get isFiltered => search.trim().isNotEmpty || assetClass != null;

  HoldingsQuery copyWith({
    String? search,
    Object? assetClass = _keep,
    HoldingSort? sort,
  }) => HoldingsQuery(
    search: search ?? this.search,
    assetClass: identical(assetClass, _keep)
        ? this.assetClass
        : assetClass as String?,
    sort: sort ?? this.sort,
  );

  static const Object _keep = Object();

  @override
  bool operator ==(Object other) =>
      other is HoldingsQuery &&
      other.search == search &&
      other.assetClass == assetClass &&
      other.sort == sort;

  @override
  int get hashCode => Object.hash(search, assetClass, sort);
}

class HoldingsQueryNotifier extends Notifier<HoldingsQuery> {
  @override
  HoldingsQuery build() => const HoldingsQuery();

  void search(String text) => state = state.copyWith(search: text);
  void filter(String? assetClass) =>
      state = state.copyWith(assetClass: assetClass);
  void sortBy(HoldingSort sort) => state = state.copyWith(sort: sort);
  void clearFilters() =>
      state = HoldingsQuery(sort: state.sort); // keeps the chosen sort
}

final holdingsQueryProvider =
    NotifierProvider<HoldingsQueryNotifier, HoldingsQuery>(
      HoldingsQueryNotifier.new,
    );

/// The asset classes present, in order of first appearance (stable for the chips).
List<String> assetClassesOf(List<HoldingSummary> holdings) => [
  for (final c in {for (final h in holdings) h.assetClass}) c,
];

/// [holdings] matching [query], sorted. A search matches the name or symbol, ignoring case and
/// surrounding spaces. Ties keep a stable order (by symbol) so the list never jumps.
List<HoldingSummary> applyQuery(
  List<HoldingSummary> holdings,
  HoldingsQuery query,
) {
  final needle = query.search.trim().toLowerCase();
  final matching = [
    for (final h in holdings)
      if ((query.assetClass == null || h.assetClass == query.assetClass) &&
          (needle.isEmpty ||
              h.name.toLowerCase().contains(needle) ||
              (h.symbol ?? '').toLowerCase().contains(needle)))
        h,
  ];
  int byName(HoldingSummary a, HoldingSummary b) =>
      a.name.toLowerCase().compareTo(b.name.toLowerCase());
  int tie(HoldingSummary a, HoldingSummary b) =>
      (a.symbol ?? a.name).compareTo(b.symbol ?? b.name);
  // Positions without a value or change sort last in both directions.
  int byNullable<T extends Comparable<Object>>(
    T? a,
    T? b, {
    required bool desc,
  }) {
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    return desc ? b.compareTo(a) : a.compareTo(b);
  }

  matching.sort((a, b) {
    final order = switch (query.sort) {
      HoldingSort.valueDesc => byNullable(
        a.value?.amount,
        b.value?.amount,
        desc: true,
      ),
      HoldingSort.valueAsc => byNullable(
        a.value?.amount,
        b.value?.amount,
        desc: false,
      ),
      HoldingSort.nameAsc => byName(a, b),
      HoldingSort.changeDesc => byNullable(
        a.changePercent,
        b.changePercent,
        desc: true,
      ),
      HoldingSort.changeAsc => byNullable(
        a.changePercent,
        b.changePercent,
        desc: false,
      ),
    };
    return order != 0 ? order : tie(a, b);
  });
  return matching;
}

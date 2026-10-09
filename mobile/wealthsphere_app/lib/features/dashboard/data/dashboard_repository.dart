import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../../../core/preferences/preferences_store.dart';
import '../../../shared/domain/wealth_models.dart';
import '../domain/dashboard_layout.dart';

/// Home dashboard data. Each section loads on its own so one failure does not blank the page.
abstract interface class DashboardRepository {
  Future<String> greetingName();
  Future<NetWorthSummary> netWorth();
  Future<IncomeSummary> income();
  Future<GoalsSummary> goals();
  Future<InsightSummary> insight();
}

/// Reads `assets/demo/dashboard.json`.
class DemoDashboardRepository implements DashboardRepository {
  DemoDashboardRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;

  Future<JsonReader> _doc() async {
    await _gate();
    return JsonReader(await _assets.load('dashboard.json'));
  }

  @override
  Future<String> greetingName() async =>
      (await _doc()).object('greeting').string('name');

  @override
  Future<NetWorthSummary> netWorth() async =>
      NetWorthSummary.fromJson((await _doc()).object('net_worth'));

  @override
  Future<IncomeSummary> income() async =>
      IncomeSummary.fromJson((await _doc()).object('income'));

  @override
  Future<GoalsSummary> goals() async =>
      GoalsSummary.fromJson((await _doc()).object('goals'));

  @override
  Future<InsightSummary> insight() async =>
      InsightSummary.fromJson((await _doc()).object('insight'));
}

final dashboardRepositoryProvider = Provider<DashboardRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoDashboardRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
  }
});

/// Where the personalised dashboard layout is kept.
abstract interface class DashboardLayoutRepository {
  Future<DashboardLayout> load();
  Future<void> save(DashboardLayout layout);
}

/// Stores the layout in on-device UI preferences. (At gate 4 this also syncs to
/// `PATCH /me/preferences`.) It holds no financial data.
class LocalDashboardLayoutRepository implements DashboardLayoutRepository {
  const LocalDashboardLayoutRepository(this._store);

  static const String key = 'dashboard_layout';

  final PreferencesStore _store;

  @override
  Future<DashboardLayout> load() async =>
      DashboardLayout.fromJsonString(await _store.getString(key));

  @override
  Future<void> save(DashboardLayout layout) =>
      _store.setString(key, layout.toJsonString());
}

final dashboardLayoutRepositoryProvider = Provider<DashboardLayoutRepository>(
  (ref) => LocalDashboardLayoutRepository(ref.watch(preferencesStoreProvider)),
);

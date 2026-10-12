import '../../../core/network/api_exception.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/domain/wealth_models.dart';
import '../domain/dashboard_layout.dart';
import 'dashboard_repository.dart';

/// Home dashboard data from the API. Net worth, income and goals are the server's summaries as
/// they are; the app adds nothing up.
class LiveDashboardRepository extends LiveRepository
    implements DashboardRepository {
  const LiveDashboardRepository(super.dio, {this.fallbackName = 'there'});

  /// Shown when the account has neither a display name nor an email.
  final String fallbackName;

  @override
  Future<String> greetingName() => getObject('/api/v1/me', (r) {
    final display = r.stringOrNull('display_name')?.trim();
    if (display != null && display.isNotEmpty) return display;
    final email = r.stringOrNull('email');
    final local = email?.split('@').first.trim();
    return local == null || local.isEmpty ? fallbackName : local;
  });

  @override
  Future<NetWorthSummary> netWorth() =>
      getObject('/api/v1/net-worth', NetWorthSummary.fromJson);

  @override
  Future<IncomeSummary> income() =>
      getObject('/api/v1/income/summary', IncomeSummary.fromJson);

  @override
  Future<GoalsSummary> goals() =>
      getObject('/api/v1/goals/summary', GoalsSummary.fromJson);

  /// AI insights arrive with the AI orchestrator (P10-T06); until then there is none, and Home
  /// shows nothing rather than an invented sentence.
  @override
  Future<InsightSummary?> insight() async => null;
}

/// Keeps the dashboard layout on the device and in the account (`PATCH /me/preferences`), so it
/// follows the user to another device.
///
/// The device copy is always written first and is what is shown when the server cannot be
/// reached. When the account has a layout it wins on load; when it has none, the device layout
/// stays and is sent on the next change.
class SyncedDashboardLayoutRepository extends LiveRepository
    implements DashboardLayoutRepository {
  const SyncedDashboardLayoutRepository(super.dio, this._local);

  final DashboardLayoutRepository _local;

  @override
  Future<DashboardLayout> load() async {
    final DashboardLayout? remote;
    try {
      remote = await getObject('/api/v1/me', (r) {
        final layout = r.object('preferences');
        if (!layout.has('dashboard_layout')) return null;
        final l = layout.object('dashboard_layout');
        return DashboardLayout.fromNames(
          order: l.strings('order'),
          hidden: l.has('hidden') ? l.strings('hidden') : const [],
        );
      });
    } on ApiException {
      return _local.load(); // offline or signed out: the device copy
    }
    if (remote == null) return _local.load();
    await _local.save(remote);
    return remote;
  }

  @override
  Future<void> save(DashboardLayout layout) async {
    await _local.save(layout);
    try {
      await sendEmpty(
        'PATCH',
        '/api/v1/me/preferences',
        body: {
          'dashboard_layout': {
            'order': [for (final s in layout.order) s.name],
            'hidden': [for (final s in layout.hidden) s.name],
          },
        },
      );
    } on ApiException {
      // Kept on the device; sent with the next change.
    }
  }
}

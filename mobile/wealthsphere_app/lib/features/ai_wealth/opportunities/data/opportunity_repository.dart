import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/data/demo_support.dart';
import '../../../../core/data/json_reader.dart';
import '../../../../core/l10n/l10n_provider.dart';
import '../../../../core/network/api_client.dart';
import '../domain/opportunity_models.dart';
import 'live_opportunity_repository.dart';

/// Research candidates from AI Investment Intelligence. Read-only: ideas to research, with no
/// call that places a trade.
abstract interface class OpportunityRepository {
  Future<OpportunityList> opportunities();

  /// The side-by-side facts of [ids], by id (the ideas' own facts in demo mode).
  Future<Map<String, List<OpportunityAttribute>>> compare(List<String> ids);
}

/// Reads `assets/demo/opportunities.json`: mock ideas, never live market data.
class DemoOpportunityRepository implements OpportunityRepository {
  DemoOpportunityRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;

  @override
  Future<OpportunityList> opportunities() async {
    await _gate();
    return OpportunityList.fromJson(
      JsonReader(await _assets.load('opportunities.json')),
    );
  }

  @override
  Future<Map<String, List<OpportunityAttribute>>> compare(
    List<String> ids,
  ) async {
    final list = await opportunities();
    return {
      for (final id in ids)
        if (list.byId(id) case final c?) id: c.attributes,
    };
  }
}

/// Demo mode reads the mock ideas; live mode runs the server's opportunity pipeline (P12-T09),
/// whose instruments are still the fictional DEMO universe (every screen keeps its DEMO badge).
final opportunityRepositoryProvider = Provider<OpportunityRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoOpportunityRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
    case DataSourceMode.live:
      return LiveOpportunityRepository(
        ref.watch(apiClientProvider),
        ref.watch(l10nProvider),
      );
  }
});

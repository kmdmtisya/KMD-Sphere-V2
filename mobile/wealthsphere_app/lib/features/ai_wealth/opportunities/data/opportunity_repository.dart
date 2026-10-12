import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/data/demo_support.dart';
import '../../../../core/data/json_reader.dart';
import '../domain/opportunity_models.dart';

/// Research candidates from AI Investment Intelligence. Read-only: ideas to research, with no
/// call that places a trade.
abstract interface class OpportunityRepository {
  Future<OpportunityList> opportunities();
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
}

// The AI services arrive in P10. Until then these screens are DEMO in every data-source
// mode, and every one of them says so (DemoBadge); nothing here is presented as live.
final opportunityRepositoryProvider = Provider<OpportunityRepository>(
  (ref) => DemoOpportunityRepository(
    ref.watch(demoAssetsProvider),
    ref.read(demoBehaviorProvider.notifier).gate,
  ),
);

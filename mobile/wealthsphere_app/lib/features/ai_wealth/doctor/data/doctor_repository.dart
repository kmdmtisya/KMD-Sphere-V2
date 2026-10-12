import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/data/demo_support.dart';
import '../../../../core/data/json_reader.dart';
import '../domain/doctor_models.dart';

/// The Portfolio Doctor's report for a portfolio (or `consolidated` for all of them).
///
/// Read-only: it describes and illustrates, and has no call that places a trade.
abstract interface class DoctorRepository {
  Future<DoctorReport> report(String portfolioId);
}

/// Reads `assets/demo/doctor.json`.
class DemoDoctorRepository implements DoctorRepository {
  DemoDoctorRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;

  @override
  Future<DoctorReport> report(String portfolioId) async {
    await _gate();
    final doc = JsonReader(await _assets.load('doctor.json'));
    final reports = doc.mapOf('reports', (r) => r);
    final found = reports[portfolioId];
    if (found == null) {
      throw DataLoadException.unknown('portfolio', portfolioId);
    }
    return DoctorReport.fromJson(found);
  }
}

// The AI services arrive in P10. Until then these screens are DEMO in every data-source
// mode, and every one of them says so (DemoBadge); nothing here is presented as live.
final doctorRepositoryProvider = Provider<DoctorRepository>(
  (ref) => DemoDoctorRepository(
    ref.watch(demoAssetsProvider),
    ref.read(demoBehaviorProvider.notifier).gate,
  ),
);

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../shared/design_system/components/portfolio_health_card.dart';
import '../data/doctor_repository.dart';
import '../domain/doctor_models.dart';

final doctorReportProvider = FutureProvider.family<DoctorReport, String>(
  (ref, portfolioId) => ref.watch(doctorRepositoryProvider).report(portfolioId),
);

/// Which finding type the detail list shows; null shows all.
class DoctorKindFilter extends Notifier<HealthFindingKind?> {
  @override
  HealthFindingKind? build() => null;

  void select(HealthFindingKind? kind) => state = kind;
}

final doctorKindFilterProvider =
    NotifierProvider<DoctorKindFilter, HealthFindingKind?>(
      DoctorKindFilter.new,
    );

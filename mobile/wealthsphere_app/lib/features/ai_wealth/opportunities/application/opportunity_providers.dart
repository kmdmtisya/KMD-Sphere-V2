import 'package:decimal/decimal.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/input/decimal_input.dart';
import '../../../calculator/application/calculator_providers.dart';
import '../../../calculator/domain/forecast_input_limits.dart';
import '../../../forecast/domain/forecast_models.dart';
import '../data/opportunity_repository.dart';
import '../domain/opportunity_models.dart';

final opportunitiesProvider = FutureProvider<OpportunityList>(
  (ref) => ref.watch(opportunityRepositoryProvider).opportunities(),
);

/// The research category shown; null shows every category.
class OpportunityCategoryFilter extends Notifier<String?> {
  @override
  String? build() => null;

  void select(String? id) => state = id;
}

final opportunityCategoryProvider =
    NotifierProvider<OpportunityCategoryFilter, String?>(
      OpportunityCategoryFilter.new,
    );

/// The most ideas that can be compared side by side.
const int maxCompare = 3;

/// The ideas chosen for comparison, in the order they were chosen.
class CompareSelection extends Notifier<List<String>> {
  @override
  List<String> build() => const [];

  bool contains(String id) => state.contains(id);

  /// Adds [id], or removes it if chosen. Returns false when the limit stopped an addition.
  bool toggle(String id) {
    if (state.contains(id)) {
      state = [
        for (final s in state)
          if (s != id) s,
      ];
      return true;
    }
    if (state.length >= maxCompare) return false;
    state = [...state, id];
    return true;
  }

  void clear() => state = const [];
}

final compareSelectionProvider =
    NotifierProvider<CompareSelection, List<String>>(CompareSelection.new);

/// The candidates of [list] in [categoryId] (all when null), in the order given.
List<OpportunityCandidate> inCategory(
  OpportunityList list,
  String? categoryId,
) => [
  for (final c in list.candidates)
    if (categoryId == null || c.categoryId == categoryId) c,
];

/// Hands an idea's example assumptions to the calculator. The inputs are written in the user's
/// number format and the calculator is told they are example assumptions from [candidate], so it
/// marks them. Returns false when the idea has no assumptions to hand over.
bool simulateInCalculator(
  WidgetRef ref,
  OpportunityCandidate candidate,
  String locale,
) {
  final a = candidate.simulation;
  if (a == null) {
    if (!candidate.ownReturns) return false;
    // No example returns: the return fields are left empty for the user's own assumptions.
    final base = CalculatorInputs.defaults(locale);
    ref
        .read(calculatorInputsProvider.notifier)
        .replace(
          base.copyWith(
            texts: {
              ...base.texts,
              CalculatorField.annualReturn: '',
              CalculatorField.conservativeReturn: '',
              CalculatorField.growthReturn: '',
            },
          ),
        );
    ref.read(calculatorPrefillProvider.notifier).clear();
    return true;
  }
  final input = DecimalInput(locale);
  String t(Decimal v) => input.format(v);
  final base = CalculatorInputs.defaults(locale);
  ref
      .read(calculatorInputsProvider.notifier)
      .replace(
        base.copyWith(
          texts: {
            ...base.texts,
            CalculatorField.initialInvestment: t(a.initialInvestment),
            CalculatorField.monthlyContribution: t(a.monthlyContribution),
            CalculatorField.annualReturn: t(a.annualReturn),
            CalculatorField.conservativeReturn: t(a.conservativeReturn),
            CalculatorField.growthReturn: t(a.growthReturn),
            CalculatorField.years: a.years.toString(),
            CalculatorField.inflation: t(a.inflation),
            CalculatorField.annualFee: t(a.annualFee),
          },
          compounding: Frequency.monthly,
          contribution: Frequency.monthly,
        ),
      );
  ref
      .read(calculatorPrefillProvider.notifier)
      .set(
        CalculatorPrefill(
          sourceName: candidate.name,
          fields: const {
            CalculatorField.initialInvestment,
            CalculatorField.monthlyContribution,
            CalculatorField.annualReturn,
            CalculatorField.conservativeReturn,
            CalculatorField.growthReturn,
            CalculatorField.years,
            CalculatorField.inflation,
            CalculatorField.annualFee,
          },
        ),
      );
  return true;
}

/// The side-by-side facts of the chosen ideas, by idea id (P12-T09: live from the server).
final comparisonProvider =
    FutureProvider.family<Map<String, List<OpportunityAttribute>>, String>(
      (ref, ids) => ref
          .watch(opportunityRepositoryProvider)
          .compare(ids.split(',').where((id) => id.isNotEmpty).toList()),
    );

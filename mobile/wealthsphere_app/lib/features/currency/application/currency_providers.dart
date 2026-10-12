import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show ProviderOrFamily;

import '../../dashboard/application/dashboard_providers.dart';
import '../../goals/application/goal_providers.dart';
import '../../more/application/more_providers.dart';
import '../../portfolios/application/portfolio_providers.dart';
import '../data/currency_repository.dart';
import '../domain/currency_models.dart';

final currenciesProvider = FutureProvider<List<SupportedCurrency>>(
  (ref) => ref.watch(currencyRepositoryProvider).currencies(),
);

final fxStatusProvider = FutureProvider<FxStatus>(
  (ref) => ref.watch(currencyRepositoryProvider).status(),
);

/// Every provider whose figures are in the reporting currency. The server converts them; after a
/// switch they are asked for again and update in place (the old figures stay on screen while the
/// new ones load, so scroll position and navigation are kept).
void refreshReportingFigures(
  void Function(ProviderOrFamily provider) invalidate,
) {
  for (final provider in <ProviderOrFamily>[
    dashboardNetWorthProvider,
    dashboardIncomeProvider,
    dashboardGoalsProvider,
    homeSummaryProvider,
    homeSeriesProvider,
    portfolioSummaryProvider,
    netWorthDetailProvider,
    incomeDetailProvider,
    goalsProvider,
    goalProvider,
  ]) {
    invalidate(provider);
  }
}

/// The reporting currency. Choosing one saves it (on the server in live mode, so every device
/// follows) and refreshes every figure shown in it.
class ReportingCurrencyNotifier extends AsyncNotifier<CurrencyPreferences> {
  @override
  Future<CurrencyPreferences> build() =>
      ref.watch(currencyRepositoryProvider).preferences();

  /// Throws when the setting could not be saved; the current currency then stays.
  Future<void> select(String code) async {
    if (state.value?.reportingCurrency == code) return;
    final updated = await ref
        .read(currencyRepositoryProvider)
        .setReportingCurrency(code);
    state = AsyncData(updated);
    refreshReportingFigures(ref.invalidate);
  }
}

final reportingCurrencyProvider =
    AsyncNotifierProvider<ReportingCurrencyNotifier, CurrencyPreferences>(
      ReportingCurrencyNotifier.new,
    );

/// Asks the server for fresh rates, then shows the new status and figures.
Future<void> refreshRates(WidgetRef ref) async {
  await ref.read(currencyRepositoryProvider).refresh();
  ref.invalidate(fxStatusProvider);
  refreshReportingFigures(ref.invalidate);
}

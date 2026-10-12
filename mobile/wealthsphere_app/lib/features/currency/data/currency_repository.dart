import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../../../core/network/api_client.dart';
import '../../../core/preferences/preferences_store.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../domain/currency_models.dart';
import 'live_currency_repository.dart';

/// Reporting currency, rates and conversions (P11-T07). Live mode reads the API; conversions are
/// always the server's.
abstract interface class CurrencyRepository {
  Future<List<SupportedCurrency>> currencies();
  Future<CurrencyPreferences> preferences();
  Future<CurrencyPreferences> setReportingCurrency(String code);
  Future<FxStatus> status();

  /// Asks for fresh rates (the server limits how often) and returns the status after it.
  Future<FxStatus> refresh();

  /// Converts [amount] into [to] with the server's current rate.
  Future<Conversion> convert(Money amount, String to);
}

/// Reads `assets/demo/currency.json`. The demo keeps the chosen currency on the device only, and
/// converts the fixture's examples only (it never computes a conversion itself).
class DemoCurrencyRepository implements CurrencyRepository {
  DemoCurrencyRepository(this._assets, this._gate, this._store);

  final DemoAssets _assets;
  final Future<void> Function() _gate;
  final PreferencesStore _store;

  static const _key = 'demo.reporting_currency';

  Future<JsonReader> _doc() async {
    await _gate();
    return JsonReader(await _assets.load('currency.json'));
  }

  @override
  Future<List<SupportedCurrency>> currencies() async =>
      (await _doc()).list('currencies', SupportedCurrency.fromJson);

  @override
  Future<CurrencyPreferences> preferences() async {
    final fixture = CurrencyPreferences.fromJson(
      (await _doc()).object('preferences'),
    );
    final chosen = await _store.getString(_key);
    return chosen == null
        ? fixture
        : CurrencyPreferences(
            reportingCurrency: chosen,
            recentCurrencies: [
              if (chosen != fixture.reportingCurrency)
                fixture.reportingCurrency,
            ],
            isDefault: false,
          );
  }

  @override
  Future<CurrencyPreferences> setReportingCurrency(String code) async {
    final known = (await currencies()).any((c) => c.code == code);
    if (!known) throw DataLoadException('Unknown currency "$code"');
    await _store.setString(_key, code);
    return preferences();
  }

  @override
  Future<FxStatus> status() async =>
      FxStatus.fromJson((await _doc()).object('status'));

  @override
  Future<FxStatus> refresh() => status();

  @override
  Future<Conversion> convert(Money amount, String to) async {
    final doc = await _doc();
    final notice = doc.string('notice');
    for (final example in doc.list('examples', (r) => r)) {
      final source = example.money('source');
      if (source.currencyCode == amount.currencyCode &&
          source.amount == amount.amount &&
          example.object('converted').string('currency') == to) {
        return Conversion.fromJson(example, notice: notice);
      }
    }
    throw DataLoadException(notice);
  }

  /// The fixture's example conversions, offered as chips in demo mode.
  Future<List<(Money, String)>> examples() async => (await _doc()).list(
    'examples',
    (r) => (r.money('source'), r.object('converted').string('currency')),
  );
}

final currencyRepositoryProvider = Provider<CurrencyRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoCurrencyRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
        ref.watch(preferencesStoreProvider),
      );
    case DataSourceMode.live:
      return LiveCurrencyRepository(ref.watch(apiClientProvider));
  }
});

import '../../../core/network/live_repository.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../domain/currency_models.dart';
import 'currency_repository.dart';

/// The reporting currency over the API (P11-T06): the setting lives on the server, so every
/// device shows the same currency, and every figure the app shows is converted by the server.
class LiveCurrencyRepository extends LiveRepository
    implements CurrencyRepository {
  const LiveCurrencyRepository(super.dio);

  static const _preferences = '/api/v1/me/currency-preferences';

  @override
  Future<List<SupportedCurrency>> currencies() =>
      getList('/api/v1/currencies', SupportedCurrency.fromJson);

  @override
  Future<CurrencyPreferences> preferences() =>
      getObject(_preferences, CurrencyPreferences.fromJson);

  @override
  Future<CurrencyPreferences> setReportingCurrency(String code) => send(
    'PATCH',
    _preferences,
    CurrencyPreferences.fromJson,
    body: {'reporting_currency': code},
  );

  @override
  Future<FxStatus> status() =>
      getObject('/api/v1/fx/status', FxStatus.fromJson);

  @override
  Future<FxStatus> refresh() => send(
    'POST',
    '/api/v1/fx/refresh',
    (r) => FxStatus.fromJson(r.object('status')),
  );

  @override
  Future<Conversion> convert(Money amount, String to) => send(
    'POST',
    '/api/v1/fx/convert',
    Conversion.fromJson,
    body: {'amount': amount.toJson(), 'to': to},
  );
}

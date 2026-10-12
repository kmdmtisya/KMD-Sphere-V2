import '../../../core/data/json_reader.dart';
import '../../../core/network/live_repository.dart';
import '../../calculator/domain/forecast_input_limits.dart';
import '../domain/forecast_models.dart';
import 'forecast_repository.dart';

/// Projections from the backend forecast engine (`POST /api/v1/forecasts/scenarios`). Every
/// figure comes from the server; the app sends the inputs and shows what comes back (DEC-03).
///
/// The API calls the per-period amount `contribution` (it can be monthly, quarterly or yearly);
/// the app's DTO calls it `monthly_contribution`. The rename happens here, both ways, so the
/// echoed assumptions match the request exactly (docs/contracts/dto-mapping.md).
class LiveForecastRepository extends LiveRepository
    implements ForecastRepository {
  const LiveForecastRepository(super.dio);

  @override
  Future<CompoundForecastResponse> compound(CompoundForecastRequest request) =>
      send(
        'POST',
        '/api/v1/forecasts/scenarios',
        _response,
        body: toApi(request),
      );

  /// The calculator opens with the shared defaults (the same limits the backend enforces).
  @override
  Future<CompoundForecastRequest> defaultRequest() async =>
      ForecastInputLimits.defaults;

  /// The request body: the DTO with `monthly_contribution` sent as `contribution`.
  static Map<String, Object?> toApi(CompoundForecastRequest request) {
    final json = request.toJson();
    json['contribution'] = json.remove('monthly_contribution');
    return json;
  }

  static CompoundForecastResponse _response(JsonReader r) {
    final scenarios = r.object('scenarios');
    return CompoundForecastResponse(
      currencyCode: r.string('currency'),
      scenarios: {
        for (final kind in ForecastScenarioKind.values)
          kind: ScenarioResult.fromJson(kind, scenarios.object(kind.name)),
      },
      assumptions: _assumptions(r.object('assumptions')),
      asOf: r.timestamp('as_of'),
      notice: r.string('notice'),
    );
  }

  static CompoundForecastRequest _assumptions(JsonReader a) =>
      CompoundForecastRequest(
        initialInvestment: a.money('initial_investment'),
        monthlyContribution: a.money('contribution'),
        annualReturnPercent: a.decimal('annual_return_percent'),
        years: a.integer('years'),
        contributionGrowthPercent: a.decimal('contribution_growth_percent'),
        inflationPercent: a.decimal('inflation_percent'),
        annualFeePercent: a.decimal('annual_fee_percent'),
        compoundingFrequency: Frequency.parse(
          a.string('compounding_frequency'),
          a.path,
        ),
        contributionFrequency: Frequency.parse(
          a.string('contribution_frequency'),
          a.path,
        ),
        conservativeReturnPercent: a.decimal('conservative_return_percent'),
        growthReturnPercent: a.decimal('growth_return_percent'),
      );
}

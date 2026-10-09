import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../domain/forecast_models.dart';

/// Compound-growth forecasts, computed by the backend (the app does no projection maths).
abstract interface class ForecastRepository {
  Future<CompoundForecastResponse> compound(CompoundForecastRequest request);

  /// The inputs the calculator starts with.
  Future<CompoundForecastRequest> defaultRequest();
}

/// Returns the one canned response in `assets/demo/forecast.json` whatever the request is.
///
/// The response echoes the inputs it was computed from, so the screen can tell when it does not
/// match the user's inputs ([CompoundForecastResponse.matches]) and show a DEMO notice. Nothing
/// is projected in Dart (DEC-03).
class DemoForecastRepository implements ForecastRepository {
  DemoForecastRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;

  @override
  Future<CompoundForecastResponse> compound(
    CompoundForecastRequest request,
  ) async {
    await _gate();
    final doc = JsonReader(await _assets.load('forecast.json'));
    return CompoundForecastResponse.fromJson(doc.object('response'));
  }

  @override
  Future<CompoundForecastRequest> defaultRequest() async {
    final doc = JsonReader(await _assets.load('forecast.json'));
    return CompoundForecastRequest.fromJson(doc.object('request'));
  }
}

final forecastRepositoryProvider = Provider<ForecastRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoForecastRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
  }
});

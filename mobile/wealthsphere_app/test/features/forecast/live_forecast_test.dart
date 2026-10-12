import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:decimal/decimal.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/core/network/api_exception.dart';
import 'package:wealthsphere_app/features/calculator/domain/forecast_input_limits.dart';
import 'package:wealthsphere_app/features/forecast/data/forecast_repository.dart';
import 'package:wealthsphere_app/features/forecast/data/live_forecast_repository.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_router.dart';

/// A stand-in for the forecast engine: answers with the fixture's projections and echoes the
/// request as the assumptions, like the API does. Or fails with [status] / a dropped connection.
class _EngineAdapter implements HttpClientAdapter {
  _EngineAdapter({this.status = 200, this.offline = false});

  final int status;
  final bool offline;
  final List<Map<String, Object?>> bodies = [];

  static final Map<String, Object?> _projections =
      (jsonDecode(File('assets/demo/forecast.json').readAsStringSync())
              as Map<String, Object?>)['response']!
          as Map<String, Object?>;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (offline) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
      );
    }
    final bytes = <int>[];
    await for (final chunk in requestStream!) {
      bytes.addAll(chunk);
    }
    final body = jsonDecode(utf8.decode(bytes)) as Map<String, Object?>;
    bodies.add(body);
    final answer = status == 200
        ? {..._projections, 'assumptions': body}
        : {'title': 'Validation failed', 'status': status};
    return ResponseBody.fromString(
      jsonEncode(answer),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Dio _dio(HttpClientAdapter adapter) =>
    Dio(BaseOptions(baseUrl: 'http://api.test'))..httpClientAdapter = adapter;

void main() {
  group('LiveForecastRepository', () {
    test('sends the per-period amount as "contribution"', () async {
      final engine = _EngineAdapter();
      await LiveForecastRepository(_dio(engine))
          .compound(ForecastInputLimits.defaults);
      final body = engine.bodies.single;
      expect(body.containsKey('monthly_contribution'), isFalse);
      final contribution = body['contribution']! as Map<String, Object?>;
      expect(contribution['currency'], 'USD');
      expect(
        Decimal.parse(contribution['amount']! as String),
        Decimal.parse('500'),
      );
      expect(
        body['annual_return_percent'],
        isA<String>(),
        reason: 'rates as strings',
      );
    });

    test('the echoed assumptions match the request exactly', () async {
      final request = ForecastInputLimits.defaults;
      final response = await LiveForecastRepository(_dio(_EngineAdapter()))
          .compound(request);
      expect(response.matches(request), isTrue);
      expect(response.notice, isNotEmpty);
      expect(response.scenarios, hasLength(3));
    });

    test('a refused input is a validation error', () async {
      await expectLater(
        LiveForecastRepository(_dio(_EngineAdapter(status: 422)))
            .compound(ForecastInputLimits.defaults),
        throwsA(
          isA<ApiException>().having(
            (e) => e.kind,
            'kind',
            ApiErrorKind.validation,
          ),
        ),
      );
    });

    test('defaults are the shared calculator defaults', () async {
      expect(
        await LiveForecastRepository(_dio(_EngineAdapter())).defaultRequest(),
        ForecastInputLimits.defaults,
      );
    });
  });

  group('calculator in live mode', () {
    Future<void> pump(WidgetTester tester, _EngineAdapter engine) =>
        pumpRouterApp(
          tester,
          initialLocation: AppRoutes.calculator,
          overrides: demoOverrides(
            extra: [
              liveModeOverride(),
              forecastRepositoryProvider.overrideWithValue(
                LiveForecastRepository(_dio(engine)),
              ),
            ],
          ),
          surfaceSize: const Size(400, 1000),
        ).then((_) {});

    Future<void> calculate(WidgetTester tester) async {
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
    }

    testWidgets('any valid input gets a real projection with no DEMO notice', (
      tester,
    ) async {
      final engine = _EngineAdapter();
      await pump(tester, engine);
      expect(find.text('DEMO'), findsNothing);
      await tester.ensureVisible(find.byKey(const ValueKey('field-years')));
      await tester.enterText(find.byKey(const ValueKey('field-years')), '7');
      await tester.pump();
      await calculate(tester);
      expect(engine.bodies.single['years'], 7);
      expect(find.text('Wealth forecast'), findsWidgets);
      expect(find.text('DEMO'), findsNothing);
      expect(
        find.textContaining('demonstration'),
        findsNothing,
        reason: 'no demo-mismatch banner: the result is for these inputs',
      );
    });

    testWidgets('a refused input says so', (tester) async {
      await pump(tester, _EngineAdapter(status: 422));
      await calculate(tester);
      expect(find.textContaining("can't use these values"), findsOneWidget);
    });

    testWidgets('offline says so', (tester) async {
      await pump(tester, _EngineAdapter(offline: true));
      await calculate(tester);
      expect(find.textContaining("can't reach WealthSphere"), findsOneWidget);
    });
  });
}

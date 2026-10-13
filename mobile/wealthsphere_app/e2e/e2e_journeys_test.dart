// End-to-end journeys (P09-T10): the real app, the live repositories and real HTTP, against a real
// backend and database seeded by backend/tests/e2e_server.py.
//
//   cd backend && uv run python -m tests.e2e_server --port 8765 --out ../e2e.json
//   cd mobile/wealthsphere_app && WS_E2E_CONFIG=../../e2e.json flutter test e2e
//
// Without WS_E2E_CONFIG the journeys are skipped. The identity provider is stood in for by a fake
// sign-in that hands over a test-signed token the backend accepts; the Keycloak login itself is
// checked by backend/tests/test_identity_keycloak_live.py and the device journeys.
library;

import 'dart:convert';
import 'dart:io';

import 'package:decimal/decimal.dart';
import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/app/router.dart';
import 'package:wealthsphere_app/core/auth/auth_controller.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_manager.dart';
import 'package:wealthsphere_app/core/auth/token_set.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';
import 'package:wealthsphere_app/core/connectivity/connectivity.dart';
import 'package:wealthsphere_app/core/network/api_client.dart';
import 'package:wealthsphere_app/core/offline/offline_interceptor.dart';
import 'package:wealthsphere_app/core/offline/snapshot_cache.dart';
import 'package:wealthsphere_app/core/security/app_lock_settings.dart';
import 'package:wealthsphere_app/features/notifications/notification_service.dart';
import 'package:wealthsphere_app/features/portfolios/application/portfolio_providers.dart';
import 'package:wealthsphere_app/features/transactions/application/ledger_view.dart'
    show todayProvider;
import 'package:wealthsphere_app/shared/design_system/components/evidence_source_chip.dart';
import 'package:wealthsphere_app/shared/design_system/components/transaction_tile.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../test/helpers/auth_fakes.dart';
import '../test/helpers/demo_overrides.dart';

final String? _configPath = Platform.environment['WS_E2E_CONFIG'];

class _Seed {
  _Seed(Map<String, Object?> json)
    : apiUrl = json['api_url']! as String,
      token = json['token']! as String;

  final String apiUrl;
  final String token;
}

_Seed? _seed;

TokenSet _tokenSet() => TokenSet(
  accessToken: _seed!.token,
  refreshToken: 'e2e-refresh',
  accessTokenExpiresAt: DateTime.now().toUtc().add(const Duration(hours: 4)),
);

Dio _client() => Dio(
  BaseOptions(
    baseUrl: _seed!.apiUrl,
    headers: {'Authorization': 'Bearer ${_seed!.token}'},
  ),
);

/// A direct call to the API, outside the app: the figure the screen must agree with.
Future<Map<String, dynamic>> _get(WidgetTester tester, String path) async {
  final r = await tester.runAsync(
    () => _client().get<Map<String, dynamic>>(path),
  );
  return r!.data!;
}

Future<Map<String, dynamic>> _post(
  WidgetTester tester,
  String path,
  Map<String, Object?> body,
) async {
  final r = await tester.runAsync(
    () => _client().post<Map<String, dynamic>>(path, data: body),
  );
  return r!.data!;
}

/// `1234.5` as `$1,234.50` (en, USD), the way the app shows it.
String usd(String amount) {
  final parts = Decimal.parse(amount).toStringAsFixed(2).split('.');
  final whole = parts[0].replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => ',',
  );
  return '\$$whole.${parts[1]}';
}

ProviderContainer? _container;

Future<void> _launch(WidgetTester tester, {bool signedIn = true}) async {
  await tester.binding.setSurfaceSize(const Size(400, 2400));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final oidc = FakeOidcClient()..signInResults.add(_tokenSet());
  final store = InMemoryTokenStore(signedIn ? _tokenSet() : null);
  final yesterday = DateTime.now().subtract(const Duration(days: 1));
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        ...demoOverrides(
          extra: [
            appConfigProvider.overrideWithValue(
              AppConfig(
                apiBaseUrl: _seed!.apiUrl,
                oidcIssuer: 'https://id.e2e.invalid',
                dataSource: 'live',
              ),
            ),
            tokenStoreProvider.overrideWithValue(store),
            apiClientProvider.overrideWith((ref) {
              ref.watch(dataEpochProvider);
              final online = ref.read(onlineProvider.notifier);
              return buildApiClient(
                config: ref.watch(appConfigProvider),
                tokens: ref.watch(tokenManagerProvider),
                // Connections close at once: the test binding forbids the timers that keeping
                // them open would leave behind.
                adapter: IOHttpClientAdapter(
                  createHttpClient: () =>
                      HttpClient()..idleTimeout = Duration.zero,
                ),
                after: [
                  OfflineInterceptor(
                    ref.watch(snapshotCacheProvider),
                    onOnline: online.reachedServer,
                    onOffline: online.unreachable,
                  ),
                ],
              );
            }),
            // The device lock is a platform prompt; it is covered by its own tests.
            initialAppLockSettingsProvider.overrideWithValue(
              const AppLockSettings(enabled: false),
            ),
            oidcClientProvider.overrideWithValue(oidc),
            snapshotCacheProvider.overrideWithValue(MemorySnapshotCache()),
            // The server judges dates in UTC: stay clear of "today" at the day boundary.
            todayProvider.overrideWithValue(yesterday),
          ],
        ),
      ],
      child: Builder(
        builder: (context) {
          _container = ProviderScope.containerOf(context);
          return const WealthSphereApp();
        },
      ),
    ),
  );
  await tester.pump();
}

/// Waits (in real time, for the HTTP answers) until [finder] matches, pumping frames as it goes.
Future<void> _until(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 20),
}) async {
  final end = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(end)) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 80)),
    );
    await tester.pump(const Duration(milliseconds: 100));
    if (finder.evaluate().isNotEmpty) return;
  }
  // One last look, with a readable failure: what the screen showed.
  final shown = [
    for (final t in find.byType(Text).evaluate())
      if ((t.widget as Text).data != null) (t.widget as Text).data!,
  ];
  debugPrint('E2E screen texts: $shown');
  expect(finder, findsWidgets, reason: 'waited ${timeout.inSeconds}s');
}

/// Lets the last request finish and removes the app, so no timer outlives the test.
Future<void> _finish(WidgetTester tester) async {
  await tester.runAsync(
    () => Future<void>.delayed(const Duration(milliseconds: 500)),
  );
  await tester.pump(const Duration(seconds: 1));
  await tester.pumpWidget(const SizedBox());
  // Request timeouts (10 s) are fake timers: let them run out.
  for (var i = 0; i < 4; i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 100)),
    );
    await tester.pump(const Duration(seconds: 8));
  }
}

Future<void> _tapTab(WidgetTester tester, String label) async {
  final tab = find.descendant(
    of: find.byType(NavigationBar),
    matching: find.text(label),
  );
  await tester.tap(tab);
  await tester.pump(const Duration(milliseconds: 400));
}

void main() {
  final path = _configPath;
  if (path == null || !File(path).existsSync()) {
    test('end-to-end journeys (set WS_E2E_CONFIG to run)', () {}, skip: true);
    return;
  }

  setUpAll(() async {
    _seed = _Seed(
      jsonDecode(File(path).readAsStringSync()) as Map<String, Object?>,
    );
    await initializeDateLabels(['en']);
    // flutter_test blocks real network access by default.
    HttpOverrides.global = null;
  });

  testWidgets('1. sign in: the account is the server\'s', (tester) async {
    await _launch(tester, signedIn: false);
    await _tapTab(tester, 'More');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Settings'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Sign in'));
    await _until(tester, find.textContaining('alice@example.test'));
    expect(_container!.read(authControllerProvider), isA<SignedIn>());
    await _finish(tester);
  });

  testWidgets('2. view the portfolio: values are the backend\'s', (
    tester,
  ) async {
    await _launch(tester);
    // Home: the greeting is the stored display name; the net worth is the server's.
    await _until(tester, find.text('Hello, Alice'));
    final netWorth = await _get(tester, '/api/v1/net-worth');
    final expected = usd((netWorth['net_worth'] as Map)['amount'] as String);
    await _until(tester, find.text(expected));
    // Portfolio tab: the holding priced from the stored market price.
    await _tapTab(tester, 'Portfolio');
    await _until(tester, find.text('E2E'));
    expect(
      find.text(usd('1200.00')),
      findsWidgets,
      reason: '10 x the stored price of 120',
    );
    await _finish(tester);
  });

  testWidgets('3. add a transaction: the totals come back from the server', (
    tester,
  ) async {
    await _launch(tester);
    await _until(tester, find.text('Hello, Alice'));
    final before = await _get(tester, '/api/v1/net-worth');
    final beforeWorth = Decimal.parse(
      (before['net_worth'] as Map)['amount'] as String,
    );
    await _tapTab(tester, 'Portfolio');
    await _until(tester, find.text('E2E'));
    _container!.read(routerProvider).go(AppRoutes.addTransaction);
    await tester.pump(const Duration(milliseconds: 400));
    await _until(tester, find.text('Type'));
    // A deposit of 500.00 into Retirement.
    await tester.tap(
      find.widgetWithText(DropdownButtonFormField<TransactionKind>, 'Type'),
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Deposit').last);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(
      find.widgetWithText(DropdownButtonFormField<String>, 'Portfolio'),
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Retirement').last);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Select a date'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('OK'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.enterText(find.widgetWithText(TextField, 'Amount'), '500.00');
    await tester.tap(find.text('Review'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Save transaction'));
    await _until(tester, find.text('Transaction recorded'));

    final after = await _get(tester, '/api/v1/net-worth');
    final afterWorth = Decimal.parse(
      (after['net_worth'] as Map)['amount'] as String,
    );
    expect(
      afterWorth - beforeWorth,
      Decimal.parse('500.00'),
      reason: 'the server booked it',
    );
    // The app re-reads the server's totals instead of adjusting its own.
    await _tapTab(tester, 'Home');
    await _until(tester, find.text(usd(afterWorth.toString())));
    await _finish(tester);
  });

  testWidgets(
    '4. forecast: the engine\'s projection for the calculator inputs',
    (tester) async {
      await _launch(tester);
      await _until(tester, find.text('Hello, Alice'));
      await _tapTab(tester, 'More');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.text('Compounding calculator'));
      await tester.pump(const Duration(milliseconds: 400));
      await tester.ensureVisible(find.text('Calculate'));
      await tester.tap(find.text('Calculate'));
      await _until(tester, find.text('Wealth forecast'));
      // The same inputs sent straight to the API give the figure on screen.
      final r = await _post(tester, '/api/v1/forecasts/scenarios', {
        'initial_investment': {'amount': '10000.00', 'currency': 'USD'},
        'contribution': {'amount': '500.00', 'currency': 'USD'},
        'annual_return_percent': '8.00',
        'years': 20,
        'contribution_growth_percent': '0.00',
        'inflation_percent': '2.50',
        'annual_fee_percent': '0.50',
        'compounding_frequency': 'monthly',
        'contribution_frequency': 'monthly',
        'conservative_return_percent': '5.00',
        'growth_return_percent': '12.00',
      });
      final base = (r['scenarios'] as Map)['base'] as Map;
      final finalNominal = (base['final_nominal'] as Map)['amount'] as String;
      await _until(
        tester,
        find.textContaining(usd(finalNominal).split('.').first),
      );
      expect(find.text('DEMO'), findsNothing);
      await _finish(tester);
    },
  );

  testWidgets(
    '5. goal progress: status and the assumption notice are the server\'s',
    (tester) async {
      await _launch(tester);
      await _until(tester, find.text('Hello, Alice'));
      await _tapTab(tester, 'Goals');
      await _until(tester, find.text('House deposit'));
      final summary = await _get(tester, '/api/v1/goals/summary');
      final notice = summary['notice'] as String;
      await _until(tester, find.text(notice));
      await _finish(tester);
    },
  );

  testWidgets('6. notification deep link opens the alerts after sign-in', (
    tester,
  ) async {
    await _launch(tester, signedIn: false);
    _container!.read(pendingDeepLinkProvider.notifier).received({
      'route': '/more/alerts',
      'type': 'alert_triggered',
    });
    await tester.pump(const Duration(milliseconds: 300));
    expect(
      find.text('Watchlist and alerts'),
      findsNothing,
      reason: 'waits while signed out',
    );
    // Sign in through the account screen.
    await _tapTab(tester, 'More');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Settings'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Sign in'));
    await _until(tester, find.text('Watchlist and alerts'));
    await _until(tester, find.text('Triggered'));
    expect(find.text('When the price rises above \$110.00'), findsOneWidget);
    expect(find.textContaining('Price reached'), findsOneWidget);
    expect(_container!.read(pendingDeepLinkProvider), isNull);
    await _finish(tester);
  });

  testWidgets('7. ask the assistant: a checked answer from your own data', (
    tester,
  ) async {
    await _launch(tester);
    await _until(tester, find.text('Hello, Alice'));
    await _tapTab(tester, 'AI Wealth');
    await _until(tester, find.text('What is my net worth?'));
    // Live mode says so: no DEMO label, the app's own introduction.
    expect(find.text('DEMO'), findsNothing);
    await tester.tap(find.text('What is my net worth?'));
    // The answer arrives in its sections, with the data it rests on and the server's notice.
    await _until(tester, find.text('Observed data'));
    expect(find.text('Your net worth was retrieved.'), findsOneWidget);
    expect(find.text('AI interpretation'), findsOneWidget);
    expect(find.byType(EvidenceSourceChip), findsOneWidget);
    // It was stored on the server and shows in the history.
    final stored = await tester.runAsync(
      () => _client().get<List<dynamic>>('/api/v1/ai/conversations'),
    );
    expect(stored!.data, hasLength(1));
    await tester.tap(find.byTooltip('Conversations'));
    await _until(tester, find.text('What is my net worth?').last);
    await _finish(tester);
  });

  testWidgets(
    '8. reporting currency: switch, see the server figures, convert',
    (tester) async {
      await _launch(tester);
      await _until(tester, find.text('Hello, Alice'));
      // Choose euros in Settings.
      await _tapTab(tester, 'More');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.text('Settings'));
      await _until(
        tester,
        find.byKey(const ValueKey('reporting-currency-tile')),
      );
      await _until(tester, find.text('USD · US dollar'));
      await tester.tap(find.byKey(const ValueKey('reporting-currency-tile')));
      await _until(tester, find.byKey(const ValueKey('currency-EUR')));
      // Let the sheet finish opening before tapping a row inside it.
      await tester.pump(const Duration(seconds: 1));
      await tester.ensureVisible(find.byKey(const ValueKey('currency-EUR')));
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.byKey(const ValueKey('currency-EUR')));
      await _until(tester, find.text('EUR · Euro'));
      // Home now shows the server's net worth in euros (the app converts nothing itself).
      final netWorth = await _get(tester, '/api/v1/net-worth');
      expect((netWorth['net_worth'] as Map)['currency'], 'EUR');
      final amount = (netWorth['net_worth'] as Map)['amount'] as String;
      await _tapTab(tester, 'Home');
      await _until(tester, find.textContaining(_grouped(amount)));
      expect(
        find.byKey(const ValueKey('reporting-currency-chip')),
        findsOneWidget,
      );
      await _until(tester, find.textContaining('FX rates current'));
      // The converter gives the server's conversion.
      _container!.read(routerProvider).go(AppRoutes.converter);
      await tester.pump(const Duration(milliseconds: 400));
      await _until(tester, find.byKey(const ValueKey('converter-amount')));
      await tester.enterText(
        find.byKey(const ValueKey('converter-amount')),
        '100',
      );
      await tester.tap(find.text('Convert'));
      await _until(tester, find.byKey(const ValueKey('converter-result')));
      final converted = await _post(tester, '/api/v1/fx/convert', {
        'amount': {'amount': '100', 'currency': 'AED'},
        'to': 'EUR',
      });
      final expected = (converted['converted'] as Map)['amount'] as String;
      expect(find.textContaining(_grouped(expected)), findsWidgets);
      // Back to dollars so the run can be repeated.
      await tester.runAsync(
        () => _client().patch<Map<String, dynamic>>(
          '/api/v1/me/currency-preferences',
          data: {'reporting_currency': 'USD'},
        ),
      );
      await _finish(tester);
    },
  );

  testWidgets('9. Portfolio Doctor and opportunities from the live services', (
    tester,
  ) async {
    await _launch(tester);
    await _until(tester, find.text('Hello, Alice'));
    // All portfolios together: the checks run per portfolio, so the screen asks for one.
    _container!.read(routerProvider).go(AppRoutes.doctor);
    await tester.pump(const Duration(milliseconds: 400));
    await _until(
      tester,
      find.text('Choose one portfolio to check its health.'),
    );
    final portfolios = await tester.runAsync(
      () => _client().get<List<dynamic>>('/api/v1/portfolios'),
    );
    final pid = (portfolios!.data!.first as Map)['id'] as String;
    _container!.read(selectedPortfolioIdProvider.notifier).select(pid);
    // The server's findings, shown as the server wrote them.
    final report = await _post(tester, '/api/v1/ai/portfolio-doctor', {
      'portfolio_id': pid,
    });
    final flagged = [
      for (final f in report['findings'] as List)
        if ((f as Map)['status'] == 'flagged') f['message'] as String,
    ];
    expect(flagged, isNotEmpty, reason: 'one stock and cash is concentrated');
    await _until(tester, find.text(flagged.first));
    expect(find.text('Buy'), findsNothing);
    expect(find.text('Sell'), findsNothing);
    // Opportunities: a run of the server's pipeline (no eligible instruments for Alice here,
    // so it is empty), never an error and never a trade button.
    _container!.read(routerProvider).go(AppRoutes.opportunities);
    await tester.pump(const Duration(milliseconds: 400));
    // The first run takes a moment: wait until the server has stored it.
    var runs = const <dynamic>[];
    final end = DateTime.now().add(const Duration(seconds: 20));
    while (runs.isEmpty && DateTime.now().isBefore(end)) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 300)),
      );
      await tester.pump(const Duration(milliseconds: 100));
      final r = await tester.runAsync(
        () => _client().get<List<dynamic>>('/api/v1/ai/opportunities/runs'),
      );
      runs = r!.data!;
    }
    expect(runs, isNotEmpty, reason: 'the screen asked the pipeline');
    expect(find.text('Buy'), findsNothing);
    await _finish(tester);
  });
}

/// `9307.6` as `9,307.60`: the digits as the app groups them, whatever the currency symbol.
String _grouped(String amount) {
  final parts = Decimal.parse(amount).toStringAsFixed(2).split('.');
  final whole = parts[0].replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => ',',
  );
  return '$whole.${parts[1]}';
}

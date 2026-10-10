@Tags(['security'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/auth_controller.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_manager.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';
import 'package:wealthsphere_app/core/network/api_client.dart';
import 'package:wealthsphere_app/features/account/presentation/account_section.dart';

import '../../helpers/auth_fakes.dart';
import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';

const config = AppConfig(
  apiBaseUrl: 'http://127.0.0.1:8000',
  oidcIssuer: 'http://127.0.0.1:8081/realms/wealthsphere',
);

void main() {
  late FakeOidcClient oidc;
  late InMemoryTokenStore store;
  late FakeAdapter api;

  setUp(() {
    oidc = FakeOidcClient();
    store = InMemoryTokenStore();
    api = FakeAdapter();
  });

  List<Override> overrides() => demoOverrides(
    extra: [
      appConfigProvider.overrideWithValue(config),
      tokenStoreProvider.overrideWithValue(store),
      oidcClientProvider.overrideWithValue(oidc),
      tokenManagerProvider.overrideWith(
        (ref) => TokenManager(store: store, client: oidc, clock: () => epoch),
      ),
      apiClientProvider.overrideWith(
        (ref) => buildApiClient(
          config: config,
          tokens: ref.watch(tokenManagerProvider),
          adapter: api,
        ),
      ),
    ],
  );

  Map<String, Object?> me(String email) => {
    'id': '7d1f2c4e-0000-4000-8000-000000000001',
    'email': email,
    'base_currency': 'USD',
  };

  testWidgets('signed out: explains DEMO data and offers sign-in', (
    tester,
  ) async {
    await tester.pumpApp(
      const Scaffold(body: AccountSection()),
      overrides: overrides(),
    );
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.textContaining('DEMO'), findsOneWidget);
    expect(api.sent, isEmpty);
  });

  testWidgets('sign in, see the server account, sign out', (tester) async {
    oidc.signInResults.add(tokens('a'));
    api.replies.add(reply(200, me('alice@example.test')));
    await tester.pumpApp(
      const Scaffold(body: AccountSection()),
      overrides: overrides(),
    );

    await tester.tap(find.byKey(const ValueKey('sign-in')));
    await tester.pumpAndSettle();
    expect(find.text('Signed in as alice@example.test'), findsOneWidget);
    expect(find.text('Server account: alice@example.test'), findsOneWidget);
    expect(store.tokens, isNotNull);
    expect(
      api.sent.single.header('authorization'),
      'Bearer ${tokens('a').accessToken}',
    );

    await tester.tap(find.byKey(const ValueKey('sign-out')));
    await tester.pumpAndSettle();
    expect(find.text('Sign in'), findsOneWidget);
    expect(store.tokens, isNull);
    expect(oidc.endedSessions, hasLength(1));
  });

  testWidgets('a stored session is restored at start-up', (tester) async {
    store.tokens = tokens('a');
    api.replies.add(reply(200, me('alice@example.test')));
    await tester.pumpApp(
      const Scaffold(body: AccountSection()),
      overrides: overrides(),
    );
    expect(find.text('Signed in as alice@example.test'), findsOneWidget);
  });

  testWidgets('cancelling sign-in shows no error', (tester) async {
    oidc.signInResults.add(const AuthException(AuthFailure.cancelled));
    await tester.pumpApp(
      const Scaffold(body: AccountSection()),
      overrides: overrides(),
    );
    await tester.tap(find.byKey(const ValueKey('sign-in')));
    await tester.pumpAndSettle();
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.textContaining('did not complete'), findsNothing);
    expect(find.textContaining("Can't reach"), findsNothing);
  });

  testWidgets('sign-in failures are explained without detail', (tester) async {
    oidc.signInResults
      ..add(const AuthException(AuthFailure.network))
      ..add(const AuthException(AuthFailure.unexpected));
    await tester.pumpApp(
      const Scaffold(body: AccountSection()),
      overrides: overrides(),
    );
    await tester.tap(find.byKey(const ValueKey('sign-in')));
    await tester.pumpAndSettle();
    expect(
      find.textContaining("Can't reach the sign-in service"),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey('sign-in')));
    await tester.pumpAndSettle();
    expect(
      find.text('Sign-in did not complete. Please try again.'),
      findsOneWidget,
    );
  });

  testWidgets('an ended session says so and returns to signed out', (
    tester,
  ) async {
    store.tokens = tokens(
      'a',
      expiresAt: epoch,
    ); // needs a refresh for the /me call
    oidc.refreshResults.add(const AuthException(AuthFailure.rejected));
    await tester.pumpApp(
      const Scaffold(body: AccountSection()),
      overrides: overrides(),
    );
    expect(
      find.text('Your session ended. Please sign in again.'),
      findsOneWidget,
    );
    expect(find.text('Sign in'), findsOneWidget);
    expect(store.tokens, isNull);
    expect(api.sent, isEmpty);
  });

  testWidgets(
    'a server error on the account check is shown, the session is kept',
    (tester) async {
      store.tokens = tokens('a');
      api.replies.add(reply(500, {'title': 'Internal Server Error'}));
      await tester.pumpApp(
        const Scaffold(body: AccountSection()),
        overrides: overrides(),
      );
      expect(
        find.text("Couldn't load your account from the server."),
        findsOneWidget,
      );
      expect(find.text('Sign out'), findsOneWidget);
      expect(store.tokens, isNotNull);
    },
  );

  testWidgets(
    'two-step verification set-up keeps the session whatever happens',
    (tester) async {
      store.tokens = tokens('a');
      api.replies.addAll([
        reply(200, me('alice@example.test')),
        reply(200, me('alice@example.test')),
      ]);
      oidc.signInResults
        ..add(const AuthException(AuthFailure.unexpected))
        ..add(const AuthException(AuthFailure.cancelled))
        ..add(tokens('b'));
      await tester.pumpApp(
        const Scaffold(body: SingleChildScrollView(child: AccountSection())),
        overrides: overrides(),
      );
      final button = find.byKey(const ValueKey('set-up-mfa'));
      await tester.ensureVisible(button);
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(
        find.text(
          'Two-step verification set-up did not complete. Please try again.',
        ),
        findsOneWidget,
      );
      expect(store.tokens!.refreshToken, 'refresh-a');
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(
        find.textContaining('did not complete'),
        findsNothing,
      ); // cancelled: no error
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(
        store.tokens!.refreshToken,
        'refresh-b',
      ); // the new tokens replace the old
      expect(
        oidc.signInRequests.map((r) => r.intent),
        everyElement(SignInIntent.configureMfa),
      );
      expect(find.text('Sign out'), findsOneWidget);
    },
  );

  test('the controller never exposes tokens', () async {
    store.tokens = tokens('a');
    final container = ProviderContainer(
      overrides: [
        tokenStoreProvider.overrideWithValue(store),
        oidcClientProvider.overrideWithValue(oidc),
      ],
    );
    addTearDown(container.dispose);
    container.read(authControllerProvider);
    await Future<void>.delayed(Duration.zero);
    final state = container.read(authControllerProvider);
    expect(state, const SignedIn(email: 'alice@example.test'));
    expect(state.toString(), isNot(contains(tokens('a').accessToken)));
  });
}

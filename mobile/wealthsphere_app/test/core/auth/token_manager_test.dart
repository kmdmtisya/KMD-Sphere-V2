@Tags(['security'])
library;

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_manager.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';

import '../../helpers/auth_fakes.dart';

void main() {
  late FakeOidcClient client;
  late InMemoryTokenStore store;
  late DateTime now;
  late List<SessionEnd> ended;

  TokenManager manager() =>
      TokenManager(store: store, client: client, clock: () => now)
        ..onSessionEnded = ended.add;

  setUp(() {
    client = FakeOidcClient();
    store = InMemoryTokenStore();
    now = epoch;
    ended = [];
  });

  test('restores a stored session', () async {
    store.tokens = tokens('a');
    final m = manager();
    expect(await m.restore(), isTrue);
    expect(m.isSignedIn, isTrue);
    expect(m.claims['email'], 'alice@example.test');
  });

  test('signed out: no token and no refresh attempt', () async {
    final m = manager();
    expect(await m.validAccessToken(), isNull);
    expect(client.refreshedFrom, isEmpty);
  });

  test('sign-in stores the new session', () async {
    client.signInResults.add(tokens('a'));
    final m = manager();
    await m.signIn();
    expect(store.tokens!.refreshToken, 'refresh-a');
    expect(await m.validAccessToken(), tokens('a').accessToken);
  });

  test('a failed sign-in stores nothing', () async {
    client.signInResults.add(const AuthException(AuthFailure.cancelled));
    final m = manager();
    await expectLater(m.signIn(), throwsA(isA<AuthException>()));
    expect(store.tokens, isNull);
    expect(m.isSignedIn, isFalse);
  });

  test('a fresh access token is used without refreshing', () async {
    store.tokens = tokens('a');
    expect(await manager().validAccessToken(), tokens('a').accessToken);
    expect(client.refreshedFrom, isEmpty);
  });

  test(
    'an expiring access token is refreshed and the rotated tokens persisted',
    () async {
      store.tokens = tokens('a');
      client.refreshResults.add(
        tokens('b', expiresAt: epoch.add(const Duration(minutes: 10))),
      );
      final m = manager();
      now = epoch.add(
        const Duration(minutes: 4, seconds: 31),
      ); // within the 30 s margin
      expect(await m.validAccessToken(), tokens('b').accessToken);
      expect(client.refreshedFrom.single.refreshToken, 'refresh-a');
      expect(
        store.tokens!.refreshToken,
        'refresh-b',
      ); // the old one is dead after rotation
      expect(await m.validAccessToken(), tokens('b').accessToken);
      expect(client.refreshedFrom, hasLength(1));
    },
  );

  test('concurrent callers share one refresh', () async {
    store.tokens = tokens('a', expiresAt: epoch);
    client
      ..refreshGate = Completer<void>()
      ..refreshResults.add(tokens('b'));
    final m = manager();
    final results = Future.wait([
      for (var i = 0; i < 5; i++) m.validAccessToken(),
    ]);
    await Future<void>.delayed(Duration.zero);
    client.refreshGate!.complete();
    expect(await results, everyElement(tokens('b').accessToken));
    expect(client.refreshedFrom, hasLength(1));
  });

  test('a refused refresh ends the session and clears storage', () async {
    store.tokens = tokens('a', expiresAt: epoch);
    client.refreshResults.add(const AuthException(AuthFailure.rejected));
    final m = manager();
    expect(await m.validAccessToken(), isNull);
    expect(store.tokens, isNull);
    expect(m.isSignedIn, isFalse);
    expect(ended, [SessionEnd.refreshRejected]);
  });

  test(
    'a network failure during refresh keeps the session for later',
    () async {
      store.tokens = tokens('a', expiresAt: epoch);
      client.refreshResults
        ..add(const AuthException(AuthFailure.network))
        ..add(tokens('b'));
      final m = manager();
      await expectLater(
        m.validAccessToken(),
        throwsA(
          isA<AuthException>().having(
            (e) => e.failure,
            'failure',
            AuthFailure.network,
          ),
        ),
      );
      expect(store.tokens!.refreshToken, 'refresh-a');
      expect(ended, isEmpty);
      expect(
        await m.validAccessToken(),
        tokens('b').accessToken,
      ); // works once back online
    },
  );

  test(
    'a token the API rejected is refreshed, unless it was already replaced',
    () async {
      store.tokens = tokens('a');
      client.refreshResults.add(tokens('b'));
      final m = manager();
      expect(
        await m.validAccessToken(rejected: tokens('a').accessToken),
        tokens('b').accessToken,
      );
      // A second request that failed with the old token gets the new one, without a refresh.
      expect(
        await m.validAccessToken(rejected: tokens('a').accessToken),
        tokens('b').accessToken,
      );
      expect(client.refreshedFrom, hasLength(1));
    },
  );

  test(
    'sign-out clears the device first and then ends the server session',
    () async {
      store.tokens = tokens('a');
      client.failEndSession = true; // offline: still signed out locally
      final m = manager();
      await m.signOut();
      expect(store.tokens, isNull);
      expect(m.isSignedIn, isFalse);
      expect(await m.validAccessToken(), isNull);
      await Future<void>.delayed(Duration.zero);
      expect(client.endedSessions.single.refreshToken, 'refresh-a');
    },
  );

  test(
    'a refresh that finishes after sign-out does not resurrect the session',
    () async {
      store.tokens = tokens('a', expiresAt: epoch);
      client
        ..refreshGate = Completer<void>()
        ..refreshResults.add(tokens('b'));
      final m = manager();
      final pending = m.validAccessToken();
      await Future<void>.delayed(Duration.zero);
      await m.signOut();
      client.refreshGate!.complete();
      expect(await pending, isNull);
      expect(store.tokens, isNull);
    },
  );

  test('the API refusing a fresh token ends the session', () async {
    store.tokens = tokens('a');
    final m = manager();
    await m.restore();
    await m.endRejectedSession();
    expect(store.tokens, isNull);
    expect(ended, [SessionEnd.rejectedByApi]);
  });
}

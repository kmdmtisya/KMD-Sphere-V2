import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:local_auth/local_auth.dart';
import 'package:mocktail/mocktail.dart';
import 'package:wealthsphere_app/core/auth/auth_controller.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_manager.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/core/security/app_lock_controller.dart';
import 'package:wealthsphere_app/core/security/app_lock_settings.dart';
import 'package:wealthsphere_app/core/security/device_authenticator.dart';

import '../../helpers/app_lock_fakes.dart';
import '../../helpers/auth_fakes.dart';

class MockLocalAuth extends Mock implements LocalAuthentication {}

void main() {
  group('LocalAuthDeviceAuthenticator', () {
    late MockLocalAuth auth;
    late LocalAuthDeviceAuthenticator authenticator;

    setUp(() {
      auth = MockLocalAuth();
      authenticator = LocalAuthDeviceAuthenticator(auth);
    });

    void answer(Future<bool> Function() result) => when(
      () => auth.authenticate(
        localizedReason: any(named: 'localizedReason'),
        biometricOnly: any(named: 'biometricOnly'),
        persistAcrossBackgrounding: any(named: 'persistAcrossBackgrounding'),
      ),
    ).thenAnswer((_) => result());

    test('success only when the platform says so', () async {
      answer(() async => true);
      expect(await authenticator.authenticate('why'), UnlockOutcome.success);
      answer(() async => false);
      expect(await authenticator.authenticate('why'), UnlockOutcome.failed);
    });

    test(
      'allows the device credential as the fallback and survives backgrounding',
      () async {
        answer(() async => true);
        await authenticator.authenticate('Unlock WealthSphere');
        verify(
          () => auth.authenticate(
            localizedReason: 'Unlock WealthSphere',
            persistAcrossBackgrounding: true,
          ),
        ).called(1);
      },
    );

    test('platform errors never count as success', () async {
      answer(
        () async => throw const LocalAuthException(
          code: LocalAuthExceptionCode.userCanceled,
        ),
      );
      expect(await authenticator.authenticate('why'), UnlockOutcome.cancelled);
      answer(() async => throw PlatformException(code: 'weird'));
      expect(await authenticator.authenticate('why'), UnlockOutcome.failed);
    });

    test('every error code maps to a non-success outcome', () {
      for (final code in LocalAuthExceptionCode.values) {
        expect(
          LocalAuthDeviceAuthenticator.outcomeFor(code),
          isNot(UnlockOutcome.success),
          reason: code.name,
        );
      }
      expect(
        LocalAuthDeviceAuthenticator.outcomeFor(
          LocalAuthExceptionCode.temporaryLockout,
        ),
        UnlockOutcome.lockedOut,
      );
      expect(
        LocalAuthDeviceAuthenticator.outcomeFor(
          LocalAuthExceptionCode.noCredentialsSet,
        ),
        UnlockOutcome.unavailable,
      );
    });

    test('availability errors mean "not available"', () async {
      when(() => auth.isDeviceSupported())
          .thenThrow(PlatformException(code: 'x'));
      expect(await authenticator.isAvailable(), isFalse);
      when(() => auth.isDeviceSupported()).thenAnswer((_) async => true);
      expect(await authenticator.isAvailable(), isTrue);
    });
  });

  group('AppLockSettings', () {
    test('round-trips through storage', () {
      const s = AppLockSettings(
        enabled: false,
        timeout: LockTimeout.fiveMinutes,
      );
      expect(AppLockSettings.fromStorage(s.toStorage()), s);
    });

    test('missing or damaged values fall back to locking on', () {
      for (final raw in [null, '', '{', '[]', '{"timeout": "never"}']) {
        final s = AppLockSettings.fromStorage(raw);
        expect(s.enabled, isTrue, reason: '$raw');
        expect(s.timeout, LockTimeout.immediately, reason: '$raw');
      }
    });

    test('changes are persisted as a preference', () async {
      final store = InMemoryPreferencesStore();
      final container = ProviderContainer(
        overrides: [preferencesStoreProvider.overrideWithValue(store)],
      );
      addTearDown(container.dispose);
      await container
          .read(appLockSettingsProvider.notifier)
          .set(const AppLockSettings(timeout: LockTimeout.oneMinute));
      expect(
        await readAppLockSettings(store),
        const AppLockSettings(timeout: LockTimeout.oneMinute),
      );
    });
  });

  group('AppLockController', () {
    late FakeDeviceAuthenticator device;
    late FakeOidcClient oidc;
    late InMemoryTokenStore store;
    late DateTime now;

    setUp(() {
      device = FakeDeviceAuthenticator();
      oidc = FakeOidcClient();
      store = InMemoryTokenStore();
      now = epoch;
    });

    Future<ProviderContainer> start({
      bool storedSession = false,
      AppLockSettings settings = const AppLockSettings(),
    }) async {
      if (storedSession) store.tokens = tokens('a');
      final container = ProviderContainer(
        overrides: [
          tokenStoreProvider.overrideWithValue(store),
          oidcClientProvider.overrideWithValue(oidc),
          deviceAuthenticatorProvider.overrideWithValue(device),
          initialAppLockSettingsProvider.overrideWithValue(settings),
        ],
      );
      addTearDown(container.dispose);
      container.read(appLockControllerProvider.notifier).clock = () => now;
      container.listen(appLockControllerProvider, (_, _) {});
      await pumpEventQueue();
      return container;
    }

    AppLockState lockOf(ProviderContainer c) =>
        c.read(appLockControllerProvider);
    AppLockController ctl(ProviderContainer c) =>
        c.read(appLockControllerProvider.notifier);

    test('signed out: nothing to lock', () async {
      final c = await start();
      ctl(c)
        ..onBackgrounded()
        ..onResumed()
        ..onIdle();
      expect(lockOf(c), const Unlocked());
    });

    test('a session restored at start-up is locked', () async {
      final c = await start(storedSession: true);
      expect(c.read(authControllerProvider), isA<SignedIn>());
      expect(lockOf(c), const Locked());
    });

    test('a session restored with the lock off is not locked', () async {
      final c = await start(
        storedSession: true,
        settings: const AppLockSettings(enabled: false),
      );
      ctl(c)
        ..onBackgrounded()
        ..onResumed()
        ..onIdle();
      expect(lockOf(c), const Unlocked());
    });

    test('a fresh sign-in is not locked', () async {
      oidc.signInResults.add(tokens('a'));
      final c = await start();
      await c.read(authControllerProvider.notifier).signIn();
      expect(lockOf(c), const Unlocked());
    });

    Future<ProviderContainer> unlockedSession({
      LockTimeout timeout = LockTimeout.immediately,
    }) async {
      final c = await start(
        storedSession: true,
        settings: AppLockSettings(timeout: timeout),
      );
      device.outcomes.add(UnlockOutcome.success);
      await ctl(c).unlock('why');
      expect(lockOf(c), const Unlocked());
      return c;
    }

    test('locks on resume (timeout: immediately)', () async {
      final c = await unlockedSession();
      ctl(c).onBackgrounded();
      ctl(c).onResumed();
      expect(lockOf(c), const Locked());
    });

    test('locks on resume only after the configured timeout', () async {
      final c = await unlockedSession(timeout: LockTimeout.oneMinute);
      ctl(c).onBackgrounded();
      now = now.add(const Duration(seconds: 59));
      ctl(c).onResumed();
      expect(lockOf(c), const Unlocked());
      ctl(c).onBackgrounded();
      now = now.add(const Duration(minutes: 1));
      ctl(c).onResumed();
      expect(lockOf(c), const Locked());
    });

    test('a clock that went backwards locks', () async {
      final c = await unlockedSession(timeout: LockTimeout.fiveMinutes);
      ctl(c).onBackgrounded();
      now = now.subtract(const Duration(hours: 1));
      ctl(c).onResumed();
      expect(lockOf(c), const Locked());
    });

    test('locks when idle', () async {
      final c = await unlockedSession(timeout: LockTimeout.fiveMinutes);
      ctl(c).onIdle();
      expect(lockOf(c), const Locked());
    });

    for (final outcome in [
      UnlockOutcome.failed,
      UnlockOutcome.cancelled,
      UnlockOutcome.lockedOut,
      UnlockOutcome.unavailable,
    ]) {
      test('${outcome.name} keeps the app locked', () async {
        final c = await start(storedSession: true);
        device.outcomes.add(outcome);
        await ctl(c).unlock('why');
        expect(lockOf(c), Locked(lastOutcome: outcome));
      });
    }

    test(
      'signing out from the lock screen releases the lock and the session',
      () async {
        final c = await start(storedSession: true);
        await c.read(authControllerProvider.notifier).signOut();
        expect(lockOf(c), const Unlocked());
        expect(store.tokens, isNull);
      },
    );

    test('a session that ends while locked leaves nothing locked', () async {
      store.tokens = tokens(
        'a',
        expiresAt: DateTime.utc(2000),
      ); // needs a refresh
      final c = await start();
      expect(lockOf(c), const Locked());
      oidc.refreshResults.add(const AuthException(AuthFailure.rejected));
      expect(await c.read(tokenManagerProvider).validAccessToken(), isNull);
      expect(
        c.read(authControllerProvider),
        const SignedOut(ended: SessionEnd.refreshRejected),
      );
      expect(lockOf(c), const Unlocked());
    });
  });
}

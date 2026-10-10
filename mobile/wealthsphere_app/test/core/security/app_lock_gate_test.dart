import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/auth_controller.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/core/security/app_lock_controller.dart';
import 'package:wealthsphere_app/core/security/app_lock_gate.dart';
import 'package:wealthsphere_app/core/security/app_lock_settings.dart';
import 'package:wealthsphere_app/core/security/device_authenticator.dart';
import 'package:wealthsphere_app/features/account/presentation/app_lock_settings_tile.dart';
import 'package:wealthsphere_app/l10n/generated/app_localizations.dart';
import 'package:wealthsphere_app/shared/design_system/theme/app_theme.dart';

import '../../helpers/app_lock_fakes.dart';
import '../../helpers/auth_fakes.dart';
import '../../helpers/strict_tap_target.dart';

const secret = r'Balance $1,234.56';

void main() {
  late FakeDeviceAuthenticator device;
  late FakeOidcClient oidc;
  late InMemoryTokenStore store;
  late InMemoryPreferencesStore prefs;

  setUp(() {
    device = FakeDeviceAuthenticator();
    oidc = FakeOidcClient();
    store = InMemoryTokenStore(tokens('a'));
    prefs = InMemoryPreferencesStore();
  });

  Future<ProviderContainer> pumpGate(
    WidgetTester tester, {
    AppLockSettings settings = const AppLockSettings(),
    Widget? home,
    double textScale = 1,
  }) async {
    final container = ProviderContainer(
      overrides: [
        tokenStoreProvider.overrideWithValue(store),
        oidcClientProvider.overrideWithValue(oidc),
        deviceAuthenticatorProvider.overrideWithValue(device),
        initialAppLockSettingsProvider.overrideWithValue(settings),
        preferencesStoreProvider.overrideWithValue(prefs),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          theme: AppTheme.light(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: TextScaler.linear(textScale)),
            child: AppLockGate(child: child!),
          ),
          home: home ?? const Scaffold(body: Center(child: Text(secret))),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return container;
  }

  Future<void> lifecycle(
    WidgetTester tester,
    List<AppLifecycleState> states,
  ) async {
    for (final s in states) {
      tester.binding.handleAppLifecycleStateChanged(s);
      await tester.pump();
    }
  }

  const background = [
    AppLifecycleState.inactive,
    AppLifecycleState.hidden,
    AppLifecycleState.paused,
  ];
  const foreground = [
    AppLifecycleState.hidden,
    AppLifecycleState.inactive,
    AppLifecycleState.resumed,
  ];

  testWidgets(
    'a restored session starts locked, hides the app and prompts once',
    (tester) async {
      await pumpGate(tester); // the fake prompt is cancelled by default
      expect(find.byKey(const ValueKey('lock-screen')), findsOneWidget);
      expect(
        find.text(secret),
        findsNothing,
      ); // offstage: not painted or hit-testable
      expect(
        find.text(secret, skipOffstage: false),
        findsOneWidget,
      ); // state is kept
      expect(device.prompts, ['Unlock WealthSphere']);
      // Hidden from screen readers too.
      final handle = tester.ensureSemantics();
      expect(find.bySemanticsLabel(secret), findsNothing);
      handle.dispose();
    },
  );

  testWidgets('only a successful check unlocks', (tester) async {
    device.outcomes.addAll([UnlockOutcome.failed, UnlockOutcome.success]);
    await pumpGate(tester);
    expect(find.text('Not recognised. Try again.'), findsOneWidget);
    expect(find.text(secret), findsNothing);
    expect(device.prompts, hasLength(1)); // no automatic retry loop
    await tester.tap(find.byKey(const ValueKey('unlock')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lock-screen')), findsNothing);
    expect(find.text(secret), findsOneWidget);
  });

  testWidgets('a locked-out device explains itself and stays locked', (
    tester,
  ) async {
    device.outcomes.add(UnlockOutcome.lockedOut);
    await pumpGate(tester);
    expect(find.textContaining('Too many attempts'), findsOneWidget);
    expect(find.text(secret), findsNothing);
  });

  testWidgets('without device security the only way on is signing out', (
    tester,
  ) async {
    device.outcomes.add(UnlockOutcome.unavailable);
    final container = await pumpGate(tester);
    expect(find.textContaining('no screen lock'), findsOneWidget);
    final unlock = tester.widget<ButtonStyleButton>(
      find.byKey(const ValueKey('unlock')),
    );
    expect(unlock.onPressed, isNull);
    expect(find.text(secret), findsNothing);
    await tester.tap(find.byKey(const ValueKey('lock-sign-out')));
    await tester.pumpAndSettle();
    expect(container.read(authControllerProvider), isA<SignedOut>());
    expect(store.tokens, isNull);
    expect(find.byKey(const ValueKey('lock-screen')), findsNothing);
  });

  testWidgets('locks again on return from the background and re-prompts', (
    tester,
  ) async {
    device.outcomes.add(UnlockOutcome.success);
    await pumpGate(tester);
    expect(find.text(secret), findsOneWidget);
    await lifecycle(tester, background);
    device.outcomes.add(UnlockOutcome.success);
    await lifecycle(tester, foreground);
    await tester.pumpAndSettle();
    expect(device.prompts, hasLength(2));
    expect(find.text(secret), findsOneWidget);
  });

  testWidgets('with a timeout, a short absence does not lock', (tester) async {
    device.outcomes.add(UnlockOutcome.success);
    final container = await pumpGate(
      tester,
      settings: const AppLockSettings(timeout: LockTimeout.fiveMinutes),
    );
    var now = DateTime.utc(2026);
    container.read(appLockControllerProvider.notifier).clock = () => now;
    await lifecycle(tester, background);
    now = now.add(const Duration(minutes: 4));
    await lifecycle(tester, foreground);
    expect(find.text(secret), findsOneWidget);
    await lifecycle(tester, background);
    now = now.add(const Duration(minutes: 6));
    await lifecycle(tester, foreground);
    await tester.pump();
    expect(find.byKey(const ValueKey('lock-screen')), findsOneWidget);
  });

  testWidgets('the app switcher sees a privacy cover, not the content', (
    tester,
  ) async {
    device.outcomes.add(UnlockOutcome.success);
    await pumpGate(tester);
    await lifecycle(tester, [AppLifecycleState.inactive]);
    expect(find.byKey(const ValueKey('privacy-cover')), findsOneWidget);
    await lifecycle(tester, [AppLifecycleState.resumed]);
    expect(find.byKey(const ValueKey('privacy-cover')), findsNothing);
    expect(
      find.text(secret),
      findsOneWidget,
    ); // a brief inactive (no hide) does not lock
  });

  testWidgets('locks after five idle minutes; touches reset the timer', (
    tester,
  ) async {
    device.outcomes.add(UnlockOutcome.success);
    await pumpGate(
      tester,
      settings: const AppLockSettings(timeout: LockTimeout.fiveMinutes),
    );
    await tester.pump(const Duration(minutes: 4));
    await tester.tap(find.text(secret));
    await tester.pump(const Duration(minutes: 4));
    expect(find.text(secret), findsOneWidget);
    await tester.pump(const Duration(minutes: 1, seconds: 1));
    expect(find.byKey(const ValueKey('lock-screen')), findsOneWidget);
  });

  testWidgets('signed out: never locked', (tester) async {
    store.tokens = null;
    await pumpGate(tester);
    await lifecycle(tester, background);
    await lifecycle(tester, foreground);
    await tester.pump(const Duration(minutes: 10));
    expect(find.text(secret), findsOneWidget);
    expect(device.prompts, isEmpty);
  });

  testWidgets('lock off: never locked', (tester) async {
    await pumpGate(tester, settings: const AppLockSettings(enabled: false));
    await lifecycle(tester, background);
    await lifecycle(tester, foreground);
    expect(find.text(secret), findsOneWidget);
    expect(device.prompts, isEmpty);
  });

  testWidgets('the lock screen is accessible and fits at 2x text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320 * 3, 640 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    device.outcomes.add(UnlockOutcome.lockedOut);
    final handle = tester.ensureSemantics();
    await pumpGate(tester, textScale: 2);
    expect(tester.takeException(), isNull);
    await expectLater(tester, meetsGuideline(strictTapTargetGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    await expectLater(tester, meetsGuideline(textContrastGuideline));
    expect(
      tester.getSemantics(find.text('WealthSphere is locked')),
      matchesSemantics(label: 'WealthSphere is locked', isHeader: true),
    );
    handle.dispose();
  });

  group('settings', () {
    Widget tile() => const Scaffold(
      body: SingleChildScrollView(child: AppLockSettingsTile()),
    );

    Future<ProviderContainer> pumpSettings(WidgetTester tester) async {
      store.tokens =
          null; // settings are reached in an unlocked session; no lock here
      return pumpGate(tester, home: tile());
    }

    testWidgets('turning the lock off needs the device to verify the user', (
      tester,
    ) async {
      final c = await pumpSettings(tester);
      device.outcomes.add(UnlockOutcome.failed);
      await tester.tap(find.byKey(const ValueKey('app-lock-switch')));
      await tester.pumpAndSettle();
      expect(c.read(appLockSettingsProvider).enabled, isTrue);
      device.outcomes.add(UnlockOutcome.success);
      await tester.tap(find.byKey(const ValueKey('app-lock-switch')));
      await tester.pumpAndSettle();
      expect(c.read(appLockSettingsProvider).enabled, isFalse);
      expect(device.prompts.last, "Confirm it's you to change app lock");
      expect(
        await readAppLockSettings(prefs),
        const AppLockSettings(enabled: false),
      );
    });

    testWidgets('changing the timeout needs verification too', (tester) async {
      final c = await pumpSettings(tester);
      device.outcomes.add(UnlockOutcome.cancelled);
      await tester.tap(find.text('After 5 minutes'));
      await tester.pumpAndSettle();
      expect(c.read(appLockSettingsProvider).timeout, LockTimeout.immediately);
      device.outcomes.add(UnlockOutcome.success);
      await tester.tap(find.text('After 5 minutes'));
      await tester.pumpAndSettle();
      expect(c.read(appLockSettingsProvider).timeout, LockTimeout.fiveMinutes);
    });

    testWidgets(
      'a device that cannot verify anyone can only turn the lock off',
      (tester) async {
        device.available = false;
        final c = await pumpSettings(tester);
        expect(find.textContaining('Set up a screen lock'), findsOneWidget);
        expect(find.byKey(const ValueKey('app-lock-timeout')), findsNothing);
        await tester.tap(find.byKey(const ValueKey('app-lock-switch')));
        await tester.pumpAndSettle();
        expect(c.read(appLockSettingsProvider).enabled, isFalse);
        expect(device.prompts, isEmpty);
        final sw = tester.widget<SwitchListTile>(
          find.byKey(const ValueKey('app-lock-switch')),
        );
        expect(sw.onChanged, isNull); // and cannot turn it back on
      },
    );
  });

  testWidgets('a prompt that answers after the session ended changes nothing', (
    tester,
  ) async {
    device.gate = Completer<void>();
    device.outcomes.add(UnlockOutcome.failed);
    final container = await pumpGate(tester)
        .timeout(const Duration(seconds: 5));
    expect(container.read(appLockControllerProvider), const Unlocking());
    await container.read(authControllerProvider.notifier).signOut();
    device.gate!.complete();
    await tester.pumpAndSettle();
    expect(container.read(authControllerProvider), isA<SignedOut>());
    expect(container.read(appLockControllerProvider), const Unlocked());
    expect(find.byKey(const ValueKey('lock-screen')), findsNothing);
  });

  testWidgets(
    'after a failed attempt, returning to the app does not re-prompt by itself',
    (tester) async {
      // iOS: the Face ID sheet makes the app inactive, then resumed. Prompting again on every
      // resume after a failure would loop.
      device.outcomes.add(UnlockOutcome.cancelled);
      await pumpGate(tester);
      expect(device.prompts, hasLength(1));
      await lifecycle(tester, [
        AppLifecycleState.inactive,
        AppLifecycleState.resumed,
      ]);
      await lifecycle(tester, background);
      await lifecycle(tester, foreground);
      await tester.pumpAndSettle();
      expect(device.prompts, hasLength(1));
      expect(find.byKey(const ValueKey('lock-screen')), findsOneWidget);
    },
  );
}

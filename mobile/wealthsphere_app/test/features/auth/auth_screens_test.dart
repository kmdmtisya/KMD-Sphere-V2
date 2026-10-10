@Tags(['security'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/router.dart';
import 'package:wealthsphere_app/core/auth/oidc_client.dart';
import 'package:wealthsphere_app/core/auth/token_store.dart';
import 'package:wealthsphere_app/core/config/app_config.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/core/security/app_lock_settings.dart';
import 'package:wealthsphere_app/core/security/device_authenticator.dart';
import 'package:wealthsphere_app/features/auth/application/auth_flow.dart';
import 'package:wealthsphere_app/l10n/generated/app_localizations.dart';
import 'package:wealthsphere_app/shared/design_system/theme/app_theme.dart';

import '../../helpers/app_lock_fakes.dart';
import '../../helpers/auth_fakes.dart';
import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_router.dart';
import '../../helpers/strict_tap_target.dart';

class FakeResetLauncher implements PasswordResetLauncher {
  bool succeed = true;
  int opened = 0;

  @override
  Future<bool> open() async {
    opened++;
    return succeed;
  }
}

void main() {
  late FakeOidcClient oidc;
  late InMemoryTokenStore store;
  late InMemoryPreferencesStore prefs;
  late FakeDeviceAuthenticator device;
  late FakeResetLauncher reset;

  setUp(() {
    oidc = FakeOidcClient();
    store = InMemoryTokenStore();
    prefs = InMemoryPreferencesStore();
    device = FakeDeviceAuthenticator();
    reset = FakeResetLauncher();
  });

  List<Override> overrides() => demoOverrides(
    store: prefs,
    extra: [
      tokenStoreProvider.overrideWithValue(store),
      oidcClientProvider.overrideWithValue(oidc),
      deviceAuthenticatorProvider.overrideWithValue(device),
      passwordResetLauncherProvider.overrideWithValue(reset),
    ],
  );

  Future<void> pumpAt(
    WidgetTester tester,
    String location, {
    Size size = const Size(390, 844),
    double textScale = 1,
    TextDirection direction = TextDirection.ltr,
  }) => pumpRouterApp(
    tester,
    initialLocation: location,
    overrides: overrides(),
    surfaceSize: size,
    textScale: textScale,
    textDirection: direction,
  );

  // ----------------------------------------------------------------------------- welcome

  group('Welcome', () {
    testWidgets('Skip is labelled for screen readers and leads to sign-in', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await pumpAt(tester, '/welcome');
      expect(find.text('All your wealth in one place'), findsOneWidget);
      expect(
        tester.getSemantics(find.byKey(const ValueKey('welcome-skip'))),
        matchesSemantics(
          label: 'Skip introduction',
          isButton: true,
          hasTapAction: true,
          isEnabled: true,
          hasEnabledState: true,
          isFocusable: true,
          hasFocusAction: true,
        ),
      );
      await tester.tap(find.byKey(const ValueKey('welcome-skip')));
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsWidgets);
      expect(await readOnboardingComplete(prefs), isTrue);
      handle.dispose();
    });

    testWidgets(
      'Next walks every slide without swiping; the last says Get started',
      (tester) async {
        await pumpAt(tester, '/welcome');
        await tester.tap(find.byKey(const ValueKey('welcome-next')));
        await tester.pumpAndSettle();
        expect(find.text('Plan with clear scenarios'), findsOneWidget);
        await tester.tap(find.byKey(const ValueKey('welcome-next')));
        await tester.pumpAndSettle();
        expect(find.text('AI that shows its working'), findsOneWidget);
        expect(find.text('Get started'), findsOneWidget);
        expect(find.byKey(const ValueKey('welcome-skip')), findsNothing);
        await tester.tap(find.text('Get started'));
        await tester.pumpAndSettle();
        expect(find.byKey(const ValueKey('continue-sign-in')), findsOneWidget);
      },
    );

    testWidgets('each slide announces its position', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpAt(tester, '/welcome');
      expect(find.bySemanticsLabel(RegExp('All your wealth')), findsWidgets);
      final node = tester.getSemantics(
        find
            .descendant(
              of: find.byKey(const ValueKey('welcome-slide-0')),
              matching: find.byType(Semantics),
            )
            .first,
      );
      expect(node.getSemanticsData().hint, 'Slide 1 of 3');
      handle.dispose();
    });

    testWidgets('"I already have an account" goes straight to sign-in', (
      tester,
    ) async {
      await pumpAt(tester, '/welcome');
      await tester.tap(find.byKey(const ValueKey('welcome-sign-in')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('continue-sign-in')), findsOneWidget);
    });

    testWidgets('no slide promises returns', (tester) async {
      await pumpAt(tester, '/welcome');
      final l10n = AppLocalizations.of(
        tester.element(find.byType(Scaffold).first),
      );
      for (final text in [
        l10n.welcomeSlide1Body,
        l10n.welcomeSlide2Body,
        l10n.welcomeSlide3Body,
        l10n.welcomeSlide2Title,
      ]) {
        expect(
          text.toLowerCase(),
          isNot(matches(RegExp('guarantee|certain|risk-free'))),
        );
      }
      expect(l10n.welcomeSlide2Body, contains('not promises'));
    });
  });

  // ----------------------------------------------------------------------------- sign in

  group('Sign in', () {
    Future<void> signInWith(WidgetTester tester, String email) async {
      await tester.enterText(
        find.byKey(const ValueKey('sign-in-email')),
        email,
      );
      await tester.tap(find.byKey(const ValueKey('continue-sign-in')));
      await tester.pumpAndSettle();
    }

    testWidgets('an invalid email is explained and nothing is opened', (
      tester,
    ) async {
      await pumpAt(tester, '/sign-in');
      await signInWith(tester, 'not-an-email');
      expect(
        find.text(
          'Enter an email address like name@example.com, or leave this empty.',
        ),
        findsOneWidget,
      );
      expect(oidc.signInCalls, 0);
    });

    testWidgets(
      'a valid email pre-fills the hosted page; empty sends no hint',
      (tester) async {
        oidc.signInResults
          ..add(const AuthException(AuthFailure.cancelled))
          ..add(const AuthException(AuthFailure.cancelled));
        await pumpAt(tester, '/sign-in');
        await signInWith(tester, '  alice@example.test ');
        await signInWith(tester, '');
        expect(oidc.signInRequests, [
          (loginHint: 'alice@example.test', intent: SignInIntent.signIn),
          (loginHint: null, intent: SignInIntent.signIn),
        ]);
      },
    );

    testWidgets('Create an account opens registration', (tester) async {
      oidc.signInResults.add(const AuthException(AuthFailure.cancelled));
      await pumpAt(tester, '/sign-in');
      await tester.tap(find.byKey(const ValueKey('create-account')));
      await tester.pumpAndSettle();
      expect(oidc.signInRequests.single.intent, SignInIntent.register);
    });

    testWidgets('cancelling shows no error', (tester) async {
      oidc.signInResults.add(const AuthException(AuthFailure.cancelled));
      await pumpAt(tester, '/sign-in');
      await signInWith(tester, '');
      expect(find.byKey(const ValueKey('sign-in-error')), findsNothing);
    });

    for (final (failure, message) in [
      (
        AuthFailure.network,
        "Can't reach the sign-in service. Check your connection and try again.",
      ),
      (AuthFailure.rejected, 'Sign-in did not complete. Please try again.'),
      (AuthFailure.unexpected, 'Sign-in did not complete. Please try again.'),
    ]) {
      testWidgets('${failure.name}: a plain, non-leaking message', (
        tester,
      ) async {
        oidc.signInResults.add(AuthException(failure));
        await pumpAt(tester, '/sign-in');
        await signInWith(tester, 'alice@example.test');
        final banner = find.byKey(const ValueKey('sign-in-error'));
        expect(
          find.descendant(of: banner, matching: find.text(message)),
          findsOneWidget,
        );
        // Nothing about the account, the provider's error codes or tokens.
        final texts = tester
            .widgetList<Text>(
              find.descendant(of: banner, matching: find.byType(Text)),
            )
            .map((t) => t.data ?? '')
            .join(' ');
        expect(
          texts,
          isNot(
            matches(
              RegExp(
                'alice|invalid_grant|token|exception',
                caseSensitive: false,
              ),
            ),
          ),
        );
      });
    }

    testWidgets(
      'Forgot password opens the reset page, and says so when it cannot',
      (tester) async {
        await pumpAt(tester, '/sign-in');
        await tester.tap(find.byKey(const ValueKey('forgot-password')));
        await tester.pumpAndSettle();
        expect(reset.opened, 1);
        expect(find.byKey(const ValueKey('sign-in-error')), findsNothing);
        reset.succeed = false;
        await tester.tap(find.byKey(const ValueKey('forgot-password')));
        await tester.pumpAndSettle();
        expect(
          find.textContaining("Couldn't open the password reset page"),
          findsOneWidget,
        );
      },
    );

    testWidgets('Explore with DEMO data goes to Home without signing in', (
      tester,
    ) async {
      await pumpAt(tester, '/sign-in');
      await tester.tap(find.byKey(const ValueKey('explore-demo')));
      await tester.pumpAndSettle();
      expect(find.text('Total wealth'), findsOneWidget);
      expect(store.tokens, isNull);
    });

    testWidgets(
      'first sign-in offers biometrics once; accepting needs a device check',
      (tester) async {
        oidc.signInResults.add(tokens('a'));
        device.outcomes.add(UnlockOutcome.success);
        await pumpAt(tester, '/sign-in');
        await signInWith(tester, '');
        expect(find.byKey(const ValueKey('biometric-offer')), findsOneWidget);
        await tester.tap(find.byKey(const ValueKey('biometric-accept')));
        await tester.pumpAndSettle();
        expect(device.prompts, ['Unlock WealthSphere']);
        expect(await readAppLockSettings(prefs), const AppLockSettings());
        expect(find.text('Total wealth'), findsOneWidget); // then Home
        expect(await biometricOfferShown(prefs), isTrue);
      },
    );

    testWidgets('"Not now" turns the lock off; the offer is not repeated', (
      tester,
    ) async {
      oidc.signInResults.add(tokens('a'));
      await pumpAt(tester, '/sign-in');
      await signInWith(tester, '');
      await tester.tap(find.byKey(const ValueKey('biometric-decline')));
      await tester.pumpAndSettle();
      expect((await readAppLockSettings(prefs)).enabled, isFalse);
      expect(device.prompts, isEmpty);
      expect(find.text('Total wealth'), findsOneWidget);
    });

    testWidgets('a failed device check leaves the lock setting unchanged', (
      tester,
    ) async {
      await prefs.setString(
        appLockPreferenceKey,
        const AppLockSettings(enabled: false).toStorage(),
      );
      oidc.signInResults.add(tokens('a'));
      device.outcomes.add(UnlockOutcome.failed);
      await pumpRouterApp(
        tester,
        initialLocation: '/sign-in',
        overrides: [
          ...overrides(),
          initialAppLockSettingsProvider.overrideWithValue(
            const AppLockSettings(enabled: false),
          ),
        ],
      );
      await signInWith(tester, '');
      await tester.tap(find.byKey(const ValueKey('biometric-accept')));
      await tester.pumpAndSettle();
      expect((await readAppLockSettings(prefs)).enabled, isFalse);
    });

    testWidgets(
      'a device without a screen lock is told what returning requires',
      (tester) async {
        device.available = false;
        oidc.signInResults.add(tokens('a'));
        await pumpAt(tester, '/sign-in');
        await signInWith(tester, '');
        expect(find.text('Protect this device'), findsOneWidget);
        await tester.tap(find.byKey(const ValueKey('biometric-ok')));
        await tester.pumpAndSettle();
        expect(find.text('Total wealth'), findsOneWidget);
      },
    );

    testWidgets('the offer is skipped once shown', (tester) async {
      await markBiometricOfferShown(prefs);
      oidc.signInResults.add(tokens('a'));
      await pumpAt(tester, '/sign-in');
      await signInWith(tester, '');
      expect(find.byKey(const ValueKey('biometric-offer')), findsNothing);
      expect(find.text('Total wealth'), findsOneWidget);
    });
  });

  // ------------------------------------------------------------------- layout and a11y

  for (final location in ['/welcome', '/sign-in']) {
    for (final (name, size, scale, dir, dark) in [
      ('320 wide, 2.0x', const Size(320, 640), 2.0, TextDirection.ltr, false),
      (
        '320 wide, dark, rtl, 2.0x',
        const Size(320, 640),
        2.0,
        TextDirection.rtl,
        true,
      ),
      ('tablet', const Size(1024, 768), 1.0, TextDirection.ltr, false),
    ]) {
      testWidgets('$location fits: $name', (tester) async {
        await tester.binding.setSurfaceSize(size);
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final router = createRouter(initialLocation: location);
        addTearDown(router.dispose);
        await tester.pumpWidget(
          ProviderScope(
            overrides: overrides(),
            child: MaterialApp.router(
              routerConfig: router,
              theme: AppTheme.light(),
              darkTheme: AppTheme.dark(),
              themeMode: dark ? ThemeMode.dark : ThemeMode.light,
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              builder: (context, child) => MediaQuery(
                data: MediaQuery.of(context)
                    .copyWith(textScaler: TextScaler.linear(scale)),
                child: Directionality(textDirection: dir, child: child!),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('$location meets the accessibility guidelines', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpAt(tester, location);
      await expectLater(tester, meetsGuideline(strictTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    });
  }

  // ---------------------------------------------------------------------- start-up and MFA

  testWidgets('first launch starts with the introduction', (tester) async {
    final container = ProviderContainer(
      overrides: [initialOnboardingCompleteProvider.overrideWithValue(false)],
    );
    addTearDown(container.dispose);
    expect(
      container
          .read(routerProvider)
          .routerDelegate
          .currentConfiguration
          .uri
          .path,
      anyOf('/welcome', ''),
    );
    expect(
      container.read(routerProvider).routeInformationProvider.value.uri.path,
      '/welcome',
    );
  });

  testWidgets('later launches start on Home', (tester) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(
      container.read(routerProvider).routeInformationProvider.value.uri.path,
      '/home',
    );
  });

  test('the reset page URL comes from configuration only', () {
    const config = AppConfig(
      apiBaseUrl: 'https://api.example.com',
      oidcIssuer: 'https://id.example.com/realms/wealthsphere/',
    );
    expect(
      resetPasswordUri(config).toString(),
      'https://id.example.com/realms/wealthsphere/login-actions/reset-credentials'
      '?client_id=wealthsphere-mobile',
    );
  });

  test('login hint validation', () {
    expect(validateLoginHint(''), isNull);
    expect(validateLoginHint('   '), isNull);
    expect(validateLoginHint('a@b.co'), isNull);
    expect(validateLoginHint(' a@b.co '), isNull);
    for (final bad in ['a', 'a@b', '@b.co', 'a b@c.co', 'a@b .co']) {
      expect(validateLoginHint(bad), EmailProblem.invalid, reason: bad);
    }
    expect(validateLoginHint('${'a' * 320}@b.co'), EmailProblem.tooLong);
  });
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/auth/auth_controller.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';
import 'package:wealthsphere_app/features/account/data/theme_mode_sync.dart';
import 'package:wealthsphere_app/shared/design_system/theme/theme.dart';

class _TestAuth extends AuthController {
  @override
  AuthState build() => const SignedOut();

  void set(AuthState next) => state = next;
}

class _FakeSync implements ThemeModeSync {
  _FakeSync(this.remote);

  ThemeMode? remote;
  final List<ThemeMode> saved = [];

  @override
  Future<ThemeMode?> load() async => remote;

  @override
  Future<void> save(ThemeMode mode) async {
    saved.add(mode);
    remote = mode;
  }
}

({ProviderContainer container, _FakeSync sync}) setUpSync({
  required ThemeMode? remote,
  ThemeMode initial = ThemeMode.system,
}) {
  final sync = _FakeSync(remote);
  final container = ProviderContainer(
    overrides: [
      preferencesStoreProvider.overrideWithValue(InMemoryPreferencesStore()),
      initialThemeModeProvider.overrideWithValue(initial),
      themeModeSyncProvider.overrideWithValue(sync),
      authControllerProvider.overrideWith(_TestAuth.new),
    ],
  );
  addTearDown(container.dispose);
  container.read(themeModeSyncWiringProvider);
  return (container: container, sync: sync);
}

Future<void> signIn(ProviderContainer c) async {
  (c.read(authControllerProvider.notifier) as _TestAuth).set(
    const SignedIn(email: 'a@example.test'),
  );
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
}

void main() {
  test('after sign-in the account\'s choice wins over the device\'s', () async {
    final t = setUpSync(remote: ThemeMode.dark, initial: ThemeMode.light);
    await signIn(t.container);
    expect(t.container.read(themeModeProvider), ThemeMode.dark);
    expect(t.sync.saved, isEmpty, reason: 'pulling must not echo back');
  });

  test('when the account has none, the device\'s choice is sent up', () async {
    final t = setUpSync(remote: null, initial: ThemeMode.dark);
    await signIn(t.container);
    expect(t.container.read(themeModeProvider), ThemeMode.dark);
    expect(t.sync.saved, [ThemeMode.dark]);
  });

  test(
    'a change on the device is saved to the account while signed in',
    () async {
      final t = setUpSync(remote: ThemeMode.system);
      await signIn(t.container);
      await t.container
          .read(themeModeProvider.notifier)
          .setMode(ThemeMode.light);
      await Future<void>.delayed(Duration.zero);
      expect(t.sync.saved, [ThemeMode.light]);
    },
  );

  test('nothing is sent while signed out', () async {
    final t = setUpSync(remote: ThemeMode.system);
    await t.container.read(themeModeProvider.notifier).setMode(ThemeMode.dark);
    await Future<void>.delayed(Duration.zero);
    expect(t.sync.saved, isEmpty);
  });

  test('a sync failure never breaks the appearance', () async {
    final sync = _ThrowingSync();
    final container = ProviderContainer(
      overrides: [
        preferencesStoreProvider.overrideWithValue(InMemoryPreferencesStore()),
        themeModeSyncProvider.overrideWithValue(sync),
        authControllerProvider.overrideWith(_TestAuth.new),
      ],
    );
    addTearDown(container.dispose);
    container.read(themeModeSyncWiringProvider);
    await signIn(container);
    await container.read(themeModeProvider.notifier).setMode(ThemeMode.dark);
    expect(container.read(themeModeProvider), ThemeMode.dark);
  });
}

class _ThrowingSync implements ThemeModeSync {
  @override
  Future<ThemeMode?> load() async => throw StateError('offline');

  @override
  Future<void> save(ThemeMode mode) async => throw StateError('offline');
}

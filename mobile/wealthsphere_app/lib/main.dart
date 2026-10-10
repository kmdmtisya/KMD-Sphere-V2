import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app/app.dart';
import 'core/auth/token_store.dart';
import 'core/preferences/preferences_store.dart';
import 'core/security/app_lock_settings.dart';
import 'features/auth/application/auth_flow.dart';
import 'shared/design_system/formatting/formatting.dart';
import 'shared/design_system/theme/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateLabels();
  final store = SharedPreferencesStore(await SharedPreferences.getInstance());
  final themeMode = await readThemeMode(store);
  final appLock = await readAppLockSettings(store);
  final onboarded = await readOnboardingComplete(store);
  runApp(
    ProviderScope(
      overrides: [
        preferencesStoreProvider.overrideWithValue(store),
        tokenStoreProvider.overrideWithValue(SecureTokenStore()),
        initialThemeModeProvider.overrideWithValue(themeMode),
        initialAppLockSettingsProvider.overrideWithValue(appLock),
        initialOnboardingCompleteProvider.overrideWithValue(onboarded),
      ],
      child: const WealthSphereApp(),
    ),
  );
}

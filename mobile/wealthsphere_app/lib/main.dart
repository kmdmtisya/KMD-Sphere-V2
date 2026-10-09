import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app/app.dart';
import 'core/preferences/preferences_store.dart';
import 'shared/design_system/formatting/formatting.dart';
import 'shared/design_system/theme/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateLabels();
  final store = SharedPreferencesStore(await SharedPreferences.getInstance());
  final themeMode = await readThemeMode(store);
  runApp(
    ProviderScope(
      overrides: [
        preferencesStoreProvider.overrideWithValue(store),
        initialThemeModeProvider.overrideWithValue(themeMode),
      ],
      child: const WealthSphereApp(),
    ),
  );
}

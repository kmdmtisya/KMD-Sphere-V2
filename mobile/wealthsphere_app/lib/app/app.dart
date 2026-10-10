import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/security/app_lock_gate.dart';
import '../l10n/generated/app_localizations.dart';
import '../shared/design_system/theme/theme.dart';
import 'router.dart';

final ThemeData _lightTheme = AppTheme.light();
final ThemeData _darkTheme = AppTheme.dark();

class WealthSphereApp extends ConsumerWidget {
  const WealthSphereApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      onGenerateTitle: (context) => AppLocalizations.of(context).appTitle,
      routerConfig: ref.watch(routerProvider),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: _lightTheme,
      darkTheme: _darkTheme,
      themeMode: ref.watch(themeModeProvider),
      builder: (context, child) =>
          AppLockGate(child: child ?? const SizedBox.shrink()),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/l10n/generated/app_localizations.dart';
import 'package:wealthsphere_app/shared/design_system/theme/app_theme.dart';

/// Wraps [child] with provider scope, theme, localisation, text scale and text direction.
/// Every widget test in the project uses this helper so light/dark, 2.0x text and RTL
/// variants are one parameter away.
extension PumpApp on WidgetTester {
  Future<void> pumpApp(
    Widget child, {
    ThemeData? theme,
    ThemeData? darkTheme,
    ThemeMode themeMode = ThemeMode.light,
    double textScale = 1.0,
    TextDirection textDirection = TextDirection.ltr,
    List<Override> overrides = const [],
    Size? surfaceSize,
    bool settle = true,
  }) async {
    if (surfaceSize != null) {
      await binding.setSurfaceSize(surfaceSize);
      addTearDown(() => binding.setSurfaceSize(null));
    }
    await pumpWidget(
      ProviderScope(
        overrides: overrides,
        child: MaterialApp(
          theme: theme ?? AppTheme.light(),
          darkTheme: darkTheme ?? AppTheme.dark(),
          themeMode: themeMode,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, widget) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: TextScaler.linear(textScale)),
            child: Directionality(textDirection: textDirection, child: widget!),
          ),
          home: child,
        ),
      ),
    );
    if (settle) {
      await pumpAndSettle();
    } else {
      await pump();
    }
  }
}

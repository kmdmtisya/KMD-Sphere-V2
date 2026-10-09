import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:wealthsphere_app/app/router.dart';
import 'package:wealthsphere_app/l10n/generated/app_localizations.dart';
import 'package:wealthsphere_app/shared/design_system/theme/app_theme.dart';

import 'demo_overrides.dart';

/// Pumps the real route table and shell starting at [initialLocation].
Future<GoRouter> pumpRouterApp(
  WidgetTester tester, {
  String initialLocation = '/home',
  Size surfaceSize = const Size(390, 844),
  double textScale = 1.0,
  TextDirection textDirection = TextDirection.ltr,
  bool enableGallery = true,
  List<Override> overrides = const [],
}) async {
  await tester.binding.setSurfaceSize(surfaceSize);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final router = createRouter(
    initialLocation: initialLocation,
    enableGallery: enableGallery,
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: overrides.isEmpty ? demoOverrides() : overrides,
      child: MaterialApp.router(
        routerConfig: router,
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(textScale)),
          child: Directionality(textDirection: textDirection, child: child!),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return router;
}

/// Counts "close the app" requests (what Android's back button does at a root screen).
class SystemBackRecorder {
  SystemBackRecorder(WidgetTester tester) {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'SystemNavigator.pop') exits++;
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );
  }

  int exits = 0;
}

String currentPath(GoRouter router) =>
    router.routerDelegate.currentConfiguration.uri.toString();

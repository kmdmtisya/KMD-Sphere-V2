@Tags(['golden'])
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/gallery/gallery_sections.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../helpers/pump_app.dart';
import '../helpers/test_fonts.dart';

// Golden images are authoritative on the CI Linux runner (dart_test.yaml); elsewhere text
// renders slightly differently, so the comparison is skipped instead of failing falsely.
final bool _linux = Platform.isLinux;

void main() {
  setUpAll(() async {
    await loadTestFonts();
    await initializeDateLabels(['en']);
  });

  // Charts have their own goldens (test/shared/design_system/charts).
  for (final section in gallerySections.where((s) => s.id != 'charts')) {
    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        testWidgets('${section.id} (${mode.name}, ${scale}x)', (tester) async {
          await tester.pumpApp(
            Scaffold(
              body: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Builder(
                  builder: (c) => section.builder(c, animated: false),
                ),
              ),
            ),
            themeMode: mode,
            textScale: scale,
            surfaceSize: const Size(360, 1800),
          );
          await expectLater(
            find.byType(Scaffold),
            matchesGoldenFile(
              'goldens/${section.id}_${mode.name}_${scale == 1.0 ? '1x' : '2x'}.png',
            ),
          );
        }, skip: !_linux);
      }
    }
  }
}

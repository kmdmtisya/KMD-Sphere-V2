import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/tokens/tokens.dart';

import '../../../helpers/contrast.dart';

/// Enforces WCAG 2.x AA for every semantic colour role in both themes: text roles at least
/// 4.5:1 and non-text roles (icons, borders, chart strokes) at least 3:1 against every surface
/// they can appear on.
void main() {
  final themes = <String, WealthColors>{
    'light': WealthColors.light,
    'dark': WealthColors.dark,
  };

  for (final entry in themes.entries) {
    final name = entry.key;
    final c = entry.value;
    final surfaces = <String, Color>{
      'scaffold': c.scaffold,
      'surface': c.surface,
      'surfaceElevated': c.surfaceElevated,
    };

    group('$name theme: text roles reach 4.5:1 on every surface', () {
      final textRoles = <String, Color>{
        'textPrimary': c.textPrimary,
        'textMuted': c.textMuted,
        'positiveText': c.positiveText,
        'negativeText': c.negativeText,
        'warningText': c.warningText,
        'riskLow': c.riskLow,
        'riskMedium': c.riskMedium,
        'riskHigh': c.riskHigh,
        'primary (links)': c.primary,
      };
      for (final role in textRoles.entries) {
        for (final surface in surfaces.entries) {
          test('${role.key} on ${surface.key}', () {
            expect(
              contrastRatio(role.value, surface.value),
              greaterThanOrEqualTo(aaNormalText),
            );
          });
        }
      }
    });

    group('$name theme: on-colour pairs reach 4.5:1', () {
      final pairs = <String, (Color, Color)>{
        'onPrimary on primary': (c.onPrimary, c.primary),
        'onAccent on accent': (c.onAccent, c.accent),
        'onDemoBadge on demoBadge': (c.onDemoBadge, c.demoBadge),
        'onStaleBanner on staleBanner': (c.onStaleBanner, c.staleBanner),
      };
      for (final pair in pairs.entries) {
        test(pair.key, () {
          expect(
            contrastRatio(pair.value.$1, pair.value.$2),
            greaterThanOrEqualTo(aaNormalText),
          );
        });
      }
    });

    group('$name theme: non-text roles reach 3:1 on every surface', () {
      final graphics = <String, Color>{
        'positive (icons)': c.positive,
        'negative (icons)': c.negative,
        'border': c.border,
        'primary (focus)': c.primary,
        // Gold is only a standalone graphic on dark surfaces. On light surfaces it is a fill that
        // always carries onAccent text (see the documented limit below).
        if (name == 'dark') 'accent': c.accent,
        'chartContributions': c.chartContributions,
        'chartGrowth': c.chartGrowth,
        for (var i = 0; i < c.chartSeries.length; i++)
          'chartSeries[$i]': c.chartSeries[i],
      };
      for (final role in graphics.entries) {
        for (final surface in surfaces.entries) {
          test('${role.key} on ${surface.key}', () {
            expect(
              contrastRatio(role.value, surface.value),
              greaterThanOrEqualTo(aaNonText),
            );
          });
        }
      }
    });
  }

  group('why derived text-safe shades exist (documented failures of the raw brand values)', () {
    test('brand teal is too weak for text on white', () {
      expect(
        contrastRatio(BrandPalette.teal600, BrandPalette.surfaceLight),
        lessThan(aaNormalText),
      );
      expect(
        contrastRatio(
          WealthColors.light.positiveText,
          BrandPalette.surfaceLight,
        ),
        greaterThanOrEqualTo(aaNormalText),
      );
    });

    test(
      'brand gold can never be text on white (accent fill with navy text only)',
      () {
        expect(
          contrastRatio(BrandPalette.gold400, BrandPalette.surfaceLight),
          lessThan(2),
        );
        expect(
          contrastRatio(BrandPalette.navy900, BrandPalette.gold400),
          greaterThanOrEqualTo(aaNormalText),
        );
      },
    );

    test('gold accent is a fill-with-text on light surfaces, never a standalone graphic', () {
      for (final surface in [
        WealthColors.light.scaffold,
        WealthColors.light.surface,
      ]) {
        expect(
          contrastRatio(WealthColors.light.accent, surface),
          lessThan(aaNonText),
        );
      }
      // Hence every gold element on a light background must carry onAccent text (or an outline
      // that meets 3:1 such as WealthColors.border) so it is never the only indicator.
      expect(
        contrastRatio(WealthColors.light.onAccent, WealthColors.light.accent),
        greaterThanOrEqualTo(aaNormalText),
      );
    });

    test('brand muted grey fails on the subtle background', () {
      expect(
        contrastRatio(BrandPalette.textMuted, BrandPalette.surfaceSubtle),
        lessThan(aaNormalText),
      );
      expect(
        contrastRatio(
          WealthColors.light.textMuted,
          WealthColors.light.scaffold,
        ),
        greaterThanOrEqualTo(aaNormalText),
      );
    });

    test('brand blue, red and teal fail as text on the brand navy', () {
      expect(
        contrastRatio(BrandPalette.blue600, BrandPalette.navy900),
        lessThan(aaNormalText),
      );
      expect(
        contrastRatio(BrandPalette.danger, BrandPalette.navy900),
        lessThan(aaNormalText),
      );
      expect(
        contrastRatio(BrandPalette.teal600, BrandPalette.navy900),
        lessThan(aaNormalText),
      );
    });
  });

  group('contrast helper', () {
    test('matches known WCAG values', () {
      expect(
        contrastRatio(const Color(0xFF000000), const Color(0xFFFFFFFF)),
        closeTo(21, 0.01),
      );
      expect(
        contrastRatio(const Color(0xFFFFFFFF), const Color(0xFFFFFFFF)),
        closeTo(1, 0.001),
      );
      expect(
        contrastRatio(BrandPalette.blue600, BrandPalette.surfaceLight),
        closeTo(5.17, 0.02),
      );
    });
  });
}

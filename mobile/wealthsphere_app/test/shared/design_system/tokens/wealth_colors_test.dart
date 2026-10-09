import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/tokens/tokens.dart';

import '../../../helpers/pump_app.dart';

void main() {
  group('WealthColors', () {
    test('light and dark define the same set of roles', () {
      expect(WealthColors.light.roles.keys, WealthColors.dark.roles.keys);
      expect(
        WealthColors.light.chartSeries.length,
        WealthColors.dark.chartSeries.length,
      );
    });

    test('chart palette has at least six distinct hues per theme', () {
      for (final colors in [WealthColors.light, WealthColors.dark]) {
        expect(colors.chartSeries.length, greaterThanOrEqualTo(6));
        expect(colors.chartSeries.toSet().length, colors.chartSeries.length);
      }
    });

    test('dark theme is genuinely different from light', () {
      final light = WealthColors.light.roles;
      final dark = WealthColors.dark.roles;
      final differing = light.keys.where((k) => light[k] != dark[k]).length;
      expect(differing, greaterThan(light.length ~/ 2));
    });

    test('every colour is fully opaque', () {
      for (final colors in [WealthColors.light, WealthColors.dark]) {
        for (final entry in colors.roles.entries) {
          expect(entry.value.a, 1.0, reason: entry.key);
        }
        for (final c in colors.chartSeries) {
          expect(c.a, 1.0);
        }
      }
    });

    test('copyWith replaces only the given roles', () {
      final changed = WealthColors.light.copyWith(
        primary: const Color(0xFF123456),
      );
      expect(changed.primary, const Color(0xFF123456));
      expect(changed.surface, WealthColors.light.surface);
      expect(changed.chartSeries, WealthColors.light.chartSeries);
    });

    test('lerp interpolates every role and endpoints are exact', () {
      const a = WealthColors.light;
      const b = WealthColors.dark;
      expect(a.lerp(b, 0).roles, a.roles);
      expect(a.lerp(b, 1).roles, b.roles);
      final mid = a.lerp(b, 0.5);
      expect(mid.surface, Color.lerp(a.surface, b.surface, 0.5));
      expect(mid.chartSeries.length, a.chartSeries.length);
      expect(a.lerp(null, 0.5), a);
    });

    testWidgets(
      'context.wealthColors falls back to the matching palette without the extension',
      (tester) async {
        late WealthColors seen;
        await tester.pumpApp(
          Builder(
            builder: (context) {
              seen = context.wealthColors;
              return const SizedBox();
            },
          ),
        );
        expect(seen, WealthColors.light);

        await tester.pumpApp(
          Builder(
            builder: (context) {
              seen = context.wealthColors;
              return const SizedBox();
            },
          ),
          themeMode: ThemeMode.dark,
        );
        expect(seen, WealthColors.dark);
      },
    );

    testWidgets('context.wealthColors prefers the registered extension', (
      tester,
    ) async {
      final custom = WealthColors.light.copyWith(
        primary: const Color(0xFFABCDEF),
      );
      late WealthColors seen;
      await tester.pumpApp(
        Builder(
          builder: (context) {
            seen = context.wealthColors;
            return const SizedBox();
          },
        ),
        theme: ThemeData(extensions: <ThemeExtension<dynamic>>[custom]),
      );
      expect(seen.primary, const Color(0xFFABCDEF));
    });
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/tokens/tokens.dart';

import '../../../helpers/pump_app.dart';

void main() {
  group('spacing', () {
    test('is an ascending 4/8-point grid', () {
      expect(AppSpacing.scale, [4, 8, 12, 16, 24, 32, 40, 48]);
      for (final value in AppSpacing.scale) {
        expect(value % 4, 0);
      }
      expect(AppSpacing.scale, orderedEquals([...AppSpacing.scale]..sort()));
    });

    test('page gutter is 16', () => expect(AppSpacing.gutter, 16));
  });

  group('radii and touch targets', () {
    test('card radii stay within the specified 12 to 20 dp', () {
      for (final r in [AppRadii.small, AppRadii.medium, AppRadii.large]) {
        expect(r, inInclusiveRange(12, 20));
      }
      expect(AppRadii.mediumRadius.topLeft.x, AppRadii.medium);
    });

    test('minimum touch targets', () {
      expect(AppTouchTarget.android, 48);
      expect(AppTouchTarget.ios, 44);
    });
  });

  group('breakpoints', () {
    test('classify widths', () {
      expect(AppBreakpoints.classify(320), WindowSizeClass.compact);
      expect(AppBreakpoints.classify(599.9), WindowSizeClass.compact);
      expect(AppBreakpoints.classify(600), WindowSizeClass.medium);
      expect(AppBreakpoints.classify(839.9), WindowSizeClass.medium);
      expect(AppBreakpoints.classify(840), WindowSizeClass.expanded);
    });

    testWidgets('reads the width from MediaQuery', (tester) async {
      late WindowSizeClass seen;
      await tester.pumpApp(
        Builder(
          builder: (context) {
            seen = AppBreakpoints.of(context);
            return const SizedBox();
          },
        ),
        surfaceSize: const Size(700, 900),
      );
      expect(seen, WindowSizeClass.medium);
    });
  });

  group('motion respects reduced motion', () {
    testWidgets(
      'durations are kept normally and zero when animations are disabled',
      (tester) async {
        late Duration normal;
        late Duration reduced;
        await tester.pumpWidget(
          MediaQuery(
            data: const MediaQueryData(),
            child: Builder(
              builder: (context) {
                normal = AppMotion.resolve(context, AppMotion.standard);
                return const SizedBox();
              },
            ),
          ),
        );
        await tester.pumpWidget(
          MediaQuery(
            data: const MediaQueryData(disableAnimations: true),
            child: Builder(
              builder: (context) {
                reduced = AppMotion.resolve(context, AppMotion.standard);
                return const SizedBox();
              },
            ),
          ),
        );
        expect(normal, AppMotion.standard);
        expect(reduced, Duration.zero);
      },
    );

    test('duration scale is ascending', () {
      expect(AppMotion.fast < AppMotion.standard, isTrue);
      expect(AppMotion.standard < AppMotion.slow, isTrue);
    });
  });
}

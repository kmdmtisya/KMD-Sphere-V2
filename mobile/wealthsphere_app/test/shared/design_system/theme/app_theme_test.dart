import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/theme/theme.dart';
import 'package:wealthsphere_app/shared/design_system/tokens/tokens.dart';

import '../../../helpers/contrast.dart';
import '../../../helpers/pump_app.dart';

void main() {
  final themes = <String, (ThemeData, WealthColors)>{
    'light': (AppTheme.light(), WealthColors.light),
    'dark': (AppTheme.dark(), WealthColors.dark),
  };

  for (final entry in themes.entries) {
    final name = entry.key;
    final theme = entry.value.$1;
    final c = entry.value.$2;

    group('$name theme data', () {
      test(
        'is Material 3 with the right brightness and registered extensions',
        () {
          expect(theme.useMaterial3, isTrue);
          expect(
            theme.brightness,
            name == 'light' ? Brightness.light : Brightness.dark,
          );
          expect(theme.extension<WealthColors>(), same(c));
          expect(theme.extension<WealthTypography>(), isNotNull);
          expect(theme.scaffoldBackgroundColor, c.scaffold);
        },
      );

      test('colour scheme maps the semantic roles', () {
        final s = theme.colorScheme;
        expect(s.primary, c.primary);
        expect(s.onPrimary, c.onPrimary);
        expect(s.tertiary, c.accent);
        expect(s.surface, c.surface);
        expect(s.onSurface, c.textPrimary);
        expect(s.outline, c.border);
        expect(s.error, c.negativeText);
      });

      test(
        'every foreground/background pair of the colour scheme reaches 4.5:1',
        () {
          final s = theme.colorScheme;
          final pairs = <String, (Color, Color)>{
            'onPrimary/primary': (s.onPrimary, s.primary),
            'onPrimaryContainer/primaryContainer': (
              s.onPrimaryContainer,
              s.primaryContainer,
            ),
            'onSecondary/secondary': (s.onSecondary, s.secondary),
            'onSecondaryContainer/secondaryContainer': (
              s.onSecondaryContainer,
              s.secondaryContainer,
            ),
            'onTertiary/tertiary': (s.onTertiary, s.tertiary),
            'onTertiaryContainer/tertiaryContainer': (
              s.onTertiaryContainer,
              s.tertiaryContainer,
            ),
            'onError/error': (s.onError, s.error),
            'onErrorContainer/errorContainer': (
              s.onErrorContainer,
              s.errorContainer,
            ),
            'onSurface/surface': (s.onSurface, s.surface),
            'onSurface/scaffold': (s.onSurface, c.scaffold),
            'onSurfaceVariant/surface': (s.onSurfaceVariant, s.surface),
            'onSurfaceVariant/scaffold': (s.onSurfaceVariant, c.scaffold),
            'onInverseSurface/inverseSurface': (
              s.onInverseSurface,
              s.inverseSurface,
            ),
            'snack-bar action (inversePrimary)/inverseSurface': (
              s.inversePrimary,
              s.inverseSurface,
            ),
          };
          for (final pair in pairs.entries) {
            expect(
              contrastRatio(pair.value.$1, pair.value.$2),
              greaterThanOrEqualTo(aaNormalText),
              reason: pair.key,
            );
          }
        },
      );

      test('selected and pressed tints stay readable: navigation indicator and chips', () {
        final s = theme.colorScheme;
        expect(
          contrastRatio(c.textPrimary, s.primaryContainer),
          greaterThanOrEqualTo(aaNormalText),
        );
        expect(
          contrastRatio(c.primary, s.primaryContainer),
          greaterThanOrEqualTo(aaNonText),
        );
      });

      test('buttons and icon buttons are at least 48 x 48 dp', () {
        final sizes = <String, Size?>{
          'filled': theme.filledButtonTheme.style?.minimumSize?.resolve({}),
          'elevated': theme.elevatedButtonTheme.style?.minimumSize?.resolve({}),
          'outlined': theme.outlinedButtonTheme.style?.minimumSize?.resolve({}),
          'text': theme.textButtonTheme.style?.minimumSize?.resolve({}),
          'icon': theme.iconButtonTheme.style?.minimumSize?.resolve({}),
        };
        for (final e in sizes.entries) {
          expect(e.value, isNotNull, reason: e.key);
          expect(
            e.value!.width,
            greaterThanOrEqualTo(AppTouchTarget.android),
            reason: e.key,
          );
          expect(
            e.value!.height,
            greaterThanOrEqualTo(AppTouchTarget.android),
            reason: e.key,
          );
        }
        expect(
          theme.segmentedButtonTheme.style!.minimumSize!.resolve({})!.height,
          greaterThanOrEqualTo(48),
        );
        expect(theme.materialTapTargetSize, MaterialTapTargetSize.padded);
        expect(theme.visualDensity, VisualDensity.standard);
      });

      test('buttons use the 12 dp radius; cards the 16 dp radius with no elevation', () {
        final shape = theme.filledButtonTheme.style!.shape!.resolve(
          {},
        ) as RoundedRectangleBorder;
        expect(shape.borderRadius, AppRadii.smallRadius);
        final card = theme.cardTheme.shape! as RoundedRectangleBorder;
        expect(card.borderRadius, AppRadii.mediumRadius);
        expect(card.side.color, c.divider);
        expect(theme.cardTheme.elevation, AppElevation.none);
        expect(theme.cardTheme.color, c.surface);
      });

      test('text fields are filled with a 3:1 border, thick focus ring and visible errors', () {
        final i = theme.inputDecorationTheme;
        expect(i.filled, isTrue);
        expect(
          (i.enabledBorder! as OutlineInputBorder).borderSide.color,
          c.border,
        );
        expect((i.focusedBorder! as OutlineInputBorder).borderSide.width, 2);
        expect(
          (i.errorBorder! as OutlineInputBorder).borderSide.color,
          c.negativeText,
        );
        expect(i.errorStyle!.color, c.negativeText);
        expect(
          contrastRatio(i.errorStyle!.color!, c.surface),
          greaterThanOrEqualTo(aaNormalText),
        );
        expect(
          contrastRatio(c.border, c.surface),
          greaterThanOrEqualTo(aaNonText),
        );
      });

      test('navigation always shows labels; sheets have a drag handle; snack bars float', () {
        expect(
          theme.navigationBarTheme.labelBehavior,
          NavigationDestinationLabelBehavior.alwaysShow,
        );
        expect(theme.bottomSheetTheme.showDragHandle, isTrue);
        expect(theme.snackBarTheme.behavior, SnackBarBehavior.floating);
        expect(theme.chipTheme.showCheckmark, isTrue);
      });

      test('page transitions are native: Cupertino on iOS, not on Android', () {
        final builders = theme.pageTransitionsTheme.builders;
        expect(
          builders[TargetPlatform.iOS],
          isA<CupertinoPageTransitionsBuilder>(),
        );
        expect(
          builders[TargetPlatform.android],
          isNot(isA<CupertinoPageTransitionsBuilder>()),
        );
      });
    });
  }

  group('typography', () {
    final type = AppTheme.light().extension<WealthTypography>()!;

    test('amounts use tabular figures so digits do not jitter', () {
      const tabular = FontFeature.tabularFigures();
      expect(type.displayAmount.fontFeatures, contains(tabular));
      expect(type.amount.fontFeatures, contains(tabular));
      expect(type.body.fontFeatures, isNull);
    });

    test('the named scale is ordered by size', () {
      expect(
        type.displayAmount.fontSize!,
        greaterThan(type.headline.fontSize!),
      );
      expect(type.headline.fontSize!, greaterThan(type.title.fontSize!));
      expect(type.title.fontSize!, greaterThanOrEqualTo(type.body.fontSize!));
      expect(type.body.fontSize!, greaterThan(type.label.fontSize!));
      expect(type.label.fontSize!, greaterThan(type.caption.fontSize!));
      expect(type.caption.fontSize!, greaterThanOrEqualTo(12));
    });

    test('every style has a colour that is readable on the surfaces', () {
      for (final t in [AppTheme.light(), AppTheme.dark()]) {
        final ty = t.extension<WealthTypography>()!;
        final colors = t.extension<WealthColors>()!;
        for (final style in ty.all) {
          expect(style.color, isNotNull);
          for (final surface in [
            colors.surface,
            colors.scaffold,
            colors.surfaceElevated,
          ]) {
            expect(
              contrastRatio(style.color!, surface),
              greaterThanOrEqualTo(aaNormalText),
            );
          }
        }
      }
    });

    test('uses the platform font (no custom family is forced)', () {
      for (final style in type.all) {
        expect(style.fontFamily, isNot(equals('CustomBrandFont')));
      }
      expect(AppTheme.light().textTheme.bodyLarge, isNotNull);
    });

    test('copyWith and lerp', () {
      final changed = type.copyWith(title: const TextStyle(fontSize: 99));
      expect(changed.title.fontSize, 99);
      expect(changed.body, type.body);
      expect(type.lerp(changed, 1).title.fontSize, 99);
      expect(type.lerp(null, 0.5), type);
    });

    testWidgets(
      'context.wealthText returns the themed scale and has a safe fallback',
      (tester) async {
        late WealthTypography themed;
        await tester.pumpApp(
          Builder(
            builder: (context) {
              themed = context.wealthText;
              return const SizedBox();
            },
          ),
        );
        expect(
          themed.displayAmount.fontFeatures,
          contains(const FontFeature.tabularFigures()),
        );

        late WealthTypography fallback;
        await tester.pumpApp(
          Builder(
            builder: (context) {
              fallback = context.wealthText;
              return const SizedBox();
            },
          ),
          theme: ThemeData(useMaterial3: true),
        );
        expect(
          fallback.displayAmount.fontFeatures,
          contains(const FontFeature.tabularFigures()),
        );
      },
    );
  });

  group('rendered widgets', () {
    for (final scale in [1.0, 2.0]) {
      testWidgets('buttons render at least 48 dp tall at text scale $scale', (
        tester,
      ) async {
        await tester.pumpApp(
          Column(
            children: [
              FilledButton(onPressed: () {}, child: const Text('Filled')),
              ElevatedButton(onPressed: () {}, child: const Text('Elevated')),
              OutlinedButton(onPressed: () {}, child: const Text('Outlined')),
              TextButton(onPressed: () {}, child: const Text('Text')),
              IconButton(onPressed: () {}, icon: const Icon(Icons.add)),
            ],
          ),
          textScale: scale,
          surfaceSize: const Size(400, 900),
        );
        for (final type in [
          FilledButton,
          ElevatedButton,
          OutlinedButton,
          TextButton,
          IconButton,
        ]) {
          final size = tester.getSize(find.byType(type));
          expect(
            size.height,
            greaterThanOrEqualTo(48),
            reason: '$type at $scale',
          );
        }
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('a field with an error shows the message in the error colour', (
      tester,
    ) async {
      await tester.pumpApp(
        const Scaffold(
          body: Padding(
            padding: EdgeInsets.all(16),
            child: TextField(
              decoration: InputDecoration(
                labelText: 'Amount',
                errorText: 'Enter a valid amount',
              ),
            ),
          ),
        ),
      );
      final error = tester.widget<Text>(find.text('Enter a valid amount'));
      expect(error.style?.color, WealthColors.light.negativeText);
    });

    testWidgets('navigation labels are always visible, selected or not', (
      tester,
    ) async {
      await tester.pumpApp(
        NavigationBar(
          selectedIndex: 0,
          onDestinationSelected: (_) {},
          destinations: const [
            NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
            NavigationDestination(
              icon: Icon(Icons.pie_chart),
              label: 'Portfolio',
            ),
            NavigationDestination(icon: Icon(Icons.flag), label: 'Goals'),
          ],
        ),
      );
      for (final label in ['Home', 'Portfolio', 'Goals']) {
        expect(find.text(label), findsOneWidget);
      }
    });

    testWidgets(
      'a selected segment shows a check mark, so selection is not colour-only',
      (tester) async {
        await tester.pumpApp(
          SegmentedButton<int>(
            segments: const [
              ButtonSegment(value: 1, label: Text('One')),
              ButtonSegment(value: 2, label: Text('Two')),
            ],
            selected: const {1},
            onSelectionChanged: (_) {},
          ),
        );
        expect(find.byIcon(Icons.check), findsOneWidget);
      },
    );

    testWidgets('default text takes the primary text colour in both themes', (
      tester,
    ) async {
      for (final mode in [ThemeMode.light, ThemeMode.dark]) {
        await tester.pumpApp(
          const Material(child: Text('Hello')),
          themeMode: mode,
        );
        final style = DefaultTextStyle.of(tester.element(find.text('Hello')))
            .style;
        final expected = mode == ThemeMode.light
            ? WealthColors.light.textPrimary
            : WealthColors.dark.textPrimary;
        expect(style.color, expected);
      }
    });
  });
}

// Accessibility sweep for UX Gate 2 (P03-T07): every priority screen against Flutter's
// tap-target, label and text-contrast guidelines, in light and dark, LTR and RTL, at 1.0x and
// 2.0x text.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/ai_wealth/presentation/ai_wealth_screen.dart';
import 'package:wealthsphere_app/features/calculator/application/calculator_providers.dart';
import 'package:wealthsphere_app/features/calculator/domain/forecast_input_limits.dart';
import 'package:wealthsphere_app/features/calculator/presentation/calculator_screen.dart';
import 'package:wealthsphere_app/features/calculator/presentation/forecast/forecast_screen.dart';
import 'package:wealthsphere_app/features/dashboard/presentation/home_screen.dart';
import 'package:wealthsphere_app/features/forecast/data/forecast_repository.dart';
import 'package:wealthsphere_app/features/portfolios/presentation/portfolio_overview_screen.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../helpers/demo_overrides.dart';
import '../helpers/pump_app.dart';
import '../helpers/strict_tap_target.dart';

class _Seeded extends ForecastResultNotifier {
  _Seeded(this._result);

  final ForecastResult _result;

  @override
  ForecastResult? build() => _result;
}

/// A screen to sweep, plus anything it needs (seeded state, an action to reach content).
class _Screen {
  const _Screen(this.name, this.widget, {this.prepare});

  final String name;
  final Widget widget;
  final Future<void> Function(WidgetTester tester)? prepare;
}

Future<List<Override>> overridesFor(String name) async {
  if (name != 'Forecast') return demoOverrides();
  final response = await DemoForecastRepository(
    DemoAssets(SyncFileBundle()),
    () async {},
  ).compound(ForecastInputLimits.defaults);
  return demoOverrides(
    extra: [
      forecastResultProvider.overrideWith(
        () => _Seeded(
          ForecastResult(
            request: ForecastInputLimits.defaults,
            response: response,
          ),
        ),
      ),
    ],
  );
}

final screens = <_Screen>[
  const _Screen('Home', HomeScreen()),
  const _Screen('Portfolio', PortfolioOverviewScreen()),
  const _Screen('Calculator', CalculatorScreen()),
  const _Screen('Forecast', ForecastScreen()),
  _Screen(
    'AI Wealth',
    const AiWealthScreen(),
    prepare: (tester) async {
      // Sweep a conversation, not only the empty state.
      await tester.tap(find.text('How is my portfolio performing?'));
      await tester.pumpAndSettle();
    },
  ),
];

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  for (final screen in screens) {
    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
        for (final scale in [1.0, 2.0]) {
          testWidgets(
            '${screen.name} / ${mode.name} / ${dir.name} / ${scale}x meets the guidelines',
            (tester) async {
              final handle = tester.ensureSemantics();
              // Size the view itself (not just the test surface): Flutter's guidelines cull nodes
              // outside FlutterView.physicalSize, so the whole screen must fit in it.
              tester.view.devicePixelRatio = 3;
              tester.view.physicalSize = const Size(400 * 3, 4200 * 3);
              addTearDown(tester.view.reset);
              await tester.pumpApp(
                screen.widget,
                overrides: await overridesFor(screen.name),
                themeMode: mode,
                textDirection: dir,
                textScale: scale,
              );
              await screen.prepare?.call(tester);

              await expectLater(
                tester,
                meetsGuideline(androidTapTargetGuideline),
              );
              await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
              await expectLater(
                tester,
                meetsGuideline(labeledTapTargetGuideline),
              );
              await expectLater(
                tester,
                meetsGuideline(strictTapTargetGuideline),
              );
              // Contrast does not depend on text size; check it once per theme and direction.
              if (scale == 1.0) {
                await expectLater(
                  tester,
                  meetsGuideline(textContrastGuideline),
                );
                // Flutter's textContrastGuideline only checks text whose semantics label equals a
                // single Text widget, so text merged into cards is skipped. This checks every Text.
                await expectLater(
                  tester,
                  meetsGuideline(
                    CustomMinimumContrastGuideline(finder: find.byType(Text)),
                  ),
                );
              }
              handle.dispose();
            },
          );
        }
      }
    }
  }
}

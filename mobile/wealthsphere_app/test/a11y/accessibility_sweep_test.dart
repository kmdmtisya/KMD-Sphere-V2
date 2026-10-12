// Accessibility sweep for UX Gate 2 (P03-T07) and UX Gate 3 (P07-T09): every screen against
// Flutter's tap-target, label and text-contrast guidelines, in light and dark, LTR and RTL, at 1.0x
// and 2.0x text. (Welcome and Sign in, screens 1 and 2, are swept in
// test/features/auth/auth_screens_test.dart, which needs the sign-in fakes.)
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/security/device_authenticator.dart';
import 'package:wealthsphere_app/features/ai_wealth/doctor/presentation/doctor_screen.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/application/opportunity_providers.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/presentation/compare_screen.dart';
import 'package:wealthsphere_app/features/ai_wealth/opportunities/presentation/opportunities_screen.dart';
import 'package:wealthsphere_app/features/ai_wealth/presentation/ai_wealth_screen.dart';
import 'package:wealthsphere_app/features/calculator/application/calculator_providers.dart';
import 'package:wealthsphere_app/features/calculator/domain/forecast_input_limits.dart';
import 'package:wealthsphere_app/features/calculator/presentation/calculator_screen.dart';
import 'package:wealthsphere_app/features/calculator/presentation/forecast/forecast_screen.dart';
import 'package:wealthsphere_app/features/currency/presentation/currency_converter_screen.dart';
import 'package:wealthsphere_app/features/dashboard/presentation/home_screen.dart';
import 'package:wealthsphere_app/features/forecast/data/forecast_repository.dart';
import 'package:wealthsphere_app/features/goals/presentation/goal_detail_screen.dart';
import 'package:wealthsphere_app/features/goals/presentation/goal_form_screen.dart';
import 'package:wealthsphere_app/features/goals/presentation/goals_screen.dart';
import 'package:wealthsphere_app/features/investments/presentation/investment_detail_screen.dart';
import 'package:wealthsphere_app/features/more/presentation/income_screen.dart';
import 'package:wealthsphere_app/features/more/presentation/more_screen.dart';
import 'package:wealthsphere_app/features/more/presentation/net_worth_screen.dart';
import 'package:wealthsphere_app/features/more/presentation/settings_screen.dart';
import 'package:wealthsphere_app/features/portfolios/presentation/holdings_screen.dart';
import 'package:wealthsphere_app/features/portfolios/presentation/portfolio_overview_screen.dart';
import 'package:wealthsphere_app/features/transactions/presentation/add_transaction_screen.dart';
import 'package:wealthsphere_app/features/transactions/presentation/transaction_detail_screen.dart';
import 'package:wealthsphere_app/features/transactions/presentation/transactions_screen.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../helpers/app_lock_fakes.dart';
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
  const _Screen(this.name, this.widget, {this.prepare, this.height = 4200});

  final String name;
  final Widget widget;
  final Future<void> Function(WidgetTester tester)? prepare;

  /// Logical height of the test view: the whole screen must fit (guidelines ignore the rest).
  final double height;
}

Future<void> _tapText(WidgetTester tester, String text) async {
  await tester.ensureVisible(find.text(text).first);
  await tester.pumpAndSettle();
  await tester.tap(find.text(text).first);
  await tester.pumpAndSettle();
}

Future<void> _tapChip(WidgetTester tester, String label) async {
  await tester.tap(find.widgetWithText(ChoiceChip, label));
  await tester.pumpAndSettle();
}

Future<List<Override>> overridesFor(String name) async {
  // Settings shows the app lock with a device that can unlock (the usual case) and without one.
  if (name == 'Settings') {
    return demoOverrides(
      extra: [
        deviceAuthenticatorProvider.overrideWithValue(
          FakeDeviceAuthenticator(),
        ),
      ],
    );
  }
  if (name == 'Settings (app lock unavailable)') {
    return demoOverrides(
      extra: [
        deviceAuthenticatorProvider.overrideWithValue(
          FakeDeviceAuthenticator(available: false),
        ),
      ],
    );
  }
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
  // ---- Gate 3 (P07) ----
  _Screen('Holdings', HoldingsScreen(onOpen: (_) {})),
  const _Screen(
    'Investment details',
    InvestmentDetailScreen(symbol: 'DEMO-GEQ'),
    height: 3600,
  ),
  _Screen(
    'Investment details / Position',
    const InvestmentDetailScreen(symbol: 'DEMO-KEN'),
    prepare: (tester) => _tapChip(tester, 'Position'),
    height: 3600,
  ),
  _Screen(
    'Investment details / Transactions',
    const InvestmentDetailScreen(symbol: 'DEMO-GEQ'),
    prepare: (tester) => _tapChip(tester, 'Transactions'),
  ),
  _Screen(
    'Investment details / Research',
    const InvestmentDetailScreen(symbol: 'DEMO-GEQ'),
    prepare: (tester) => _tapChip(tester, 'Research'),
  ),
  _Screen(
    'Transactions',
    TransactionsScreen(onOpen: (_) {}, onAdd: () {}),
    height: 8000,
  ),
  _Screen(
    'Transaction detail',
    TransactionDetailScreen(
      entryId: 't-005',
      onOpenEntry: (_) {},
      onAddCorrected: (_) {},
    ),
  ),
  _Screen(
    'Add transaction (with errors)',
    const AddTransactionScreen(),
    prepare: (tester) => _tapText(tester, 'Review'),
    height: 5000,
  ),
  _Screen('Goals', GoalsScreen(onOpen: (_) {}, onAdd: () {}), height: 6000),
  _Screen(
    'Goal detail',
    GoalDetailScreen(goalId: 'g-trip', onEdit: (_) {}, onAskAi: (_) {}),
    height: 6000,
  ),
  _Screen(
    'Goal form (with errors)',
    const GoalFormScreen(),
    prepare: (tester) => _tapText(tester, 'Save goal'),
    height: 7000,
  ),
  _Screen('Portfolio Doctor', DoctorScreen(onAskAi: (_) {}), height: 9000),
  _Screen(
    'Opportunities',
    OpportunitiesScreen(onCompare: () {}, onSimulated: () {}),
    prepare: (tester) async {
      // Two ideas chosen, so the comparison bar is on screen too.
      for (final n in [0, 1]) {
        final button = find.widgetWithText(OutlinedButton, 'Compare').at(n);
        await tester.ensureVisible(button);
        await tester.pumpAndSettle();
        await tester.tap(button);
        await tester.pumpAndSettle();
      }
    },
    height: 14000,
  ),
  _Screen(
    'Compare ideas',
    const CompareScreen(),
    prepare: (tester) async {
      // Seed the selection through the provider the screen reads.
      final container = ProviderScope.containerOf(
        tester.element(find.byType(Scaffold).first),
      );
      container.read(compareSelectionProvider.notifier)
        ..toggle('o-glb')
        ..toggle('o-gov')
        ..toggle('o-new');
      await tester.pumpAndSettle();
    },
    height: 9000,
  ),
  _Screen(
    'Currency converter',
    const CurrencyConverterScreen(),
    prepare: (tester) async {
      // A demo example converted, so the result card is checked too.
      await tester.tap(find.textContaining('500000 AED'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Convert'));
      await tester.pumpAndSettle();
    },
  ),
  _Screen(
    'More',
    MoreScreen(
      onOpenNetWorth: () {},
      onOpenIncome: () {},
      onOpenCalculator: () {},
      onOpenSettings: () {},
    ),
    height: 5000,
  ),
  const _Screen('Net worth', NetWorthScreen(), height: 5000),
  const _Screen('Income', IncomeScreen(), height: 5000),
  const _Screen('Settings', SettingsScreen(), height: 6000),
  const _Screen(
    'Settings (app lock unavailable)',
    SettingsScreen(),
    height: 6000,
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
              tester.view.physicalSize = Size(400 * 3, screen.height * 3);
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

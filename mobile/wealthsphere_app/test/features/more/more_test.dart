import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/features/account/presentation/account_section.dart';
import 'package:wealthsphere_app/features/dashboard/data/dashboard_repository.dart';
import 'package:wealthsphere_app/features/more/data/more_repository.dart';
import 'package:wealthsphere_app/features/more/domain/more_models.dart';
import 'package:wealthsphere_app/features/more/presentation/income_screen.dart';
import 'package:wealthsphere_app/features/more/presentation/more_screen.dart';
import 'package:wealthsphere_app/features/more/presentation/net_worth_screen.dart';
import 'package:wealthsphere_app/features/more/presentation/settings_screen.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';
import 'package:wealthsphere_app/shared/design_system/theme/theme.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';
import '../../helpers/strict_tap_target.dart';

class _FakeMore implements MoreRepository {
  final DateTime asOf = DateTime.utc(2026, 10, 9, 8);

  @override
  Future<NetWorthDetail> netWorth() async => NetWorthDetail(
    netWorth: Money.parse('100.00', 'USD'),
    assets: NetWorthSection(
      total: Money.parse('100.00', 'USD'),
      items: [
        NetWorthItem(
          label: 'Savings',
          kind: 'cash',
          value: Money.parse('100.00', 'USD'),
          sharePercent: Decimal.parse('100'),
        ),
      ],
    ),
    liabilities: NetWorthSection(
      total: Money.parse('0.00', 'USD'),
      items: const [],
    ),
    asOf: asOf,
  );

  @override
  Future<IncomeDetail> income() async => IncomeDetail(
    monthly: Money.parse('10.00', 'USD'),
    yearly: Money.parse('120.00', 'USD'),
    bySource: const [],
    recent: const [],
    asOf: asOf,
  );
}

ProviderContainer containerOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));

Future<void> pumpScreen(
  WidgetTester tester,
  Widget screen, {
  ThemeMode mode = ThemeMode.light,
  double scale = 1.0,
  TextDirection dir = TextDirection.ltr,
  List<Override>? overrides,
  double height = 4000,
}) => tester.pumpApp(
  screen,
  themeMode: mode,
  textScale: scale,
  textDirection: dir,
  overrides: overrides ?? demoOverrides(),
  surfaceSize: Size(400, height),
);

Future<void> accessibilityChecks(WidgetTester tester) async {
  expect(tester.takeException(), isNull);
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(const StrictTapTargetGuideline()));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
}

void main() {
  setUpAll(() => initializeDateLabels(['en']));

  group('Demo data', () {
    late ProviderContainer container;
    setUp(() {
      container = ProviderContainer(overrides: demoOverrides());
      addTearDown(container.dispose);
    });

    test('net worth adds up and agrees with the Home dashboard', () async {
      final d = await container.read(moreRepositoryProvider).netWorth();
      final home = await container.read(dashboardRepositoryProvider).netWorth();
      Decimal sum(List<NetWorthItem> items) =>
          items.fold(Decimal.zero, (a, i) => a + i.value.amount);
      expect(sum(d.assets.items), d.assets.total.amount);
      expect(sum(d.liabilities.items), d.liabilities.total.amount);
      expect(
        d.assets.total.amount - d.liabilities.total.amount,
        d.netWorth.amount,
      );
      expect(d.netWorth.amount, home.netWorth.amount);
      expect(d.assets.total.amount, home.assets.amount);
      expect(d.liabilities.total.amount, home.liabilities.amount);
      expect(d.asOf, home.asOf);
    });

    test('asset shares add up to 100 within rounding', () async {
      final d = await container.read(moreRepositoryProvider).netWorth();
      final total = d.assets.items.fold(
        Decimal.zero,
        (a, i) => a + i.sharePercent!,
      );
      expect(
        (total - Decimal.fromInt(100)).abs() <= Decimal.parse('0.05'),
        isTrue,
      );
    });

    test('income adds up and agrees with the Home dashboard', () async {
      final d = await container.read(moreRepositoryProvider).income();
      final home = await container.read(dashboardRepositoryProvider).income();
      final sum = d.bySource.fold(Decimal.zero, (a, s) => a + s.yearly.amount);
      expect(sum, d.yearly.amount);
      expect(d.monthly.amount, home.monthly.amount);
      expect(d.yearly.amount, home.yearly.amount);
      expect(d.recent, isNotEmpty);
      final shares = d.bySource.fold(
        Decimal.zero,
        (a, s) => a + s.sharePercent!,
      );
      expect(
        (shares - Decimal.fromInt(100)).abs() <= Decimal.parse('0.05'),
        isTrue,
      );
    });
  });

  group('MoreScreen', () {
    testWidgets('lists the wealth views, tools and settings in sections', (
      tester,
    ) async {
      await pumpScreen(tester, const MoreScreen());
      for (final t in [
        'Your wealth',
        'Net worth',
        'Income',
        'Compounding calculator',
        'Coming soon',
        'Watchlist and alerts',
        'Reports',
        'Documents',
        'App',
        'Settings',
      ]) {
        expect(find.text(t), findsWidgets, reason: t);
      }
      expect(find.text('DEMO'), findsWidgets);
    });

    testWidgets('unavailable entries say Coming soon and cannot be opened', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      var opened = 0;
      await pumpScreen(
        tester,
        MoreScreen(
          onOpenNetWorth: () => opened++,
          onOpenIncome: () => opened++,
          onOpenCalculator: () => opened++,
          onOpenSettings: () => opened++,
        ),
      );
      // The section heading plus one label under each of the two entries.
      expect(find.text('Coming soon'), findsNWidgets(3));
      for (final name in ['Reports', 'Documents']) {
        await tester.tap(find.text(name));
      }
      expect(opened, 0);
      expect(
        find.bySemanticsLabel('Reports, coming soon, not available yet'),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('available entries open', (tester) async {
      final opened = <String>[];
      await pumpScreen(
        tester,
        MoreScreen(
          onOpenNetWorth: () => opened.add('nw'),
          onOpenIncome: () => opened.add('income'),
          onOpenCalculator: () => opened.add('calc'),
          onOpenSettings: () => opened.add('settings'),
          onOpenAlerts: () => opened.add('alerts'),
        ),
      );
      await tester.tap(find.text('Net worth'));
      await tester.tap(find.text('Income'));
      await tester.tap(find.text('Compounding calculator'));
      await tester.tap(find.text('Watchlist and alerts'));
      await tester.tap(find.text('Settings'));
      expect(opened, ['nw', 'income', 'calc', 'alerts', 'settings']);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpScreen(
                tester,
                MoreScreen(
                  onOpenNetWorth: () {},
                  onOpenIncome: () {},
                  onOpenCalculator: () {},
                  onOpenSettings: () {},
                  onOpenAlerts: () {},
                ),
                mode: mode,
                scale: scale,
                dir: dir,
                height: 5000,
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('NetWorthScreen', () {
    testWidgets('shows net worth, assets and liabilities with their items', (
      tester,
    ) async {
      await pumpScreen(tester, const NetWorthScreen());
      expect(find.text('\$168,286.35'), findsOneWidget);
      expect(find.text('Assets'), findsOneWidget);
      expect(find.text('Liabilities'), findsOneWidget);
      expect(find.text('\$186,486.35'), findsOneWidget);
      expect(find.text('Investment portfolios'), findsOneWidget);
      expect(find.text('Car loan'), findsOneWidget);
      expect(find.text('75.1% of assets'), findsOneWidget);
      expect(find.textContaining('Calculated by the server'), findsOneWidget);
      expect(find.textContaining('your estimate'), findsWidgets);
    });

    testWidgets('no liabilities says so', (tester) async {
      await pumpScreen(
        tester,
        const NetWorthScreen(),
        overrides: demoOverrides(
          extra: [moreRepositoryProvider.overrideWithValue(_FakeMore())],
        ),
      );
      expect(find.text('No liabilities recorded.'), findsOneWidget);
    });

    testWidgets('failure shows an error with retry, then recovers', (
      tester,
    ) async {
      await pumpScreen(
        tester,
        const NetWorthScreen(),
        overrides: demoOverrides(
          behavior: const DemoBehavior(
            latency: Duration.zero,
            failNextCalls: 1,
          ),
        ),
      );
      expect(find.text('Assets'), findsNothing);
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.text('Assets'), findsOneWidget);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpScreen(
                tester,
                const NetWorthScreen(),
                mode: mode,
                scale: scale,
                dir: dir,
                height: 5000,
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('IncomeScreen', () {
    testWidgets('shows the averages, sources and recent payments', (
      tester,
    ) async {
      await pumpScreen(tester, const IncomeScreen());
      expect(find.text('\$1,245.30'), findsOneWidget);
      expect(find.text('\$14,943.60'), findsOneWidget);
      expect(find.text('Dividends'), findsOneWidget);
      expect(find.text('61.0%'), findsOneWidget);
      expect(
        find.textContaining('Dividend · Demo Global Equity Fund'),
        findsOneWidget,
      );
      expect(find.text('+\$184.20'), findsOneWidget);
    });

    testWidgets('says it is not a forecast', (tester) async {
      await pumpScreen(tester, const IncomeScreen());
      expect(find.textContaining('not a forecast'), findsOneWidget);
    });

    testWidgets('no recent payments says so', (tester) async {
      await pumpScreen(
        tester,
        const IncomeScreen(),
        overrides: demoOverrides(
          extra: [moreRepositoryProvider.overrideWithValue(_FakeMore())],
        ),
      );
      expect(find.text('No recent payments.'), findsOneWidget);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpScreen(
                tester,
                const IncomeScreen(),
                mode: mode,
                scale: scale,
                dir: dir,
                height: 5000,
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('SettingsScreen', () {
    testWidgets(
      'has the account, appearance, security, preferences and about',
      (tester) async {
        await pumpScreen(tester, const SettingsScreen());
        expect(find.byType(AccountSection), findsOneWidget);
        for (final t in [
          'Appearance',
          'Security',
          'Preferences',
          'About',
          'System',
          'Light',
          'Dark',
        ]) {
          expect(find.text(t), findsWidgets, reason: t);
        }
        expect(find.textContaining('never places trades'), findsOneWidget);
        expect(find.textContaining('Demo build'), findsOneWidget);
      },
    );

    testWidgets('unavailable preferences are labelled Coming soon', (
      tester,
    ) async {
      await pumpScreen(tester, const SettingsScreen());
      expect(find.text('Notifications'), findsOneWidget);
      expect(find.text('Coming soon'), findsOneWidget);
      // The reporting currency is available since P11-T07: a real setting, not "Coming soon".
      expect(
        find.byKey(const ValueKey('reporting-currency-tile')),
        findsOneWidget,
      );
    });

    testWidgets('the theme can be changed', (tester) async {
      await pumpScreen(tester, const SettingsScreen());
      await tester.tap(find.text('Dark'));
      await tester.pumpAndSettle();
      expect(containerOf(tester).read(themeModeProvider), ThemeMode.dark);
    });

    for (final mode in [ThemeMode.light, ThemeMode.dark]) {
      for (final scale in [1.0, 2.0]) {
        for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
          testWidgets(
            'meets the accessibility guidelines (${mode.name}, ${scale}x, ${dir.name})',
            (tester) async {
              final handle = tester.ensureSemantics();
              await pumpScreen(
                tester,
                const SettingsScreen(),
                mode: mode,
                scale: scale,
                dir: dir,
                height: 6000,
              );
              await accessibilityChecks(tester);
              handle.dispose();
            },
          );
        }
      }
    }
  });

  group('Routes', () {
    testWidgets('the More tab opens each view and back returns', (
      tester,
    ) async {
      await pumpRouterApp(
        tester,
        initialLocation: '/more',
        surfaceSize: const Size(400, 3000),
      );
      expect(find.byType(MoreScreen), findsOneWidget);

      for (final (label, type) in <(String, Type)>[
        ('Net worth', NetWorthScreen),
        ('Income', IncomeScreen),
        ('Settings', SettingsScreen),
      ]) {
        await tester.tap(find.text(label));
        await tester.pumpAndSettle();
        expect(find.byType(type), findsOneWidget, reason: label);
        await tester.tap(find.byType(BackButton));
        await tester.pumpAndSettle();
        expect(find.byType(MoreScreen), findsOneWidget, reason: label);
      }
    });

    testWidgets('deep links open the views', (tester) async {
      for (final (path, type) in <(String, Type)>[
        ('/more/net-worth', NetWorthScreen),
        ('/more/income', IncomeScreen),
        ('/more/settings', SettingsScreen),
      ]) {
        await pumpRouterApp(
          tester,
          initialLocation: path,
          surfaceSize: const Size(400, 3000),
        );
        expect(find.byType(type), findsOneWidget, reason: path);
      }
    });
  });
}

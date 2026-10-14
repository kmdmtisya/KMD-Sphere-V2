import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/features/forex/application/forex_providers.dart';
import 'package:wealthsphere_app/features/forex/data/forex_repository.dart';
import 'package:wealthsphere_app/features/forex/data/forex_stream.dart';
import 'package:wealthsphere_app/features/forex/data/live_forex_repository.dart';
import 'package:wealthsphere_app/features/forex/domain/forex_models.dart';
import 'package:wealthsphere_app/features/forex/presentation/forex_calendar_screen.dart';
import 'package:wealthsphere_app/features/forex/presentation/forex_home_screen.dart';
import 'package:wealthsphere_app/features/forex/presentation/forex_opportunities_screen.dart';
import 'package:wealthsphere_app/features/forex/presentation/forex_pair_screen.dart';
import 'package:wealthsphere_app/features/forex/presentation/forex_paper_screen.dart';
import 'package:wealthsphere_app/features/forex/presentation/forex_risk_screen.dart';

import '../../helpers/demo_overrides.dart';
import '../../helpers/fake_api.dart';
import '../../helpers/pump_app.dart';
import '../../helpers/pump_router.dart';

/// The forex screens in DEMO mode (P13-T11.10): every screen loads its data, prices always show
/// their type and freshness (none is shown as an executable quote), PAPER TRADING and DEMO labels
/// are visible, forecasts carry their calibration label, the calculator shows its disclosures,
/// and the screens hold up at 2.0x text, in RTL and in dark mode. The forex entry exists only
/// when the section is available.
class QuietStream implements ForexQuoteStream {
  @override
  Stream<ForexQuote> get quotes => const Stream.empty();

  @override
  Stream<StreamState> get states => Stream.value(StreamState.live);

  @override
  StreamState get state => StreamState.live;

  @override
  void follow(Set<String> instruments) {}

  @override
  Future<void> start() async {}

  @override
  Future<void> pause() async {}

  @override
  Future<void> resume() async {}

  @override
  Future<void> dispose() async {}
}

List<Override> demo() => demoOverrides(
  extra: [forexStreamProvider.overrideWithValue(QuietStream())],
);

const tall = Size(420, 3200);

Widget home() => ForexHomeScreen(
  onOpenPair: (_) {},
  onOpenOpportunities: () {},
  onOpenRisk: () {},
  onOpenCalendar: () {},
  onOpenPaper: () {},
  onOpenCopilot: () {},
);

void main() {
  testWidgets(
    'home: simulated prices with their type, a stale one labelled, links',
    (tester) async {
      await tester.pumpApp(home(), overrides: demo(), surfaceSize: tall);
      expect(find.text('Forex Intelligence'), findsOneWidget);
      expect(find.text('EUR/USD'), findsOneWidget);
      expect(find.text('Simulated'), findsNWidgets(6));
      expect(
        find.text('Stale'),
        findsOneWidget,
      ); // USD/KES: never shown as current
      expect(find.text('Tradable quote'), findsNothing);
      for (final link in [
        'Opportunity Ranking',
        'Trade setup and risk',
        'Economic calendar',
        'Paper trading',
        'Ask the Copilot',
      ]) {
        expect(find.text(link), findsOneWidget);
      }
      expect(
        find.text('Remind me before high-importance events'),
        findsOneWidget,
      );
      await tester.tap(find.text('Tell me when a paper position closes'));
      await tester.pumpAndSettle();
      final toggles = tester.widgetList<SwitchListTile>(
        find.byType(SwitchListTile),
      );
      expect(toggles.map((t) => t.value), [true, false]);
    },
  );

  testWidgets(
    'pair: chart, indicators, levels, forecasts with labels, backtests',
    (tester) async {
      String? trade;
      await tester.pumpApp(
        ForexPairScreen(instrument: 'EUR_USD', onSetUpTrade: (i) => trade = i),
        overrides: demo(),
        surfaceSize: tall,
      );
      expect(
        find.bySemanticsLabel(RegExp('Price chart of EUR/USD: 60 bars')),
        findsOneWidget,
      );
      expect(find.text('RSI'), findsOneWidget);
      expect(find.textContaining('support at 1.0832'), findsOneWidget);
      expect(find.text('Calibrated'), findsOneWidget);
      expect(find.text('Requires calibration: not reliable'), findsOneWidget);
      expect(
        find.textContaining('56.12% probability of a rise over 4h'),
        findsOneWidget,
      );
      expect(find.textContaining('42 out-of-sample trades'), findsOneWidget);
      await tester.tap(find.text('Set up a trade'));
      expect(trade, 'EUR_USD');
    },
  );

  testWidgets('ranking: research candidates, filtered by the scanner', (
    tester,
  ) async {
    await tester.pumpApp(
      ForexOpportunitiesScreen(onOpenPair: (_) {}),
      overrides: demo(),
      surfaceSize: tall,
    );
    expect(find.textContaining('Research candidate ·'), findsNWidgets(2));
    expect(find.textContaining('not a recommendation'), findsOneWidget);
    await tester.tap(find.widgetWithText(ChoiceChip, 'low'));
    await tester.pumpAndSettle();
    expect(find.text('AUD/USD'), findsOneWidget);
    expect(find.text('EUR/USD'), findsNothing);
  });

  testWidgets(
    'risk: fields are checked; the result shows warnings and disclosures',
    (tester) async {
      await tester.pumpApp(
        const ForexRiskScreen(),
        overrides: demo(),
        surfaceSize: tall,
      );
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
      expect(
        find.text('Enter a plain number, for example 1.0850'),
        findsNWidgets(2),
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Entry'),
        '1.10000',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Stop-loss'),
        '1.09500',
      );
      await tester.tap(find.text('Calculate'));
      await tester.pumpAndSettle();
      expect(find.text('Size 0.19 lots (19000 units)'), findsOneWidget);
      expect(find.textContaining('gap or slip'), findsOneWidget);
      expect(find.textContaining('unreviewed defaults'), findsOneWidget);
    },
  );

  testWidgets('calendar: DEMO events and consensus labelled as not a fact', (
    tester,
  ) async {
    await tester.pumpApp(
      const ForexCalendarScreen(),
      overrides: demo(),
      surfaceSize: tall,
    );
    expect(find.text('DEMO event'), findsNWidgets(3));
    expect(find.text('Consensus (not a fact) 155k'), findsOneWidget);
    expect(find.text('Actual 0.4%'), findsOneWidget);
  });

  testWidgets('paper: PAPER TRADING is always visible; DEMO is read-only', (
    tester,
  ) async {
    await tester.pumpApp(
      const ForexPaperScreen(),
      overrides: demo(),
      surfaceSize: tall,
    );
    expect(find.bySemanticsLabel(RegExp('^PAPER TRADING')), findsOneWidget);
    expect(find.textContaining('Long 0.1 lots at 1.0849'), findsOneWidget);
    expect(find.textContaining('never combined'), findsOneWidget);
    await tester.tap(find.text('Close at market'));
    await tester.pumpAndSettle();
    expect(
      find.text('In DEMO mode paper trading shows sample data only.'),
      findsOneWidget,
    );
    await tester.tap(find.text('Closed'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Realised 86.4 USD (target)'), findsOneWidget);
  });

  for (final (name, theme, scale, direction) in [
    ('2.0x text', ThemeMode.light, 2.0, TextDirection.ltr),
    ('RTL', ThemeMode.light, 1.0, TextDirection.rtl),
    ('dark', ThemeMode.dark, 1.0, TextDirection.ltr),
  ]) {
    testWidgets('every forex screen lays out in $name', (tester) async {
      for (final screen in <Widget>[
        home(),
        ForexPairScreen(instrument: 'EUR_USD', onSetUpTrade: (_) {}),
        ForexOpportunitiesScreen(onOpenPair: (_) {}),
        const ForexRiskScreen(),
        const ForexCalendarScreen(),
        const ForexPaperScreen(),
      ]) {
        await tester.pumpApp(
          screen,
          overrides: demo(),
          themeMode: theme,
          textScale: scale,
          textDirection: direction,
          surfaceSize: const Size(390, 6000),
        );
        expect(
          tester.takeException(),
          isNull,
          reason: '${screen.runtimeType} in $name',
        );
      }
    });
  }

  testWidgets('More shows the forex entry in DEMO and opens it', (
    tester,
  ) async {
    await pumpRouterApp(tester, initialLocation: '/more', overrides: demo());
    expect(find.text('Forex Intelligence'), findsOneWidget);
    await tester.tap(find.text('Forex Intelligence'));
    await tester.pumpAndSettle();
    expect(find.text('Markets'), findsOneWidget);
  });

  testWidgets(
    'with forex switched off on the server, More has no forex entry',
    (tester) async {
      final api =
          FakeApi(); // every forex route answers 404, as with the flag off
      await pumpRouterApp(
        tester,
        initialLocation: '/more',
        overrides: demoOverrides(
          extra: [
            forexStreamProvider.overrideWithValue(QuietStream()),
            forexRepositoryProvider.overrideWithValue(
              LiveForexRepository(api.dio()),
            ),
            forexAvailableProvider.overrideWith((ref) async {
              try {
                await ref.watch(forexRepositoryProvider).quotes();
                return true;
              } on Object {
                return false;
              }
            }),
          ],
        ),
      );
      expect(find.text('Forex Intelligence'), findsNothing);
      expect(api.callsTo('GET', '/api/v1/forex/quotes'), hasLength(1));
    },
  );
}

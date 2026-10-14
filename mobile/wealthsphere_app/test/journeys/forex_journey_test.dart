import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/features/forex/application/forex_providers.dart';

import '../features/forex/forex_screens_test.dart' show QuietStream;
import '../helpers/demo_overrides.dart';
import '../helpers/pump_router.dart';

/// The forex journey through the real routes (P13-T11.10), in DEMO mode: More, Forex
/// Intelligence, a pair, "Set up a trade", the calculator's result with its disclosures, then
/// back to paper trading with its PAPER TRADING label.
void main() {
  testWidgets('More → Forex → pair → trade setup → paper trading', (
    tester,
  ) async {
    await pumpRouterApp(
      tester,
      initialLocation: '/more',
      surfaceSize: const Size(420, 2400),
      overrides: demoOverrides(
        extra: [forexStreamProvider.overrideWithValue(QuietStream())],
      ),
    );
    await tester.tap(find.text('Forex Intelligence'));
    await tester.pumpAndSettle();
    expect(find.text('Markets'), findsOneWidget);

    await tester.tap(find.text('EUR/USD'));
    await tester.pumpAndSettle();
    expect(find.text('Model forecasts'), findsOneWidget);

    await tester.tap(find.text('Set up a trade'));
    await tester.pumpAndSettle();
    expect(find.text('Trade setup and risk'), findsOneWidget);
    expect(
      tester
          .widget<EditableText>(find.byType(EditableText).first)
          .controller
          .text,
      'EUR_USD',
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
    expect(find.textContaining('gap or slip'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Paper trading'));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(RegExp('^PAPER TRADING')), findsOneWidget);
  });
}

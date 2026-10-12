import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/features/portfolios/application/holdings_query.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/money.dart';
import 'package:wealthsphere_app/shared/domain/wealth_models.dart';

import '../../../helpers/pump_app.dart';

HoldingSummary holding(
  String name, {
  String? symbol,
  String? value,
  String? change,
}) => HoldingSummary(
  symbol: symbol,
  name: name,
  assetClass: 'Stocks',
  value: value == null ? null : Money(Decimal.parse(value), 'USD'),
  nativeValue: value == null ? null : Money(Decimal.parse(value), 'USD'),
  changePercent: change == null ? null : Decimal.parse(change),
  asOf: null,
);

void main() {
  group('DataQualityNotice', () {
    testWidgets('is silent when the figures are complete and current', (
      tester,
    ) async {
      await tester.pumpApp(const DataQualityNotice(complete: true));
      expect(find.byType(Text), findsNothing);
    });

    testWidgets('says the total may be incomplete', (tester) async {
      await tester.pumpApp(const DataQualityNotice(complete: false));
      expect(find.textContaining('may be incomplete'), findsOneWidget);
    });

    testWidgets('counts stale prices, singular and plural', (tester) async {
      await tester.pumpApp(
        const DataQualityNotice(complete: true, stalePriceCount: 1),
      );
      expect(find.textContaining('1 price is out of date'), findsOneWidget);
      await tester.pumpApp(
        const DataQualityNotice(complete: true, stalePriceCount: 3),
      );
      expect(find.textContaining('3 prices are out of date'), findsOneWidget);
    });
  });

  group('InvestmentRow without a value or ticker', () {
    testWidgets('says "No value yet" instead of zero', (tester) async {
      await tester.pumpApp(
        const Scaffold(
          body: InvestmentRow(symbol: null, name: 'My flat', value: null),
        ),
      );
      expect(find.text('No value yet'), findsOneWidget);
      expect(find.text('My flat'), findsOneWidget);
      expect(find.textContaining(r'$0'), findsNothing);
    });
  });

  group('holdings sorting with missing figures', () {
    final all = [
      holding('No price'),
      holding('Small', symbol: 'SML', value: '10.00', change: '1.0'),
      holding('Large', symbol: 'LRG', value: '99.00', change: '-2.0'),
    ];

    List<String> names(HoldingSort sort) => [
      for (final h in applyQuery(all, HoldingsQuery(sort: sort))) h.name,
    ];

    test('unpriced positions sort last in both directions', () {
      expect(names(HoldingSort.valueDesc), ['Large', 'Small', 'No price']);
      expect(names(HoldingSort.valueAsc), ['Small', 'Large', 'No price']);
    });

    test('positions without a change sort last in both directions', () {
      expect(names(HoldingSort.changeDesc), ['Small', 'Large', 'No price']);
      expect(names(HoldingSort.changeAsc), ['Large', 'Small', 'No price']);
    });

    test('search tolerates a missing ticker', () {
      final found = applyQuery(all, const HoldingsQuery(search: 'price'));
      expect([for (final h in found) h.name], ['No price']);
    });
  });
}

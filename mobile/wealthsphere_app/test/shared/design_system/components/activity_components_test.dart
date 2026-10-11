import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';
import 'package:wealthsphere_app/shared/design_system/formatting/formatting.dart';

import '../../../helpers/pump_app.dart';
import '../../../helpers/strict_tap_target.dart';

Money usd(String amount) => Money.parse(amount, 'USD');
Decimal d(String value) => Decimal.parse(value);
final now = DateTime.utc(2026, 10, 9, 12);
final day = DateTime.utc(2026, 10, 2);

Widget page(Widget child) => Scaffold(
  body: SingleChildScrollView(padding: const EdgeInsets.all(16), child: child),
);

/// The spoken text of the tile, card or label whose visible text includes [text].
String spokenOf(WidgetTester tester, Finder inside) {
  final node = tester.getSemantics(inside);
  return node.label;
}

void main() {
  group('TransactionTile', () {
    testWidgets('a purchase: type, detail, date, money out and fee', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          TransactionTile(
            kind: TransactionKind.buy,
            date: day,
            amount: usd('1004.00'),
            assetName: 'Demo Fund',
            quantity: '10',
            unitPrice: r'$100.00',
            fee: usd('4.00'),
          ),
        ),
      );
      expect(find.text('Buy'), findsOneWidget);
      expect(find.text(r'Demo Fund · 10 at $100.00'), findsOneWidget);
      expect(find.text('Money out'), findsOneWidget);
      expect(find.textContaining(r'$1,004.00'), findsOneWidget);
      expect(find.text(r'Fee $4.00'), findsOneWidget);
    });

    testWidgets('money in has a plus sign, money out a minus sign', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          Column(
            children: [
              TransactionTile(
                kind: TransactionKind.dividend,
                date: day,
                amount: usd('30.00'),
              ),
              TransactionTile(
                kind: TransactionKind.withdrawal,
                date: day,
                amount: usd('45.00'),
              ),
            ],
          ),
        ),
      );
      expect(find.textContaining(r'+$30.00'), findsOneWidget);
      expect(find.textContaining(r'-$45.00'), findsOneWidget);
      expect(find.text('Money in'), findsOneWidget);
      expect(find.text('Money out'), findsOneWidget);
    });

    testWidgets('transfers and valuation adjustments move no cash', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          TransactionTile(
            kind: TransactionKind.transferIn,
            date: day,
            amount: usd('1200.00'),
          ),
        ),
      );
      expect(find.text('No cash movement'), findsOneWidget);
      expect(find.textContaining('+'), findsNothing);
    });

    testWidgets('a reversed entry is struck through and says so', (
      tester,
    ) async {
      await tester.pumpApp(
        page(
          TransactionTile(
            kind: TransactionKind.deposit,
            date: day,
            amount: usd('500.00'),
            reversed: true,
          ),
        ),
      );
      expect(find.text('Reversed'), findsOneWidget);
      final title = tester.widget<Text>(find.text('Deposit'));
      expect(title.style?.decoration, TextDecoration.lineThrough);
    });

    testWidgets('is read as one phrase and taps', (tester) async {
      final handle = tester.ensureSemantics();
      var taps = 0;
      await tester.pumpApp(
        page(
          TransactionTile(
            kind: TransactionKind.sell,
            date: day,
            amount: usd('700.00'),
            assetName: 'Demo Fund',
            reversed: true,
            onTap: () => taps++,
          ),
        ),
      );
      final label = spokenOf(tester, find.byType(TransactionTile));
      expect(label, contains('Sell'));
      expect(label, contains('Demo Fund'));
      expect(label, contains('Money in'));
      expect(label, contains(r'$700.00'));
      expect(label, contains('Reversed'));
      await tester.tap(find.byType(TransactionTile));
      expect(taps, 1);
      handle.dispose();
    });

    test('every API type parses and has a label', () {
      for (final name in [
        'BUY',
        'SELL',
        'DEPOSIT',
        'WITHDRAWAL',
        'DIVIDEND',
        'INTEREST',
        'COUPON',
        'RENT',
        'DISTRIBUTION',
        'FEE',
        'TAX',
        'TRANSFER_IN',
        'TRANSFER_OUT',
        'VALUATION_ADJUSTMENT',
      ]) {
        expect(
          TransactionKind.parse(name),
          isA<TransactionKind>(),
          reason: name,
        );
      }
      expect(TransactionKind.values, hasLength(14));
      expect(() => TransactionKind.parse('GIFT'), throwsFormatException);
    });
  });

  group('GoalProgressCard', () {
    GoalProgressCard card({
      String percent = '62',
      GoalProgressStatus status = GoalProgressStatus.onTrack,
      Money? current,
    }) => GoalProgressCard(
      name: 'House deposit',
      progressPercent: d(percent),
      status: status,
      target: usd('50000.00'),
      targetDate: DateTime.utc(2028, 6, 1),
      current: current ?? usd('31000.00'),
    );

    testWidgets('the ring has a numeric label and a text status', (
      tester,
    ) async {
      await tester.pumpApp(page(card()));
      expect(find.text('62%'), findsOneWidget);
      expect(find.text('on track'), findsOneWidget);
      expect(find.text('House deposit'), findsOneWidget);
      expect(find.textContaining(r'Target $50,000.00 by'), findsOneWidget);
      expect(find.textContaining(r'Now $31,000.00'), findsOneWidget);
      expect(find.textContaining('not guaranteed'), findsOneWidget);
    });

    for (final (status, word) in [
      (GoalProgressStatus.onTrack, 'on track'),
      (GoalProgressStatus.behind, 'behind'),
      (GoalProgressStatus.reached, 'reached'),
    ]) {
      testWidgets('status ${status.name} is a word and an icon', (
        tester,
      ) async {
        await tester.pumpApp(page(card(status: status)));
        expect(find.text(word), findsOneWidget);
        final row = find.ancestor(
          of: find.text(word),
          matching: find.byType(Row),
        );
        expect(
          find.descendant(of: row.first, matching: find.byType(Icon)),
          findsOneWidget,
        );
      });
    }

    testWidgets('is read as one phrase with the estimate wording', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(
        page(card(percent: '18', status: GoalProgressStatus.behind)),
      );
      final label = spokenOf(tester, find.byType(GoalProgressCard));
      expect(label, contains('House deposit: 18% complete, behind'));
      expect(label, contains('not guaranteed'));
      handle.dispose();
    });

    testWidgets('out-of-range progress is drawn clamped, shown as given', (
      tester,
    ) async {
      await tester.pumpApp(page(card(percent: '140')));
      expect(find.text('140%'), findsOneWidget);
      await tester.pumpApp(page(card(percent: '-5')));
      expect(find.text('-5%'), findsOneWidget);
    });

    testWidgets('works without a current value and taps', (tester) async {
      var taps = 0;
      await tester.pumpApp(
        page(
          GoalProgressCard(
            name: 'Goal',
            progressPercent: d('0'),
            status: GoalProgressStatus.behind,
            target: usd('100.00'),
            targetDate: DateTime.utc(2030, 1, 1),
            onTap: () => taps++,
          ),
        ),
      );
      expect(find.textContaining('Now'), findsNothing);
      await tester.tap(find.byType(GoalProgressCard));
      expect(taps, 1);
    });
  });

  group('PortfolioHealthCard', () {
    const findings = [
      HealthFinding(
        kind: HealthFindingKind.concentration,
        severity: RiskLevel.high,
        title: 'One position is 52%',
        explanation: 'It is the largest part of the value.',
      ),
      HealthFinding(
        kind: HealthFindingKind.currency,
        severity: RiskLevel.low,
        title: '38% in one currency',
        explanation: 'Exchange rates affect it.',
      ),
    ];

    testWidgets('lists each finding with kind, severity and explanation', (
      tester,
    ) async {
      await tester.pumpApp(
        page(PortfolioHealthCard(findings: findings, asOf: now, now: now)),
      );
      expect(find.text('Portfolio health'), findsOneWidget);
      expect(find.text('2 findings'), findsOneWidget);
      expect(find.text('Concentration'), findsOneWidget);
      expect(find.text('High risk'), findsOneWidget);
      expect(find.text('One position is 52%'), findsOneWidget);
      expect(find.text('Exchange rates affect it.'), findsOneWidget);
      expect(find.textContaining('not advice'), findsOneWidget);
      expect(find.textContaining('As of'), findsOneWidget);
    });

    testWidgets('counts one, none and many', (tester) async {
      await tester.pumpApp(
        page(PortfolioHealthCard(findings: findings.sublist(0, 1))),
      );
      expect(find.text('1 finding'), findsOneWidget);
      await tester.pumpApp(page(const PortfolioHealthCard(findings: [])));
      expect(find.text('No findings'), findsOneWidget);
      expect(
        find.text('Nothing to flag from the checks that could be run.'),
        findsOneWidget,
      );
    });

    testWidgets('is read as one phrase', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(const PortfolioHealthCard(findings: findings)));
      final label = spokenOf(tester, find.byType(PortfolioHealthCard));
      expect(label, contains('Portfolio health, 2 findings'));
      expect(label, contains('Concentration, High risk: One position is 52%'));
      expect(label, contains('not advice'));
      handle.dispose();
    });
  });

  group('OpportunityCard', () {
    OpportunityCard card({
      List<EvidenceSource>? evidence,
      int? score = 72,
      bool isDemo = true,
      VoidCallback? onResearch,
    }) => OpportunityCard(
      name: 'Demo Dividend Fund',
      symbol: 'DEMO3',
      assetClass: 'Equity fund',
      summary: 'Pays a steady income.',
      risk: RiskLevel.medium,
      score: score,
      scoreExplanation: score == null
          ? null
          : const Text('Weighted from four parts.'),
      risks: const ['Dividends can be cut.'],
      evidence:
          evidence ??
          [
            EvidenceSource(
              label: 'Factsheet',
              provider: 'Demo Data Co.',
              asOf: now.subtract(const Duration(days: 2)),
            ),
          ],
      asOf: now.subtract(const Duration(hours: 3)),
      now: now,
      isDemo: isDemo,
      onResearch: onResearch,
    );

    testWidgets('shows risk, evidence, data-as-of and the score explanation', (
      tester,
    ) async {
      await tester.pumpApp(page(card()), surfaceSize: const Size(400, 1400));
      expect(find.text('DEMO3 · Demo Dividend Fund'), findsOneWidget);
      expect(find.text('Medium risk'), findsOneWidget);
      expect(find.text('Research score 72 of 100'), findsWidgets);
      expect(find.text('How this score is made'), findsOneWidget);
      expect(find.text('Evidence'), findsOneWidget);
      expect(find.byType(EvidenceSourceChip), findsOneWidget);
      expect(find.text('As of 3 hours ago'), findsOneWidget);
      expect(find.text('Dividends can be cut.'), findsOneWidget);
      expect(find.text('DEMO'), findsOneWidget);
      expect(find.textContaining('never guaranteed'), findsOneWidget);
    });

    testWidgets('the score explanation opens', (tester) async {
      await tester.pumpApp(page(card()), surfaceSize: const Size(400, 1400));
      expect(find.text('Weighted from four parts.'), findsNothing);
      await tester.tap(find.text('How this score is made'));
      await tester.pump();
      expect(find.text('Weighted from four parts.'), findsOneWidget);
    });

    testWidgets('without evidence it says not to rely on the idea', (
      tester,
    ) async {
      await tester.pumpApp(page(card(evidence: const [], score: null)));
      expect(find.byType(EvidenceSourceChip), findsNothing);
      expect(
        find.text('No evidence yet. Do not rely on this idea.'),
        findsOneWidget,
      );
      expect(find.text('How this score is made'), findsNothing);
    });

    testWidgets('a live card has no DEMO badge', (tester) async {
      await tester.pumpApp(
        page(card(isDemo: false)),
        surfaceSize: const Size(400, 1400),
      );
      expect(find.text('DEMO'), findsNothing);
    });

    testWidgets('actions appear only when given and only navigate', (
      tester,
    ) async {
      await tester.pumpApp(page(card()), surfaceSize: const Size(400, 1400));
      expect(find.text('Research'), findsNothing);
      var researched = 0;
      await tester.pumpApp(
        page(card(onResearch: () => researched++)),
        surfaceSize: const Size(400, 1400),
      );
      await tester.tap(find.text('Research'));
      expect(researched, 1);
      expect(find.text('Compare'), findsNothing);
    });

    test('a score needs an explanation and stays within 0 to 100', () {
      expect(
        () => OpportunityCard(
          name: 'x',
          risk: RiskLevel.low,
          evidence: const [],
          asOf: now,
          score: 50,
        ),
        throwsAssertionError,
      );
      expect(
        () => OpportunityCard(
          name: 'x',
          risk: RiskLevel.low,
          evidence: const [],
          asOf: now,
          score: 101,
          scoreExplanation: const SizedBox(),
        ),
        throwsAssertionError,
      );
    });

    testWidgets('is read with its risk, score and DEMO status', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpApp(page(card()), surfaceSize: const Size(400, 1400));
      final label = spokenOf(tester, find.text('DEMO3 · Demo Dividend Fund'));
      expect(label, contains('Research candidate'));
      expect(label, contains('Medium risk'));
      expect(label, contains('Research score 72 of 100'));
      expect(label, contains('Demo data'));
      handle.dispose();
    });
  });

  group('all four', () {
    final widgets = <String, Widget>{
      'transaction': TransactionTile(
        kind: TransactionKind.buy,
        date: day,
        amount: usd('1004.00'),
        assetName: 'Demo Global Equity Fund With A Long Name',
        quantity: '10',
        unitPrice: r'$100.00',
        fee: usd('4.00'),
        onTap: () {},
      ),
      'goal': GoalProgressCard(
        name: 'A goal with a rather long name that needs to wrap',
        progressPercent: d('62'),
        status: GoalProgressStatus.onTrack,
        target: usd('50000.00'),
        targetDate: DateTime.utc(2028, 6, 1),
        current: usd('31000.00'),
        onTap: () {},
      ),
      'health': const PortfolioHealthCard(
        findings: [
          HealthFinding(
            kind: HealthFindingKind.concentration,
            severity: RiskLevel.high,
            title: 'One position is 52% of the portfolio',
            explanation: 'It is the largest part of the value.',
          ),
        ],
      ),
      'opportunity': OpportunityCard(
        name: 'Demo Dividend Fund',
        risk: RiskLevel.medium,
        score: 72,
        scoreExplanation: const Text('Weighted from four parts.'),
        evidence: [
          EvidenceSource(label: 'Factsheet', provider: 'Demo', asOf: now),
        ],
        asOf: now,
        now: now,
        isDemo: true,
        onResearch: () {},
        onCompare: () {},
        onSimulate: () {},
      ),
    };

    for (final entry in widgets.entries) {
      for (final mode in [ThemeMode.light, ThemeMode.dark]) {
        for (final scale in [1.0, 2.0]) {
          for (final dir in [TextDirection.ltr, TextDirection.rtl]) {
            testWidgets(
              '${entry.key}: ${mode.name}, ${scale}x, ${dir.name} meets the guidelines',
              (tester) async {
                final handle = tester.ensureSemantics();
                await tester.pumpApp(
                  page(entry.value),
                  themeMode: mode,
                  textScale: scale,
                  textDirection: dir,
                  surfaceSize: const Size(400, 2400),
                );
                expect(tester.takeException(), isNull);
                await expectLater(
                  tester,
                  meetsGuideline(androidTapTargetGuideline),
                );
                await expectLater(
                  tester,
                  meetsGuideline(iOSTapTargetGuideline),
                );
                await expectLater(
                  tester,
                  meetsGuideline(labeledTapTargetGuideline),
                );
                await expectLater(
                  tester,
                  meetsGuideline(const StrictTapTargetGuideline()),
                );
                await expectLater(
                  tester,
                  meetsGuideline(textContrastGuideline),
                );
                handle.dispose();
              },
            );
          }
        }
      }
    }
  });
}

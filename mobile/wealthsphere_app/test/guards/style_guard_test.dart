import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'style_rules.dart';

void main() {
  group('lib/ obeys the style rules', () {
    test(
      'no hard-coded colours, left/right layout, or double in money code',
      () {
        final violations = scanLib('lib');
        expect(violations, isEmpty, reason: violations.join('\n'));
      },
    );

    test('the colour-literal exclusion is not vacuous: brand_palette.dart does hold them', () {
      final palette = File('lib/shared/design_system/tokens/brand_palette.dart')
          .readAsStringSync();
      expect(
        RegExp(r'\bColor\(0x').allMatches(palette).length,
        greaterThan(20),
      );
      final others = scanLib('lib').where((v) => v.rule == 'hardcoded-color');
      expect(others, isEmpty);
    });
  });

  group('the scanner detects what it claims to', () {
    const lib = 'lib/features/demo/screen.dart';

    List<String> rulesFlagged(String code, {String path = lib}) =>
        scanSource(path, code).map((v) => v.rule).toSet().toList()..sort();

    test('hard-coded colours', () {
      expect(rulesFlagged('final c = Color(0xFF123456);'), ['hardcoded-color']);
      expect(rulesFlagged('final c = Color( 0xFF123456 );'), [
        'hardcoded-color',
      ]);
      expect(rulesFlagged('final c = Color.fromARGB(255, 1, 2, 3);'), [
        'color-constructor',
      ]);
      expect(rulesFlagged('final c = Color.fromRGBO(1, 2, 3, 1);'), [
        'color-constructor',
      ]);
      expect(rulesFlagged('final c = Colors.red;'), ['material-named-color']);
    });

    test('allowed colour usage is not flagged', () {
      expect(rulesFlagged('final c = Colors.transparent;'), isEmpty);
      expect(rulesFlagged('final c = context.wealthColors.primary;'), isEmpty);
      expect(
        rulesFlagged(
          'static const Color a = Color(0xFF102A43);',
          path: 'lib/shared/design_system/tokens/brand_palette.dart',
        ),
        isEmpty,
      );
    });

    test('left/right layout (not RTL-safe)', () {
      expect(rulesFlagged('EdgeInsets.only(left: 8)'), [
        'directional-edge-insets',
      ]);
      expect(rulesFlagged('EdgeInsets.only(top: 4,\n    right: 8)'), [
        'directional-edge-insets',
      ]);
      expect(rulesFlagged('EdgeInsets.fromLTRB(1, 2, 3, 4)'), [
        'directional-edge-insets',
      ]);
      expect(rulesFlagged('Alignment.centerLeft'), ['directional-alignment']);
      expect(rulesFlagged('Alignment.topRight'), ['directional-alignment']);
      expect(rulesFlagged('textAlign: TextAlign.left'), [
        'directional-text-align',
      ]);
      expect(rulesFlagged('Positioned(left: 4, child: x)'), [
        'directional-positioned',
      ]);
      expect(rulesFlagged('BorderRadius.only(topLeft: Radius.circular(8))'), [
        'directional-border-radius',
      ]);
    });

    test('directional equivalents are fine', () {
      expect(
        rulesFlagged('EdgeInsetsDirectional.only(start: 8, end: 4)'),
        isEmpty,
      );
      expect(rulesFlagged('EdgeInsets.only(top: 8, bottom: 4)'), isEmpty);
      expect(rulesFlagged('EdgeInsets.symmetric(horizontal: 8)'), isEmpty);
      expect(rulesFlagged('AlignmentDirectional.centerStart'), isEmpty);
      expect(rulesFlagged('TextAlign.start'), isEmpty);
      expect(
        rulesFlagged('PositionedDirectional(start: 4, child: x)'),
        isEmpty,
      );
      expect(
        rulesFlagged(
          'BorderRadiusDirectional.only(topStart: Radius.circular(8))',
        ),
        isEmpty,
      );
    });

    test('double/num are flagged only in money and formatting code', () {
      const code = 'double x = 1.5; num y = 2; final z = a.toDouble();';
      expect(
        rulesFlagged(
          code,
          path: 'lib/shared/design_system/formatting/money.dart',
        ),
        ['no-double-in-money-code'],
      );
      expect(
        rulesFlagged(
          code,
          path: 'lib/shared/design_system/charts/line_chart.dart',
        ),
        isEmpty,
      );
      expect(rulesFlagged(code), isEmpty);
    });

    test('comments and doc comments never trigger rules', () {
      const code = '''
// final c = Color(0xFF123456);
/// Use Alignment.centerLeft? No: use AlignmentDirectional.
/* EdgeInsets.only(left: 4) */
final ok = 1;
''';
      expect(rulesFlagged(code), isEmpty);
    });

    test('reports the correct line number', () {
      final v = scanSource(
        lib,
        'final a = 1;\n\n// note\nfinal c = Colors.red;\n',
      ).single;
      expect(v.line, 4);
      expect(v.toString(), contains('[material-named-color]'));
    });

    test('URLs inside strings are not mistaken for comments', () {
      expect(
        rulesFlagged(
          "const u = 'https://example.com/path'; final c = Colors.red;",
        ),
        ['material-named-color'],
      );
    });
  });
}

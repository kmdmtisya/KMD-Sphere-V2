import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'test_fonts.dart';

double widthOf(String text, String family) {
  final painter = TextPainter(
    text: TextSpan(
      text: text,
      style: TextStyle(fontFamily: family, fontSize: 40),
    ),
    textDirection: TextDirection.ltr,
  )..layout();
  return painter.width;
}

void main() {
  testWidgets(
    'loadTestFonts makes real, proportional Roboto available for golden tests',
    (tester) async {
      // The default test font (Ahem) draws every glyph as an identical square.
      final before = widthOf('iiii', 'Roboto') - widthOf('WWWW', 'Roboto');
      expect(
        before,
        0,
        reason: 'before loading, Roboto falls back to the square test font',
      );

      await loadTestFonts();

      final narrow = widthOf('iiii', 'Roboto');
      final wide = widthOf('WWWW', 'Roboto');
      expect(narrow, lessThan(wide), reason: 'real Roboto is proportional');
    },
  );

  testWidgets('the Material icon font is available too', (tester) async {
    await loadTestFonts();
    final icon = TextPainter(
      text: TextSpan(
        text: String.fromCharCode(Icons.check.codePoint),
        style: TextStyle(fontFamily: Icons.check.fontFamily, fontSize: 24),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    expect(icon.width, greaterThan(0));
  });
}

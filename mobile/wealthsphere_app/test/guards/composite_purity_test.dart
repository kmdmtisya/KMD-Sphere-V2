import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Composite components take plain view-models: they must not read Riverpod providers or reach
/// for repositories, so each is testable on its own (UI_EXECUTION_PLAN step 5).
void main() {
  const composites = [
    'cards.dart',
    'period_selector.dart',
    'portfolio_switcher.dart',
    'investment_row.dart',
    'scenario_card.dart',
    'evidence_source_chip.dart',
    'ai_chat_composer.dart',
  ];

  for (final name in composites) {
    test('$name does not use providers or repositories', () {
      final source = File('lib/shared/design_system/components/$name')
          .readAsStringSync();
      expect(source, isNot(contains('riverpod')));
      expect(source, isNot(contains('ref.')));
      expect(source.toLowerCase(), isNot(contains('repository')));
    });
  }

  test('chart widgets do not use providers either', () {
    final dir = Directory('lib/shared/design_system/charts');
    for (final f in dir.listSync().whereType<File>()) {
      expect(f.readAsStringSync(), isNot(contains('riverpod')), reason: f.path);
    }
  });
}

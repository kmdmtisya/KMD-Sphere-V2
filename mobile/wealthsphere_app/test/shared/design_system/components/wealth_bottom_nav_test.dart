import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/components/components.dart';

import '../../../helpers/pump_app.dart';

const destinations = [
  WealthNavDestination(
    icon: Icons.home_outlined,
    selectedIcon: Icons.home,
    label: 'Home',
  ),
  WealthNavDestination(
    icon: Icons.pie_chart_outline,
    selectedIcon: Icons.pie_chart,
    label: 'Portfolio',
  ),
  WealthNavDestination(
    icon: Icons.auto_awesome_outlined,
    selectedIcon: Icons.auto_awesome,
    label: 'AI Wealth',
  ),
  WealthNavDestination(
    icon: Icons.flag_outlined,
    selectedIcon: Icons.flag,
    label: 'Goals',
  ),
  WealthNavDestination(
    icon: Icons.more_horiz,
    selectedIcon: Icons.more_horiz,
    label: 'More',
  ),
];

Widget nav({
  int selected = 0,
  ValueChanged<int>? onSelected,
  ValueChanged<int>? onReselected,
}) => Scaffold(
  bottomNavigationBar: WealthBottomNav(
    destinations: destinations,
    selectedIndex: selected,
    onSelected: onSelected ?? (_) {},
    onReselected: onReselected,
  ),
);

void main() {
  testWidgets('all five labels are always visible', (tester) async {
    await tester.pumpApp(nav());
    for (final d in destinations) {
      expect(find.text(d.label), findsOneWidget);
    }
  });

  testWidgets('tapping another tab reports its index', (tester) async {
    final selected = <int>[];
    await tester.pumpApp(nav(onSelected: selected.add));
    await tester.tap(find.text('Goals'));
    expect(selected, [3]);
  });

  testWidgets('tapping the active tab reports a reselect, not a selection', (
    tester,
  ) async {
    final selected = <int>[];
    final reselected = <int>[];
    await tester.pumpApp(
      nav(selected: 1, onSelected: selected.add, onReselected: reselected.add),
    );
    await tester.tap(find.text('Portfolio'));
    expect(reselected, [1]);
    expect(selected, isEmpty);
  });

  testWidgets('reselect without a handler is harmless', (tester) async {
    await tester.pumpApp(nav());
    await tester.tap(find.text('Home'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('selected tab shows its filled icon', (tester) async {
    await tester.pumpApp(nav(selected: 1));
    expect(find.byIcon(Icons.pie_chart), findsOneWidget);
    expect(find.byIcon(Icons.pie_chart_outline), findsNothing);
    expect(find.byIcon(Icons.home_outlined), findsOneWidget);
  });

  testWidgets('the selected tab is announced as selected', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpApp(nav(selected: 2));
    expect(
      tester.getSemantics(find.bySemanticsLabel(RegExp('AI Wealth')).first),
      isSemantics(
        isButton: true,
        hasTapAction: true,
        hasFocusAction: true,
        isFocusable: true,
        hasSelectedState: true,
        isSelected: true,
      ),
    );
    handle.dispose();
  });

  testWidgets('every destination is at least 48 dp tall and wide', (
    tester,
  ) async {
    await tester.pumpApp(nav());
    for (final d in destinations) {
      final size = tester.getSize(
        find
            .ancestor(
              of: find.text(d.label),
              matching: find.byType(NavigationDestination),
            )
            .first,
      );
      expect(size.height, greaterThanOrEqualTo(48), reason: d.label);
      expect(size.width, greaterThanOrEqualTo(48), reason: d.label);
    }
  });

  testWidgets('needs at least two destinations', (tester) async {
    expect(
      () => WealthBottomNav(
        destinations: destinations.take(1).toList(),
        selectedIndex: 0,
        onSelected: (_) {},
      ),
      throwsAssertionError,
    );
  });

  for (final dir in TextDirection.values) {
    for (final scale in [1.0, 2.0]) {
      testWidgets(
        '320 dp wide, ${dir.name}, ${scale}x text: no overflow, labels present',
        (tester) async {
          await tester.pumpApp(
            nav(selected: 2),
            textDirection: dir,
            textScale: scale,
            surfaceSize: const Size(320, 568),
          );
          expect(tester.takeException(), isNull);
          for (final d in destinations) {
            expect(find.text(d.label), findsOneWidget);
          }
        },
      );
    }
  }

  testWidgets('RTL mirrors the order of tabs', (tester) async {
    await tester.pumpApp(nav(), textDirection: TextDirection.rtl);
    expect(
      tester.getCenter(find.text('Home')).dx,
      greaterThan(tester.getCenter(find.text('More')).dx),
    );
  });
}

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app.dart';

import '../helpers/demo_overrides.dart';

void main() {
  testWidgets('the app opens on the Home dashboard', (tester) async {
    await tester.pumpWidget(
      ProviderScope(overrides: demoOverrides(), child: const WealthSphereApp()),
    );
    await tester.pumpAndSettle();

    expect(find.text('Hello, Alex'), findsOneWidget);
    expect(find.text('Total wealth'), findsOneWidget);
  });
}

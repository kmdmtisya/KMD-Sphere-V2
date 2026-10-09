import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app.dart';

void main() {
  testWidgets('app shell renders title and tagline', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: WealthSphereApp()));
    await tester.pumpAndSettle();

    expect(find.text('WealthSphere'), findsOneWidget);
    expect(find.text('Track. Measure. Forecast. Grow.'), findsOneWidget);
  });
}

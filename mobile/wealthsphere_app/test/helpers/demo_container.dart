import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/core/data/demo_support.dart';

class _InstantBehavior extends DemoBehaviorNotifier {
  _InstantBehavior(this._initial);

  final DemoBehavior _initial;

  @override
  DemoBehavior build() => _initial;
}

/// A provider container whose demo repositories answer immediately (or with [behavior]) and read
/// the real `assets/demo` fixtures.
ProviderContainer demoContainer({
  DemoBehavior behavior = DemoBehavior.instant,
}) {
  TestWidgetsFlutterBinding.ensureInitialized();
  final container = ProviderContainer(
    overrides: [
      demoBehaviorProvider.overrideWith(() => _InstantBehavior(behavior)),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

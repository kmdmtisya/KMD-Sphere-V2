import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../shared/design_system/components/demo_badge.dart';
import 'demo_support.dart';

/// The DEMO badge for a screen whose data comes from the repositories: shown while the app runs
/// on DEMO data, absent when it runs on the API. Screens whose data is always demo (the AI
/// screens, until P10) use [DemoBadge] directly.
class DataSourceBadge extends ConsumerWidget {
  const DataSourceBadge({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      ref.watch(dataSourceModeProvider) == DataSourceMode.demo
      ? const DemoBadge()
      : const SizedBox.shrink();
}

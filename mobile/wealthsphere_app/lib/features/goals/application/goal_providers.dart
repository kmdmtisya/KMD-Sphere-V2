import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/goal_repository.dart';
import '../domain/goal_models.dart';

final goalsProvider = FutureProvider<List<GoalEntry>>(
  (ref) => ref.watch(goalRepositoryProvider).goals(),
);

final goalProvider = FutureProvider.family<GoalEntry, String>(
  (ref, id) => ref.watch(goalRepositoryProvider).goal(id),
);

/// Refreshes every goal view after a goal was added or changed.
void refreshGoals(WidgetRef ref) {
  ref
    ..invalidate(goalsProvider)
    ..invalidate(goalProvider);
}

/// The current moment; tests override it. Used for the target date rules.
final goalsTodayProvider = Provider<DateTime>((ref) => DateTime.now());

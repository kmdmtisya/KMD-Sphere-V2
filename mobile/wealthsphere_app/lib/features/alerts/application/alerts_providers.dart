import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/alerts_repository.dart';
import '../domain/alert_models.dart';

final watchlistItemsProvider = FutureProvider<List<WatchItem>>(
  (ref) => ref.watch(watchlistRepositoryProvider).items(),
);

/// Whether [assetKey] is on the watchlist; null while the list is loading or failed.
final isWatchingProvider = Provider.family<bool?, String>((ref, assetKey) {
  final items = ref.watch(watchlistItemsProvider).value;
  return items?.any((i) => i.assetKey == assetKey);
});

final alertsProvider = FutureProvider<List<PriceAlert>>(
  (ref) => ref.watch(alertRepositoryProvider).alerts(),
);

final alertEventsProvider = FutureProvider<List<AlertEvent>>(
  (ref) => ref.watch(alertRepositoryProvider).events(),
);

/// Adds or removes [assetKey], then reloads the list. Returns true when it is now watched.
Future<bool> toggleWatch(WidgetRef ref, String assetKey) async {
  final repo = ref.read(watchlistRepositoryProvider);
  final watching = ref.read(isWatchingProvider(assetKey)) ?? false;
  if (watching) {
    await repo.remove(assetKey);
  } else {
    await repo.add(assetKey);
  }
  ref.invalidate(watchlistItemsProvider);
  return !watching;
}

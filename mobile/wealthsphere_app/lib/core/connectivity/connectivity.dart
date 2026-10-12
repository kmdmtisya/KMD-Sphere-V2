import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Whether the API can be reached, judged from real requests rather than from the radio state:
/// a phone can be "connected" and still not reach the server. Set by the API client's offline
/// interceptor (and by tests).
class ConnectivityNotifier extends Notifier<bool> {
  @override
  bool build() => true;

  void setOnline({required bool online}) => state = online;

  /// A request reached the server. Coming back online drops the saved-data age and asks every
  /// live screen to load fresh data.
  void reachedServer() {
    if (state) return;
    state = true;
    ref.read(savedDataAsOfProvider.notifier).clear();
    ref.read(dataEpochProvider.notifier).bump();
  }

  /// A request could not reach the server. [savedAt] is the age of the saved copy shown instead.
  void unreachable(DateTime? savedAt) {
    state = false;
    if (savedAt != null) {
      ref.read(savedDataAsOfProvider.notifier).shown(savedAt);
    }
  }
}

final onlineProvider = NotifierProvider<ConnectivityNotifier, bool>(
  ConnectivityNotifier.new,
);

/// The oldest saved copy on screen while offline (null when nothing saved is shown).
class SavedDataAsOfNotifier extends Notifier<DateTime?> {
  @override
  DateTime? build() => null;

  void shown(DateTime savedAt) {
    final current = state;
    if (current == null || savedAt.isBefore(current)) state = savedAt;
  }

  void clear() => state = null;
}

final savedDataAsOfProvider =
    NotifierProvider<SavedDataAsOfNotifier, DateTime?>(
      SavedDataAsOfNotifier.new,
    );

/// Bumped when every live screen must load again: on reconnecting, and when the signed-in user
/// changes (so nothing loaded for one user stays on screen for the next). The API client watches
/// it, so every live repository, and every provider built on one, is rebuilt.
class DataEpochNotifier extends Notifier<int> {
  @override
  int build() => 0;

  void bump() => state++;
}

final dataEpochProvider = NotifierProvider<DataEpochNotifier, int>(
  DataEpochNotifier.new,
);

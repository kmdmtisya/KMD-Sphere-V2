import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/preferences/preferences_store.dart';
import '../domain/forex_models.dart';
import 'forex_providers.dart';

/// Forex notifications (P13-T11.8, QG-19.4): which ones the user wants, kept on the device, and
/// the in-app notices they produce. The server sends no forex push yet; these notices come from
/// data the app already loads (the calendar and the paper positions).
@immutable
class ForexAlertPrefs {
  const ForexAlertPrefs({this.eventReminders = true, this.paperExits = true});

  factory ForexAlertPrefs.decode(String? raw) {
    if (raw == null) return const ForexAlertPrefs();
    try {
      final m = jsonDecode(raw) as Map<String, dynamic>;
      return ForexAlertPrefs(
        eventReminders: m['event_reminders'] != false,
        paperExits: m['paper_exits'] != false,
      );
    } on Object {
      return const ForexAlertPrefs();
    }
  }

  final bool eventReminders;
  final bool paperExits;

  String encode() => jsonEncode({
    'event_reminders': eventReminders,
    'paper_exits': paperExits,
  });

  ForexAlertPrefs copyWith({bool? eventReminders, bool? paperExits}) =>
      ForexAlertPrefs(
        eventReminders: eventReminders ?? this.eventReminders,
        paperExits: paperExits ?? this.paperExits,
      );
}

class ForexAlertPrefsNotifier extends AsyncNotifier<ForexAlertPrefs> {
  static const key = 'forex.alert_prefs';

  @override
  Future<ForexAlertPrefs> build() async => ForexAlertPrefs.decode(
    await ref.watch(preferencesStoreProvider).getString(key),
  );

  Future<void> set(ForexAlertPrefs prefs) async {
    state = AsyncData(prefs);
    await ref.read(preferencesStoreProvider).setString(key, prefs.encode());
  }
}

final forexAlertPrefsProvider =
    AsyncNotifierProvider<ForexAlertPrefsNotifier, ForexAlertPrefs>(
      ForexAlertPrefsNotifier.new,
    );

/// One in-app notice: an event about to start, or a paper position that closed.
sealed class ForexNotice {
  const ForexNotice();
}

class EventSoonNotice extends ForexNotice {
  const EventSoonNotice(this.event, this.minutes);

  final ForexEvent event;
  final int minutes;
}

class PaperClosedNotice extends ForexNotice {
  const PaperClosedNotice(this.position);

  final PaperPosition position;
}

/// High-importance events starting within [eventWindow], and paper positions closed within
/// [closedWindow], each only when the user wants them. Pure, so it is tested on its own.
List<ForexNotice> noticesFor({
  required ForexAlertPrefs prefs,
  required List<ForexEvent> events,
  required List<PaperPosition> positions,
  required DateTime now,
  Duration eventWindow = const Duration(minutes: 60),
  Duration closedWindow = const Duration(hours: 24),
}) {
  final out = <ForexNotice>[];
  if (prefs.eventReminders) {
    for (final e in events) {
      final until = e.scheduledAt.difference(now);
      if (e.importance == 'high' && !until.isNegative && until <= eventWindow) {
        out.add(EventSoonNotice(e, until.inMinutes));
      }
    }
  }
  if (prefs.paperExits) {
    for (final p in positions) {
      final at = p.exitAt;
      if (!p.open && at != null && now.difference(at) <= closedWindow) {
        out.add(PaperClosedNotice(p));
      }
    }
  }
  return out;
}

/// The notices to show now, from the calendar and the first paper account's positions.
final forexNoticesProvider = FutureProvider<List<ForexNotice>>((ref) async {
  final prefs = await ref.watch(forexAlertPrefsProvider.future);
  final events = await ref.watch(forexCalendarProvider.future);
  final accounts = await ref.watch(paperAccountsProvider.future);
  final positions = accounts.isEmpty
      ? const <PaperPosition>[]
      : await ref.watch(paperPositionsProvider(accounts.first.id).future);
  return noticesFor(
    prefs: prefs,
    events: events,
    positions: positions,
    now: DateTime.now().toUtc(),
  );
});

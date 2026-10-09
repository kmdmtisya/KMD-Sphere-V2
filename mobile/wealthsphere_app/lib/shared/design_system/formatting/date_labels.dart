import 'package:flutter/foundation.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';

/// Coarse units for "as of 2 hours ago" labels.
enum AgeUnit { justNow, minutes, hours, days, older }

/// How long ago something happened, as data. The words ("2 hours ago") are produced by the
/// localised UI layer so that the primitives stay language-neutral.
@immutable
class RelativeAge {
  const RelativeAge(this.unit, this.value, {this.isFuture = false});

  /// Classifies the distance between [asOf] and [now].
  ///
  /// < 1 minute -> [AgeUnit.justNow]; < 1 hour -> minutes; < 1 day -> hours; < 7 days -> days;
  /// otherwise [AgeUnit.older] (the UI then shows an absolute date). A timestamp more than a
  /// minute in the future (clock skew or bad data) is flagged with [isFuture].
  factory RelativeAge.between(DateTime asOf, {required DateTime now}) {
    final difference = now.toUtc().difference(asOf.toUtc());
    final future = difference.isNegative;
    final span = future ? -difference : difference;
    if (span < const Duration(minutes: 1)) {
      return const RelativeAge(AgeUnit.justNow, 0);
    }
    if (span < const Duration(hours: 1)) {
      return RelativeAge(AgeUnit.minutes, span.inMinutes, isFuture: future);
    }
    if (span < const Duration(days: 1)) {
      return RelativeAge(AgeUnit.hours, span.inHours, isFuture: future);
    }
    if (span < const Duration(days: 7)) {
      return RelativeAge(AgeUnit.days, span.inDays, isFuture: future);
    }
    return RelativeAge(AgeUnit.older, span.inDays, isFuture: future);
  }

  final AgeUnit unit;
  final int value;
  final bool isFuture;

  @override
  bool operator ==(Object other) =>
      other is RelativeAge &&
      other.unit == unit &&
      other.value == value &&
      other.isFuture == isFuture;

  @override
  int get hashCode => Object.hash(unit, value, isFuture);

  @override
  String toString() =>
      'RelativeAge($unit, $value${isFuture ? ', future' : ''})';
}

/// Loads the date symbols for [locales]. Call once at start-up (`main`) before any date is shown;
/// until then [DateLabels] falls back to plain ISO dates instead of throwing.
Future<void> initializeDateLabels([
  Iterable<String> locales = const <String>['en'],
]) async {
  await Future.wait(locales.map(initializeDateFormatting));
}

/// Absolute date and time labels in the user's locale and local time zone.
///
/// Never throws: if the locale's date data is not loaded, English is tried, and if that is not
/// loaded either (before [initializeDateLabels]) a plain ISO date is returned.
abstract final class DateLabels {
  /// `Mar 12, 2024` (en).
  static String date(DateTime value, {String locale = 'en'}) => _safe(
    locale,
    (l) => DateFormat.yMMMd(l).format(value),
    () => _iso(value),
  );

  /// `Mar 12, 2024, 2:05 PM` (en).
  static String dateTime(DateTime value, {String locale = 'en'}) => _safe(
    locale,
    (l) => DateFormat.yMMMd(l).add_jm().format(value),
    () => '${_iso(value)} ${_two(value.hour)}:${_two(value.minute)}',
  );

  /// `Mar 12` (en): compact axis label.
  static String dayMonth(DateTime value, {String locale = 'en'}) => _safe(
    locale,
    (l) => DateFormat.MMMd(l).format(value),
    () => '${_two(value.month)}-${_two(value.day)}',
  );

  static String _safe(
    String locale,
    String Function(String) build,
    String Function() plain,
  ) {
    for (final candidate in <String>[locale, 'en']) {
      try {
        return build(candidate);
      } on Object {
        continue;
      }
    }
    return plain();
  }

  static String _two(int n) => n.toString().padLeft(2, '0');
  static String _iso(DateTime v) =>
      '${v.year.toString().padLeft(4, '0')}-${_two(v.month)}-${_two(v.day)}';
}

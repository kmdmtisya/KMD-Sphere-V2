import 'package:decimal/decimal.dart';

import '../../shared/design_system/formatting/money.dart';

/// Strict readers for API-shaped JSON (`snake_case` fields, money as `{amount, currency}` with the
/// amount as a **string**, rates and quantities as strings).
///
/// Every reader throws [FormatException] with the field path in the message, so a malformed or
/// tampered payload fails loudly instead of showing wrong numbers. JSON numbers are rejected for
/// money, rates and percentages because they cannot carry exact decimal values.
class JsonReader {
  JsonReader(Object? json, [this.path = r'$'])
    : _map = json is Map<String, dynamic>
          ? json
          : throw FormatException(
              '$path must be a JSON object, got ${json.runtimeType}',
            );

  final Map<String, dynamic> _map;
  final String path;

  String _at(String key) => '$path.$key';

  Object? _raw(String key) {
    if (!_map.containsKey(key)) {
      throw FormatException('${_at(key)} is missing');
    }
    return _map[key];
  }

  bool has(String key) => _map.containsKey(key) && _map[key] != null;

  String string(String key) {
    final v = _raw(key);
    if (v is! String) {
      throw FormatException(
        '${_at(key)} must be a string, got ${v.runtimeType}',
      );
    }
    return v;
  }

  String? stringOrNull(String key) => has(key) ? string(key) : null;

  int integer(String key) {
    final v = _raw(key);
    if (v is! int) {
      throw FormatException(
        '${_at(key)} must be an integer, got ${v.runtimeType}',
      );
    }
    return v;
  }

  bool boolean(String key) {
    final v = _raw(key);
    if (v is! bool) {
      throw FormatException(
        '${_at(key)} must be a boolean, got ${v.runtimeType}',
      );
    }
    return v;
  }

  /// A decimal carried as a string such as `"12.50"` (a percentage, rate or quantity).
  Decimal decimal(String key) {
    final text = string(key);
    if (!_decimalPattern.hasMatch(text)) {
      throw FormatException(
        '${_at(key)} is not a plain decimal string: "$text"',
      );
    }
    return Decimal.parse(text);
  }

  Money money(String key) {
    final v = _raw(key);
    try {
      return Money.fromJson(v);
    } on FormatException catch (e) {
      throw FormatException('${_at(key)}: ${e.message}');
    }
  }

  /// ISO 8601 timestamp with an explicit zone (`Z` or an offset), returned in UTC.
  DateTime timestamp(String key) {
    final text = string(key);
    if (!_zonePattern.hasMatch(text)) {
      throw FormatException(
        '${_at(key)} must be an ISO 8601 timestamp with a time zone: "$text"',
      );
    }
    final parsed = DateTime.tryParse(text);
    if (parsed == null || !_calendarInRange(text)) {
      throw FormatException('${_at(key)} is not a valid timestamp: "$text"');
    }
    return parsed.toUtc();
  }

  /// A calendar date (`YYYY-MM-DD`) as a UTC midnight.
  DateTime date(String key) {
    final text = string(key);
    if (!_datePattern.hasMatch(text)) {
      throw FormatException('${_at(key)} must be YYYY-MM-DD: "$text"');
    }
    final parsed = DateTime.tryParse('${text}T00:00:00Z');
    if (parsed == null || !_calendarInRange(text)) {
      throw FormatException('${_at(key)} is not a valid date: "$text"');
    }
    return parsed;
  }

  JsonReader object(String key) => JsonReader(_raw(key), _at(key));

  List<T> list<T>(String key, T Function(JsonReader item) read) {
    final v = _raw(key);
    if (v is! List) {
      throw FormatException('${_at(key)} must be a list, got ${v.runtimeType}');
    }
    return List.unmodifiable([
      for (var i = 0; i < v.length; i++)
        read(JsonReader(v[i], '${_at(key)}[$i]')),
    ]);
  }

  List<String> strings(String key) {
    final v = _raw(key);
    if (v is! List) {
      throw FormatException('${_at(key)} must be a list, got ${v.runtimeType}');
    }
    return List.unmodifiable([
      for (var i = 0; i < v.length; i++)
        v[i] is String
            ? v[i] as String
            : throw FormatException(
                '${_at(key)}[$i] must be a string, got ${v[i].runtimeType}',
              ),
    ]);
  }

  /// Reads an object whose keys are arbitrary ids and whose values are read by [read].
  Map<String, T> mapOf<T>(String key, T Function(JsonReader item) read) {
    final v = _raw(key);
    if (v is! Map<String, dynamic>) {
      throw FormatException(
        '${_at(key)} must be an object, got ${v.runtimeType}',
      );
    }
    return Map.unmodifiable({
      for (final e in v.entries)
        e.key: read(JsonReader(e.value, '${_at(key)}.${e.key}')),
    });
  }

  /// `DateTime.tryParse` rolls impossible values over (month 13 becomes January of the next
  /// year), so ranges are checked on the text itself.
  static bool _calendarInRange(String text) {
    final m = RegExp(r'^(\d{4})-(\d\d)-(\d\d)(?:T(\d\d):(\d\d)(?::(\d\d))?)?')
        .firstMatch(text);
    if (m == null) return false;
    final year = int.parse(m[1]!);
    final month = int.parse(m[2]!);
    final day = int.parse(m[3]!);
    if (month < 1 || month > 12) return false;
    final lastDay = DateTime.utc(year, month + 1, 0).day;
    if (day < 1 || day > lastDay) return false;
    final hour = int.tryParse(m[4] ?? '0')!;
    final minute = int.tryParse(m[5] ?? '0')!;
    final second = int.tryParse(m[6] ?? '0')!;
    return hour < 24 && minute < 60 && second < 60;
  }

  static final RegExp _decimalPattern = RegExp(r'^-?\d+(\.\d+)?$');
  static final RegExp _zonePattern = RegExp(
    r'^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?(Z|[+-]\d\d:\d\d)$',
  );
  static final RegExp _datePattern = RegExp(r'^\d{4}-\d\d-\d\d$');
}

/// Builds `{amount, currency}` JSON for a [Money] (string amount).
Map<String, String> moneyJson(Money m) => m.toJson();

/// ISO 8601 UTC text for a timestamp.
String timestampJson(DateTime t) =>
    t.toUtc().toIso8601String().replaceFirst('.000Z', 'Z');

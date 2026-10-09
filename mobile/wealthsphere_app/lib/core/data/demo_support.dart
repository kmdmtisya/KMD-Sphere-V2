import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Where data comes from. Only `demo` exists until the backend is wired in P09.
enum DataSourceMode { demo }

class DataSourceModeNotifier extends Notifier<DataSourceMode> {
  @override
  DataSourceMode build() => DataSourceMode.demo;
}

final dataSourceModeProvider =
    NotifierProvider<DataSourceModeNotifier, DataSourceMode>(
      DataSourceModeNotifier.new,
    );

/// A repository call failed. Raised by demo repositories when failure injection is on, and by the
/// real repositories later, so error and retry states look the same in both modes.
class DataLoadException implements Exception {
  const DataLoadException(this.message);

  final String message;

  @override
  String toString() => 'DataLoadException: $message';
}

/// A demo asset is missing, is not marked `"demo": true`, or has the wrong shape.
class DemoDataException implements Exception {
  const DemoDataException(this.message);

  final String message;

  @override
  String toString() => 'DemoDataException: $message';
}

/// How demo repositories behave: how long they take, and whether they fail.
///
/// This exists so loading, error and retry states can be exercised in the gallery and in tests.
@immutable
class DemoBehavior {
  const DemoBehavior({
    this.latency = const Duration(milliseconds: 600),
    this.streamInterval = const Duration(milliseconds: 250),
    this.failAlways = false,
    this.failNextCalls = 0,
  });

  /// No waiting at all, for tests that do not exercise timing.
  static const DemoBehavior instant = DemoBehavior(
    latency: Duration.zero,
    streamInterval: Duration.zero,
  );

  /// Delay before a repository call completes.
  final Duration latency;

  /// Delay between streamed chat events.
  final Duration streamInterval;

  /// Every call fails while this is true.
  final bool failAlways;

  /// The next N calls fail, then calls succeed again (to test retry).
  final int failNextCalls;

  bool get willFail => failAlways || failNextCalls > 0;

  DemoBehavior copyWith({
    Duration? latency,
    Duration? streamInterval,
    bool? failAlways,
    int? failNextCalls,
  }) => DemoBehavior(
    latency: latency ?? this.latency,
    streamInterval: streamInterval ?? this.streamInterval,
    failAlways: failAlways ?? this.failAlways,
    failNextCalls: failNextCalls ?? this.failNextCalls,
  );
}

class DemoBehaviorNotifier extends Notifier<DemoBehavior> {
  @override
  DemoBehavior build() => const DemoBehavior();

  void set(DemoBehavior behavior) => state = behavior;

  /// Called once per repository call: applies the latency and throws if failure is injected.
  /// A pending "fail the next N calls" count is consumed here.
  Future<void> gate() async {
    final current = state;
    if (current.latency > Duration.zero) {
      await Future<void>.delayed(current.latency);
    }
    if (current.failNextCalls > 0) {
      state = current.copyWith(failNextCalls: current.failNextCalls - 1);
      throw const DataLoadException('Demo failure injected');
    }
    if (current.failAlways) {
      throw const DataLoadException('Demo failure injected');
    }
  }
}

final demoBehaviorProvider =
    NotifierProvider<DemoBehaviorNotifier, DemoBehavior>(
      DemoBehaviorNotifier.new,
    );

/// Loads and caches `assets/demo/*.json`. Refuses any file that is not marked `"demo": true`, so
/// real data can never be mistaken for a fixture (and the reverse).
class DemoAssets {
  DemoAssets(this._bundle, {this.folder = 'assets/demo'});

  final AssetBundle _bundle;
  final String folder;
  final Map<String, Map<String, dynamic>> _cache = {};

  Future<Map<String, dynamic>> load(String file) async {
    final cached = _cache[file];
    if (cached != null) return cached;
    final String text;
    try {
      text = await _bundle.loadString('$folder/$file');
    } catch (e) {
      throw DemoDataException('Cannot load $folder/$file: $e');
    }
    final Object? decoded;
    try {
      decoded = jsonDecode(text);
    } on FormatException catch (e) {
      throw DemoDataException('$file is not valid JSON: ${e.message}');
    }
    if (decoded is! Map<String, dynamic> || decoded['demo'] != true) {
      throw DemoDataException('$file must be a JSON object with "demo": true');
    }
    return _cache[file] = decoded;
  }
}

final demoAssetsProvider = Provider<DemoAssets>(
  (ref) => DemoAssets(rootBundle),
);

import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:wealthsphere_app/core/data/demo_support.dart';
import 'package:wealthsphere_app/core/preferences/preferences_store.dart';

/// Reads the real `assets/demo` files **synchronously**, so widget tests (which run in fake
/// async) never wait on real file I/O and `pumpAndSettle` can finish.
class SyncFileBundle extends CachingAssetBundle {
  @override
  Future<ByteData> load(String key) {
    final bytes = File(key).readAsBytesSync();
    return Future.value(ByteData.sublistView(bytes));
  }

  /// Decodes on this isolate. The base class hands anything over 50 KB to a background isolate
  /// (`compute`), which never finishes under fake async and would hang `pumpAndSettle`.
  @override
  Future<String> loadString(String key, {bool cache = true}) =>
      Future.value(utf8.decode(File(key).readAsBytesSync()));
}

class _FixedBehavior extends DemoBehaviorNotifier {
  _FixedBehavior(this._initial);

  final DemoBehavior _initial;

  @override
  DemoBehavior build() => _initial;
}

/// Provider overrides for widget tests: instant demo repositories (or [behavior]) and an
/// in-memory preferences store that can be shared between two pumps to simulate a restart.
List<Override> demoOverrides({
  DemoBehavior behavior = DemoBehavior.instant,
  PreferencesStore? store,
  List<Override> extra = const [],
}) => [
  demoBehaviorProvider.overrideWith(() => _FixedBehavior(behavior)),
  demoAssetsProvider.overrideWithValue(DemoAssets(SyncFileBundle())),
  if (store != null) preferencesStoreProvider.overrideWithValue(store),
  ...extra,
];

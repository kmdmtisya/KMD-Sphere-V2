import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../domain/more_models.dart';

/// The wealth views behind the More tab. Read-only.
abstract interface class MoreRepository {
  Future<NetWorthDetail> netWorth();
  Future<IncomeDetail> income();
}

/// Reads `assets/demo/more.json`.
class DemoMoreRepository implements MoreRepository {
  DemoMoreRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;

  Future<JsonReader> _doc() async {
    await _gate();
    return JsonReader(await _assets.load('more.json'));
  }

  @override
  Future<NetWorthDetail> netWorth() async =>
      NetWorthDetail.fromJson((await _doc()).object('net_worth'));

  @override
  Future<IncomeDetail> income() async =>
      IncomeDetail.fromJson((await _doc()).object('income'));
}

final moreRepositoryProvider = Provider<MoreRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoMoreRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
    case DataSourceMode.live:
      liveNotWired('MoreRepository');
  }
});

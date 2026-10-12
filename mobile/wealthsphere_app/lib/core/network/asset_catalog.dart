import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api_client.dart';
import 'live_repository.dart';

/// The descriptive part of an asset (`GET /api/v1/assets/{id}`): what the ledger and the
/// investment screen show next to an asset id. No figures.
@immutable
class AssetInfo {
  const AssetInfo({
    required this.id,
    required this.symbol,
    required this.name,
    required this.assetClass,
    required this.assetClassName,
    required this.currency,
  });

  final String id;

  /// Null for user-defined assets without a ticker.
  final String? symbol;
  final String name;
  final String assetClass;
  final String assetClassName;
  final String currency;
}

/// Reads assets by id, once each per session (an asset's name and ticker do not change while the
/// app runs). A failed read is not kept, so the next call tries again.
class AssetCatalog extends LiveRepository {
  AssetCatalog(super.dio);

  final Map<String, Future<AssetInfo>> _byId = {};

  Future<AssetInfo> asset(String id) => _byId[id] ??= _load(id);

  Future<Map<String, AssetInfo>> assets(Iterable<String> ids) async {
    final unique = ids.toSet().toList();
    final found = await Future.wait(unique.map(asset));
    return {for (var i = 0; i < unique.length; i++) unique[i]: found[i]};
  }

  Future<AssetInfo> _load(String id) async {
    try {
      return await getObject(
        '/api/v1/assets/$id',
        (r) => AssetInfo(
          id: r.string('id'),
          symbol: r.stringOrNull('symbol'),
          name: r.string('name'),
          assetClass: r.string('asset_class'),
          assetClassName: r.string('asset_class_name'),
          currency: r.string('currency'),
        ),
      );
    } catch (_) {
      final _ = _byId.remove(id);
      rethrow;
    }
  }
}

final assetCatalogProvider = Provider<AssetCatalog>(
  (ref) => AssetCatalog(ref.watch(apiClientProvider)),
);

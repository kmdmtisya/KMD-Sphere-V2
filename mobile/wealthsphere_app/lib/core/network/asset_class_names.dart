import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api_client.dart';
import 'live_repository.dart';

/// Display names of the asset classes (`GET /api/v1/asset-classes`), keyed by class code.
///
/// The API reports classes by code (`stock`, `real_estate`); this is the server's own name for
/// each. Loaded once and kept; a code the server does not list is shown as received.
class AssetClassNames extends LiveRepository {
  AssetClassNames(super.dio);

  Future<Map<String, String>>? _names;

  Future<Map<String, String>> names() => _names ??= _load();

  Future<Map<String, String>> _load() async {
    try {
      final items = await getList(
        '/api/v1/asset-classes',
        (r) => (code: r.string('code'), name: r.string('name')),
      );
      return {for (final i in items) i.code: i.name};
    } catch (_) {
      _names = null; // let the next call try again
      rethrow;
    }
  }

  /// The name for [code], or the code itself when unknown.
  Future<String> nameOf(String code) async => (await names())[code] ?? code;
}

final assetClassNamesProvider = Provider<AssetClassNames>(
  (ref) => AssetClassNames(ref.watch(apiClientProvider)),
);

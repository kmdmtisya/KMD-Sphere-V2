import 'package:decimal/decimal.dart';

import '../../../core/data/json_reader.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/asset_catalog.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/design_system/components/transaction_tile.dart';
import '../../../shared/domain/wealth_models.dart';
import '../application/transaction_draft.dart';
import '../domain/ledger_entry.dart';
import 'transaction_repository.dart';

/// The ledger from the API. It stays append-only: [add] posts a new entry and [reverse] posts a
/// linked reversal; nothing is edited or deleted. The server works out every total (a trade's
/// gross amount, holdings, summaries); the app sends what the person typed.
class LiveTransactionRepository extends LiveRepository
    implements TransactionRepository {
  LiveTransactionRepository(super.dio, this._assets, this._portfolioIds);

  final AssetCatalog _assets;

  /// The ids of the user's portfolios (for the all-portfolios ledger).
  final Future<List<String>> Function() _portfolioIds;

  /// Which portfolio each entry seen so far belongs to: the single-entry routes need it.
  final Map<String, String> _portfolioOf = {};

  static const _pageSize = 100;

  @override
  Future<List<LedgerEntry>> entries(String portfolioId) async {
    final ids = portfolioId == PortfolioRef.consolidatedId
        ? await _portfolioIds()
        : [portfolioId];
    final pages = await Future.wait(ids.map(_allOf));
    final rows = [for (final p in pages) ...p];
    final assets = await _assets.assets([
      for (final r in rows)
        if (r.has('asset_id')) r.string('asset_id'),
    ]);
    return [for (final r in rows) _entry(r, assets)];
  }

  /// Every entry of one portfolio, following the cursor to the end.
  Future<List<JsonReader>> _allOf(String portfolioId) async {
    final rows = <JsonReader>[];
    String? cursor;
    do {
      final page = await getObject(
        '/api/v1/portfolios/$portfolioId/transactions',
        (r) => r,
        query: {'limit': _pageSize, 'cursor': ?cursor},
      );
      rows.addAll(page.list('items', (i) => i));
      cursor = page.stringOrNull('next_cursor');
    } while (cursor != null);
    return rows;
  }

  @override
  Future<LedgerEntry> entry(String id) async {
    var portfolioId = _portfolioOf[id];
    if (portfolioId == null) {
      await entries(PortfolioRef.consolidatedId);
      portfolioId = _portfolioOf[id];
      if (portfolioId == null) {
        throw const LedgerRuleException(LedgerRule.notFound);
      }
    }
    final row = await _ruled(
      getObject('/api/v1/portfolios/$portfolioId/transactions/$id', (r) => r),
    );
    return _entry(row, await _assetsOf(row));
  }

  @override
  Future<LedgerEntry> add(NewTransaction t) async {
    final row = await send(
      'POST',
      '/api/v1/portfolios/${t.portfolioId}/transactions',
      (r) => r,
      body: toApi(t),
      idempotencyKey: t.idempotencyKey,
    );
    return _entry(row, await _assetsOf(row));
  }

  @override
  Future<LedgerEntry> reverse(String id, {String? note}) async {
    final original = await entry(id);
    if (original.isReversal) {
      throw const LedgerRuleException(LedgerRule.isReversal);
    }
    if (original.isReversed) {
      throw const LedgerRuleException(LedgerRule.alreadyReversed);
    }
    final row = await _ruled(
      send(
        'POST',
        '/api/v1/portfolios/${original.portfolioId}/transactions/$id/reversal',
        (r) => r,
        body: {'note': note},
      ),
    );
    return _entry(row, await _assetsOf(row));
  }

  /// The request body for [t]: amounts as strings in the transaction currency. A trade sends
  /// quantity and unit price; the server derives its gross amount.
  static Map<String, Object?> toApi(NewTransaction t) {
    Map<String, String>? money(Object? amount) =>
        amount == null ? null : {'amount': '$amount', 'currency': t.currency};
    final d = t.date;
    return {
      'transaction_type': t.kind.apiName,
      'trade_date':
          '${d.year.toString().padLeft(4, '0')}-'
          '${d.month.toString().padLeft(2, '0')}-'
          '${d.day.toString().padLeft(2, '0')}',
      'currency': t.currency,
      'asset_id': ?t.assetId,
      'quantity': ?t.quantity?.toString(),
      'unit_price': ?money(t.unitPrice),
      'gross_amount': ?money(t.amount),
      'fees': ?money(t.fee),
      'note': ?t.note,
    };
  }

  Future<Map<String, AssetInfo>> _assetsOf(JsonReader row) =>
      _assets.assets([if (row.has('asset_id')) row.string('asset_id')]);

  /// A refused correction says why, in the ledger's own terms.
  Future<T> _ruled<T>(Future<T> call) async {
    try {
      return await call;
    } on ApiException catch (e) {
      throw switch (e.kind) {
        ApiErrorKind.notFound => const LedgerRuleException(LedgerRule.notFound),
        _ when e.status == 409 => const LedgerRuleException(
          LedgerRule.alreadyReversed,
        ),
        _ => e,
      };
    }
  }

  LedgerEntry _entry(JsonReader r, Map<String, AssetInfo> assets) {
    final id = r.string('id');
    final portfolioId = r.string('portfolio_id');
    _portfolioOf[id] = portfolioId;
    final day = r.date('trade_date');
    final asset = r.has('asset_id') ? assets[r.string('asset_id')] : null;
    final fees = r.money('fees');
    return LedgerEntry(
      id: id,
      portfolioId: portfolioId,
      kind: TransactionKind.parse(r.string('transaction_type')),
      tradeDate: DateTime(day.year, day.month, day.day),
      gross: r.money('gross_amount'),
      source: r.string('source'),
      createdAt: r.timestamp('created_at'),
      assetId: asset?.id,
      assetSymbol: asset?.symbol,
      assetName: asset?.name,
      quantity: r.has('quantity') ? r.decimal('quantity') : null,
      unitPrice: r.has('unit_price') ? r.money('unit_price') : null,
      // The API always sends fees; zero means there were none, as in the DEMO data.
      fees: fees.amount == Decimal.zero ? null : fees,
      note: r.stringOrNull('note'),
      reversesId: r.stringOrNull('reverses_transaction_id'),
      reversedById: r.stringOrNull('reversed_by_transaction_id'),
    );
  }
}

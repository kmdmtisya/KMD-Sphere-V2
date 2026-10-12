import '../../../core/data/json_reader.dart';
import '../../../core/network/asset_class_names.dart';
import '../../../core/network/live_repository.dart';
import '../../../shared/design_system/components/transaction_tile.dart';
import '../../../shared/domain/wealth_models.dart';
import '../../transactions/domain/ledger_entry.dart';
import '../domain/more_models.dart';
import 'more_repository.dart';

/// Net worth and income from the API. The totals, shares and conversions are the server's; the
/// app arranges them into the screens' sections and adds nothing up.
class LiveMoreRepository extends LiveRepository implements MoreRepository {
  LiveMoreRepository(super.dio, this._classes, this._portfolios, this._ledger);

  final AssetClassNames _classes;
  final Future<List<PortfolioRef>> Function() _portfolios;

  /// Every ledger entry (all portfolios), for the list of recent income payments.
  final Future<List<LedgerEntry>> Function() _ledger;

  /// How many recent payments the Income screen lists.
  static const recentCount = 10;

  static const _incomeKinds = {
    TransactionKind.dividend,
    TransactionKind.interest,
    TransactionKind.coupon,
    TransactionKind.rent,
    TransactionKind.distribution,
  };

  @override
  Future<NetWorthDetail> netWorth() async {
    final names = await _classes.names();
    return getObject('/api/v1/net-worth', (r) {
      final liabilities = r.list('liability_lines', (l) => l);
      return NetWorthDetail(
        netWorth: r.money('net_worth'),
        assets: NetWorthSection(
          total: r.money('assets'),
          items: r.list('assets_by_class', (a) {
            final code = a.string('asset_class');
            return NetWorthItem(
              label: names[code] ?? code,
              kind: code,
              value: a.money('value'),
              sharePercent: a.has('share_percent')
                  ? a.decimal('share_percent')
                  : null,
            );
          }),
        ),
        liabilities: NetWorthSection(
          total: r.money('liabilities'),
          items: [
            for (final l in liabilities)
              NetWorthItem(
                label: l.string('name'),
                kind: l.string('liability_type'),
                // The converted value; when it could not be converted, the balance in its own
                // currency (the total then says it is incomplete).
                value: l.has('value') ? l.money('value') : l.money('balance'),
              ),
          ],
        ),
        asOf: r.timestamp('as_of'),
        complete: r.object('freshness').boolean('complete'),
      );
    });
  }

  @override
  Future<IncomeDetail> income() async {
    final results = await Future.wait([
      getObject('/api/v1/income/summary', (r) => r),
      _portfolios(),
      _ledger(),
    ]);
    final summary = results[0] as JsonReader;
    final portfolios = {
      for (final p in results[1] as List<PortfolioRef>) p.id: p.name,
    };
    final ledger = results[2] as List<LedgerEntry>;
    final payments = [
      for (final e in ledger)
        if (_incomeKinds.contains(e.kind) && e.canCorrect) e,
    ]..sort((a, b) => b.tradeDate.compareTo(a.tradeDate));
    return IncomeDetail(
      monthly: summary.money('monthly'),
      yearly: summary.money('yearly'),
      bySource: [
        for (final line in summary.list('portfolios', (l) => l))
          IncomeSource(
            label:
                portfolios[line.string('portfolio_id')] ??
                line.string('portfolio_id'),
            yearly: line.money('yearly'),
            sharePercent: null,
          ),
      ],
      recent: [
        for (final e in payments.take(recentCount))
          IncomePayment(
            date: e.tradeDate,
            kind: '',
            transactionKind: e.kind,
            assetName: e.assetName ?? '',
            amount: e.gross,
          ),
      ],
      asOf: summary.timestamp('as_of'),
      complete: summary.boolean('complete'),
    );
  }
}

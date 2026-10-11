import '../../../l10n/generated/app_localizations.dart';
import '../application/ledger_view.dart';
import '../application/transaction_draft.dart';

String txFilterLabel(AppLocalizations l10n, TxFilter filter) =>
    switch (filter) {
      TxFilter.all => l10n.ledgerFilterAll,
      TxFilter.trades => l10n.ledgerFilterTrades,
      TxFilter.cash => l10n.ledgerFilterCash,
      TxFilter.income => l10n.ledgerFilterIncome,
      TxFilter.costs => l10n.ledgerFilterCosts,
      TxFilter.other => l10n.ledgerFilterOther,
    };

String txFieldLabel(AppLocalizations l10n, TxField field) => switch (field) {
  TxField.kind => l10n.addTxType,
  TxField.portfolio => l10n.addTxPortfolio,
  TxField.asset => l10n.addTxAsset,
  TxField.date => l10n.addTxDate,
  TxField.quantity => l10n.addTxQuantity,
  TxField.unitPrice => l10n.addTxUnitPrice,
  TxField.amount => l10n.addTxAmount,
  TxField.fee => l10n.ledgerFieldFee,
};

/// The human-readable sentence for a problem with [field].
String txIssueText(AppLocalizations l10n, TxField field, TxIssue issue) =>
    switch (issue.error) {
      TxFieldError.required => l10n.txErrRequired(txFieldLabel(l10n, field)),
      TxFieldError.notANumber => l10n.txErrNotANumber,
      TxFieldError.notPositive => l10n.txErrNotPositive,
      TxFieldError.negative => l10n.txErrNegative,
      TxFieldError.tooManyDecimals => l10n.txErrTooManyDecimals(
        issue.places ?? 0,
      ),
      TxFieldError.tooLarge => l10n.txErrTooLarge,
      TxFieldError.futureDate => l10n.txErrFutureDate,
      TxFieldError.tooOld => l10n.txErrTooOld,
    };

String ledgerSourceLabel(AppLocalizations l10n, String source) =>
    switch (source) {
      'manual' => l10n.ledgerSourceManual,
      'import' => l10n.ledgerSourceImport,
      _ => l10n.ledgerSourceSystem,
    };

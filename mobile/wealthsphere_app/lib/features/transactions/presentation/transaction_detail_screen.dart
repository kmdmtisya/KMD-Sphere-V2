import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/ledger_view.dart';
import '../data/transaction_repository.dart';
import '../domain/ledger_entry.dart';
import 'ledger_entry_tile.dart';
import 'ledger_labels.dart';

/// One ledger entry with its history. A correction never edits the entry: it appends a reversal
/// that links to it, and both are shown here with a way to open the other.
class TransactionDetailScreen extends ConsumerStatefulWidget {
  const TransactionDetailScreen({
    required this.entryId,
    this.onOpenEntry,
    this.onAddCorrected,
    super.key,
  });

  final String entryId;

  /// Opens another entry (the reversal, or the entry a reversal cancels).
  final void Function(String id)? onOpenEntry;

  /// Opens the add flow prefilled from this (reversed) entry.
  final void Function(LedgerEntry entry)? onAddCorrected;

  @override
  ConsumerState<TransactionDetailScreen> createState() =>
      _TransactionDetailScreenState();
}

class _TransactionDetailScreenState
    extends ConsumerState<TransactionDetailScreen> {
  bool _working = false;
  String? _message;
  bool _messageIsError = false;

  Future<void> _correct(LedgerEntry entry) async {
    final l10n = AppLocalizations.of(context);
    final note = await showDialog<String>(
      context: context,
      builder: (_) => const _ReverseDialog(),
    );
    if (note == null || !mounted) return;
    setState(() {
      _working = true;
      _message = null;
    });
    String? text;
    var isError = false;
    try {
      await ref
          .read(transactionRepositoryProvider)
          .reverse(entry.id, note: note.isEmpty ? null : note);
      refreshLedger(ref);
      text = l10n.ledgerReversalDone;
    } on LedgerRuleException catch (e) {
      isError = true;
      text = switch (e.rule) {
        LedgerRule.notFound => l10n.ledgerErrNotFound,
        LedgerRule.alreadyReversed => l10n.ledgerErrAlreadyReversed,
        LedgerRule.isReversal => l10n.ledgerErrIsReversal,
      };
    } on Object {
      isError = true;
      text = l10n.ledgerReverseFailed;
    }
    if (!mounted) return;
    setState(() {
      _working = false;
      _message = text;
      _messageIsError = isError;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final entry = ref.watch(ledgerEntryProvider(widget.entryId));
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.ledgerDetailTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: AsyncValueView<LedgerEntry>(
        value: entry,
        onRetry: () => ref.invalidate(ledgerEntryProvider(widget.entryId)),
        data: (e) => ListView(
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          children: [
            if (_message != null) ...[
              StatusBanner(
                icon: _messageIsError
                    ? Icons.error_outline_rounded
                    : Icons.check_circle_outline_rounded,
                message: _message!,
              ),
              const SizedBox(height: AppSpacing.m),
            ],
            WealthCard(
              padding: EdgeInsets.zero,
              child: LedgerEntryTile(entry: e),
            ),
            const SizedBox(height: AppSpacing.m),
            _Facts(entry: e),
            const SizedBox(height: AppSpacing.m),
            _History(entry: e, onOpen: widget.onOpenEntry),
            const SizedBox(height: AppSpacing.m),
            if (e.canCorrect)
              FilledButton.tonalIcon(
                onPressed: _working ? null : () => _correct(e),
                icon: _working
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.undo_rounded),
                label: Text(l10n.ledgerCorrect),
              ),
            if (e.isReversed && widget.onAddCorrected != null)
              FilledButton.icon(
                onPressed: () => widget.onAddCorrected!(e),
                icon: const Icon(Icons.add_rounded),
                label: Text(l10n.ledgerAddCorrected),
              ),
            const SizedBox(height: AppSpacing.m),
            Text(
              l10n.ledgerAppendOnlyNote,
              style: context.wealthText.caption.copyWith(
                color: context.wealthColors.textMuted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Facts extends StatelessWidget {
  const _Facts({required this.entry});

  final LedgerEntry entry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final money = context.moneyFormatter;
    final locale = context.formatLocale;
    final rows = <(String, String)>[
      (l10n.ledgerFieldType, TransactionTile.label(l10n, entry.kind)),
      if (entry.assetName != null)
        (
          l10n.ledgerFieldAsset,
          '${entry.assetName} (${entry.assetSymbol ?? ''})',
        ),
      (l10n.ledgerFieldDate, DateLabels.date(entry.tradeDate, locale: locale)),
      if (entry.quantity != null)
        (l10n.ledgerFieldQuantity, entry.quantity.toString()),
      if (entry.unitPrice != null)
        (l10n.ledgerFieldUnitPrice, money.format(entry.unitPrice!)),
      (l10n.ledgerFieldAmount, money.format(entry.gross)),
      if (entry.fees != null && entry.fees!.amount.sign != 0)
        (l10n.ledgerFieldFee, money.format(entry.fees!)),
      (l10n.ledgerFieldSource, ledgerSourceLabel(l10n, entry.source)),
      if (entry.note != null) (l10n.ledgerFieldNote, entry.note!),
      (
        l10n.ledgerFieldRecorded,
        DateLabels.dateTime(entry.createdAt.toLocal(), locale: locale),
      ),
    ];
    final text = context.wealthText;
    return WealthCard(
      child: Column(
        children: [
          for (final (label, value) in rows)
            MergeSemantics(
              child: Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  vertical: AppSpacing.xxs,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      flex: 2,
                      child: Text(
                        label,
                        style: text.caption.copyWith(
                          color: context.wealthColors.textMuted,
                        ),
                      ),
                    ),
                    Expanded(flex: 3, child: Text(value, style: text.body)),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _History extends StatelessWidget {
  const _History({required this.entry, required this.onOpen});

  final LedgerEntry entry;
  final void Function(String id)? onOpen;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final String message;
    final String? linkLabel;
    final String? linkId;
    if (entry.isReversal) {
      message = l10n.ledgerHistoryReverses;
      linkLabel = l10n.ledgerViewOriginal;
      linkId = entry.reversesId;
    } else if (entry.isReversed) {
      message = l10n.ledgerHistoryReversedBy;
      linkLabel = l10n.ledgerViewReversal;
      linkId = entry.reversedById;
    } else {
      message = l10n.ledgerHistoryLive;
      linkLabel = null;
      linkId = null;
    }
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            header: true,
            child: Text(l10n.ledgerHistoryTitle, style: text.title),
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                entry.isReversal || entry.isReversed
                    ? Icons.link_rounded
                    : Icons.check_circle_outline_rounded,
                size: 20,
              ),
              const SizedBox(width: AppSpacing.xs),
              Expanded(child: Text(message, style: text.body)),
            ],
          ),
          if (linkLabel != null && linkId != null && onOpen != null)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton(
                onPressed: () => onOpen!(linkId!),
                child: Text(linkLabel),
              ),
            ),
        ],
      ),
    );
  }
}

class _ReverseDialog extends StatefulWidget {
  const _ReverseDialog();

  @override
  State<_ReverseDialog> createState() => _ReverseDialogState();
}

class _ReverseDialogState extends State<_ReverseDialog> {
  final TextEditingController _note = TextEditingController();

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return AlertDialog(
      title: Text(l10n.ledgerCorrectTitle),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.ledgerCorrectBody),
            const SizedBox(height: AppSpacing.m),
            TextField(
              controller: _note,
              maxLength: 500,
              decoration: InputDecoration(
                labelText: l10n.ledgerCorrectNoteLabel,
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(l10n.ledgerCancel),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_note.text.trim()),
          child: Text(l10n.ledgerCorrectConfirm),
        ),
      ],
    );
  }
}

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../../shared/domain/wealth_models.dart';
import '../../portfolios/application/portfolio_providers.dart';
import '../application/ledger_view.dart';
import '../application/transaction_draft.dart';
import '../data/transaction_repository.dart';
import '../domain/ledger_entry.dart';
import 'ledger_entry_tile.dart';
import 'ledger_labels.dart';

enum _Step { form, review, done }

/// The add-transaction flow: a form with inline, human-readable validation, a review step, and a
/// confirmation. Nothing is calculated here: a trade shows the quantity and price the person
/// typed, and the server derives the total when the entry is saved.
///
/// [correctionOf] prefills the form from a reversed entry so a mistake can be re-entered.
class AddTransactionScreen extends ConsumerStatefulWidget {
  const AddTransactionScreen({
    this.correctionOf,
    this.onOpenEntry,
    this.onDone,
    super.key,
  });

  final LedgerEntry? correctionOf;

  /// Opens the saved entry.
  final void Function(String id)? onOpenEntry;

  /// Leaves the flow (back to the list).
  final VoidCallback? onDone;

  @override
  ConsumerState<AddTransactionScreen> createState() =>
      _AddTransactionScreenState();
}

class _AddTransactionScreenState extends ConsumerState<AddTransactionScreen> {
  final _quantity = TextEditingController();
  final _unitPrice = TextEditingController();
  final _amount = TextEditingController();
  final _fee = TextEditingController();
  final _note = TextEditingController();

  TransactionKind _kind = TransactionKind.buy;
  String? _portfolioId;
  String? _assetId;
  String? _assetSymbol;

  /// What the asset picker holds: the asset id (live) or the symbol (DEMO).
  String? get _assetKey => _assetId ?? _assetSymbol;

  /// Sent as `Idempotency-Key` with this entry, so retrying a failed save can never post it
  /// twice. A new one is made each time the form is reviewed.
  String? _saveKey;
  String? _assetName;
  DateTime? _date;

  _Step _step = _Step.form;
  bool _submitted = false;
  Map<TxField, TxIssue> _issues = const {};
  NewTransaction? _validated;
  bool _saving = false;
  bool _saveFailed = false;
  LedgerEntry? _saved;

  @override
  void initState() {
    super.initState();
    final c = widget.correctionOf;
    if (c != null) {
      _kind = addableKinds.contains(c.kind) ? c.kind : TransactionKind.buy;
      _portfolioId = c.portfolioId;
      _assetId = c.assetId;
      _assetSymbol = c.assetSymbol;
      _assetName = c.assetName;
      _date = c.tradeDate;
      _quantity.text = c.quantity?.toString() ?? '';
      _unitPrice.text = c.unitPrice?.amount.toString() ?? '';
      if (!_kind.isTrade) _amount.text = c.gross.amount.toString();
      final fee = c.fees;
      _fee.text = fee == null || fee.amount.sign == 0
          ? ''
          : fee.amount.toString();
      _note.text = c.note ?? '';
    } else {
      final selected = ref.read(selectedPortfolioIdProvider);
      if (selected != PortfolioRef.consolidatedId) _portfolioId = selected;
    }
  }

  @override
  void dispose() {
    for (final c in [_quantity, _unitPrice, _amount, _fee, _note]) {
      c.dispose();
    }
    super.dispose();
  }

  TransactionDraft _draft() => TransactionDraft(
    kind: _kind,
    portfolioId: _portfolioId,
    assetId: _assetId,
    assetSymbol: _assetSymbol,
    assetName: _assetName,
    date: _date,
    quantity: _quantity.text,
    unitPrice: _unitPrice.text,
    amount: _amount.text,
    fee: _fee.text,
    note: _note.text,
  );

  DraftValidation _check(List<PortfolioRef> portfolios) => validateDraft(
    _draft(),
    today: ref.read(todayProvider),
    currency: _currencyOf(portfolios),
  );

  String _currencyOf(List<PortfolioRef> portfolios) =>
      portfolios
          .where((p) => p.id == _portfolioId)
          .map((p) => p.baseCurrency)
          .firstOrNull ??
      portfolios.firstOrNull?.baseCurrency ??
      'USD';

  /// Once the person has tried to continue, problems update as they type.
  void _changed(List<PortfolioRef> portfolios, VoidCallback update) {
    setState(() {
      update();
      if (_submitted) _issues = _check(portfolios).issues;
    });
  }

  void _review(List<PortfolioRef> portfolios) {
    final result = _check(portfolios);
    setState(() {
      _submitted = true;
      _issues = result.issues;
      if (result.isValid) {
        _validated = result.value;
        _saveKey = newIdempotencyKey();
        _step = _Step.review;
        _saveFailed = false;
      }
    });
  }

  Future<void> _save() async {
    final value = _validated;
    if (value == null || _saving) return;
    setState(() {
      _saving = true;
      _saveFailed = false;
    });
    try {
      final entry = await ref
          .read(transactionRepositoryProvider)
          .add(value.withIdempotencyKey(_saveKey));
      refreshLedger(ref);
      if (!mounted) return;
      setState(() {
        _saving = false;
        _saved = entry;
        _step = _Step.done;
      });
    } on Object {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _saveFailed = true;
      });
    }
  }

  void _reset() {
    for (final c in [_quantity, _unitPrice, _amount, _fee, _note]) {
      c.clear();
    }
    setState(() {
      _kind = TransactionKind.buy;
      _assetId = null;
      _assetSymbol = null;
      _assetName = null;
      _date = null;
      _step = _Step.form;
      _submitted = false;
      _issues = const {};
      _validated = null;
      _saved = null;
    });
  }

  Future<void> _pickDate(List<PortfolioRef> portfolios) async {
    final today = ref.read(todayProvider);
    final last = DateTime(today.year, today.month, today.day);
    final picked = await showDatePicker(
      context: context,
      initialDate: _date != null && !_date!.isAfter(last) ? _date! : last,
      firstDate: earliestTradeDate,
      lastDate: last,
    );
    if (picked != null && mounted) _changed(portfolios, () => _date = picked);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final portfolios = ref.watch(portfolioListProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.addTxTitle),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: AsyncValueView<List<PortfolioRef>>(
        value: portfolios,
        onRetry: () => ref.invalidate(portfolioListProvider),
        data: (list) => switch (_step) {
          _Step.form => _form(context, list),
          _Step.review => _reviewStep(context, list),
          _Step.done => _doneStep(context),
        },
      ),
    );
  }

  // ------------------------------------------------------------------------------- form
  Widget _form(BuildContext context, List<PortfolioRef> portfolios) {
    final l10n = AppLocalizations.of(context);
    final currency = _currencyOf(portfolios);
    final holdings = _portfolioId == null
        ? const AsyncValue<List<HoldingSummary>>.data([])
        : ref.watch(portfolioHoldingsProvider(_portfolioId!));
    final assets = holdings.value ?? const <HoldingSummary>[];

    String? error(TxField f) =>
        _issues[f] == null ? null : txIssueText(l10n, f, _issues[f]!);

    InputDecoration decoration(String label, TxField f, {String? helper}) =>
        InputDecoration(
          labelText: label,
          errorText: error(f),
          errorMaxLines: 3,
          helperText: helper,
          helperMaxLines: 2,
        );

    Widget number(
      TextEditingController c,
      String label,
      TxField f, {
      String? helper,
      TextInputAction action = TextInputAction.next,
    }) => TextField(
      controller: c,
      decoration: decoration(label, f, helper: helper),
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      textInputAction: action,
      inputFormatters: [
        // Typing a letter is ignored; a pasted comma or minus is kept so validation can explain.
        FilteringTextInputFormatter.allow(RegExp(r'[0-9.,\-]')),
      ],
      onChanged: (_) => _changed(portfolios, () {}),
    );

    const gap = SizedBox(height: AppSpacing.m);
    return ListView(
      padding: const EdgeInsetsDirectional.all(AppSpacing.m),
      children: [
        if (widget.correctionOf != null) ...[
          StatusBanner(
            icon: Icons.edit_note_rounded,
            message: l10n.addTxCorrectionBanner,
          ),
          gap,
        ],
        if (_issues.isNotEmpty) ...[
          Semantics(
            liveRegion: true,
            child: StatusBanner(
              icon: Icons.error_outline_rounded,
              message: l10n.addTxFixFields(_issues.length),
            ),
          ),
          gap,
        ],
        DropdownButtonFormField<String>(
          key: ValueKey('portfolio-$_portfolioId'),
          initialValue: _portfolioId,
          isExpanded: true,
          decoration: decoration(l10n.addTxPortfolio, TxField.portfolio),
          items: [
            for (final p in portfolios)
              DropdownMenuItem(value: p.id, child: Text(p.name)),
          ],
          onChanged: (v) => _changed(portfolios, () {
            if (v != _portfolioId) {
              _assetId = null;
              _assetSymbol = null;
              _assetName = null;
            }
            _portfolioId = v;
          }),
        ),
        gap,
        DropdownButtonFormField<TransactionKind>(
          key: ValueKey('kind-$_kind'),
          initialValue: _kind,
          isExpanded: true,
          decoration: decoration(l10n.addTxType, TxField.kind),
          items: [
            for (final k in addableKinds)
              DropdownMenuItem(
                value: k,
                child: Text(TransactionTile.label(l10n, k)),
              ),
          ],
          onChanged: (v) {
            if (v != null) _changed(portfolios, () => _kind = v);
          },
        ),
        if (_kind.needsAsset) ...[
          gap,
          DropdownButtonFormField<String>(
            key: ValueKey('asset-$_portfolioId-$_assetKey'),
            initialValue: _assetKey,
            isExpanded: true,
            decoration: decoration(l10n.addTxAsset, TxField.asset),
            items: [
              for (final a in assets)
                DropdownMenuItem(
                  value: a.detailKey,
                  child: Text(a.name, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: (v) => _changed(portfolios, () {
              final chosen = assets.where((a) => a.detailKey == v).firstOrNull;
              _assetId = chosen?.assetId;
              _assetSymbol = chosen?.symbol;
              _assetName = chosen?.name;
            }),
          ),
        ],
        gap,
        _DateField(
          label: l10n.addTxDate,
          hint: l10n.addTxDateHint,
          value: _date,
          error: error(TxField.date),
          onTap: () => _pickDate(portfolios),
        ),
        if (_kind.isTrade) ...[
          gap,
          number(_quantity, l10n.addTxQuantity, TxField.quantity),
          gap,
          number(_unitPrice, l10n.addTxUnitPrice, TxField.unitPrice),
          gap,
          number(_fee, l10n.addTxFee, TxField.fee),
        ] else ...[
          gap,
          number(_amount, l10n.addTxAmount, TxField.amount),
        ],
        gap,
        TextField(
          controller: _note,
          maxLength: 500,
          decoration: InputDecoration(labelText: l10n.addTxNote),
          textInputAction: TextInputAction.done,
        ),
        Text(
          l10n.addTxCurrencyNote(currency),
          style: context.wealthText.caption.copyWith(
            color: context.wealthColors.textMuted,
          ),
        ),
        gap,
        FilledButton(
          onPressed: () => _review(portfolios),
          child: Text(l10n.addTxReview),
        ),
      ],
    );
  }

  // ----------------------------------------------------------------------------- review
  Widget _reviewStep(BuildContext context, List<PortfolioRef> portfolios) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final money = context.moneyFormatter;
    final t = _validated!;
    final minor = CurrencyInfo.of(t.currency).minorUnits;
    String amountText(Decimal d) => money.format(
      Money(d, t.currency),
      fractionDigits: d.scale > minor ? d.scale : null,
    );
    final portfolioName =
        portfolios.where((p) => p.id == t.portfolioId).firstOrNull?.name ??
        t.portfolioId;
    final rows = <(String, String)>[
      (l10n.addTxType, TransactionTile.label(l10n, t.kind)),
      (l10n.addTxPortfolio, portfolioName),
      if (t.assetName != null) (l10n.addTxAsset, t.assetName!),
      (l10n.addTxDate, DateLabels.date(t.date, locale: context.formatLocale)),
      if (t.quantity != null) (l10n.addTxQuantity, t.quantity.toString()),
      if (t.unitPrice != null) (l10n.addTxUnitPrice, amountText(t.unitPrice!)),
      if (t.amount != null) (l10n.addTxAmount, amountText(t.amount!)),
      if (t.fee != null) (l10n.ledgerFieldFee, amountText(t.fee!)),
      if (t.note != null) (l10n.ledgerFieldNote, t.note!),
    ];
    return ListView(
      padding: const EdgeInsetsDirectional.all(AppSpacing.m),
      children: [
        if (_saveFailed) ...[
          Semantics(
            liveRegion: true,
            child: StatusBanner(
              icon: Icons.error_outline_rounded,
              message: l10n.addTxSaveFailed,
              actionLabel: l10n.addTxRetry,
              onAction: _save,
            ),
          ),
          const SizedBox(height: AppSpacing.m),
        ],
        Semantics(
          header: true,
          child: Text(l10n.addTxReviewTitle, style: text.title),
        ),
        const SizedBox(height: AppSpacing.s),
        WealthCard(
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
        ),
        const SizedBox(height: AppSpacing.s),
        if (t.kind.isTrade)
          Text(
            l10n.addTxServerTotalNote,
            style: text.caption.copyWith(color: context.wealthColors.textMuted),
          ),
        Text(
          l10n.addTxDemoNote,
          style: text.caption.copyWith(color: context.wealthColors.textMuted),
        ),
        const SizedBox(height: AppSpacing.m),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: Text(_saving ? l10n.addTxSaving : l10n.addTxSave),
        ),
        const SizedBox(height: AppSpacing.xs),
        OutlinedButton(
          onPressed: _saving ? null : () => setState(() => _step = _Step.form),
          child: Text(l10n.addTxBackToEdit),
        ),
      ],
    );
  }

  // ------------------------------------------------------------------------ confirmation
  Widget _doneStep(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final saved = _saved;
    return ListView(
      padding: const EdgeInsetsDirectional.all(AppSpacing.m),
      children: [
        const SizedBox(height: AppSpacing.l),
        Semantics(
          liveRegion: true,
          container: true,
          child: Column(
            children: [
              ExcludeSemantics(
                child: Icon(
                  Icons.check_circle_rounded,
                  size: 56,
                  color: context.wealthColors.positiveText,
                ),
              ),
              const SizedBox(height: AppSpacing.s),
              Text(
                l10n.addTxDoneTitle,
                style: text.headline,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                l10n.addTxDoneMessage,
                style: text.body,
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
        if (saved != null) ...[
          const SizedBox(height: AppSpacing.m),
          WealthCard(
            padding: EdgeInsets.zero,
            child: LedgerEntryTile(entry: saved),
          ),
        ],
        const SizedBox(height: AppSpacing.l),
        if (saved != null && widget.onOpenEntry != null)
          FilledButton(
            onPressed: () => widget.onOpenEntry!(saved.id),
            child: Text(l10n.addTxViewEntry),
          ),
        const SizedBox(height: AppSpacing.xs),
        OutlinedButton(onPressed: _reset, child: Text(l10n.addTxAddAnother)),
        const SizedBox(height: AppSpacing.xs),
        if (widget.onDone != null)
          TextButton(
            onPressed: widget.onDone,
            child: Text(l10n.addTxBackToList),
          ),
      ],
    );
  }
}

/// A read-only field that opens the date picker, with the same label, value and error layout as
/// the text fields.
class _DateField extends StatelessWidget {
  const _DateField({
    required this.label,
    required this.hint,
    required this.value,
    required this.error,
    required this.onTap,
  });

  final String label;
  final String hint;
  final DateTime? value;
  final String? error;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final shown = value == null
        ? hint
        : DateLabels.date(value!, locale: context.formatLocale);
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: AppTouchTarget.android),
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            errorText: error,
            errorMaxLines: 3,
            suffixIcon: const Icon(Icons.calendar_today_rounded),
          ),
          child: Text(
            shown,
            style: value == null
                ? context.wealthText.body.copyWith(
                    color: context.wealthColors.textMuted,
                  )
                : context.wealthText.body,
          ),
        ),
      ),
    );
  }
}

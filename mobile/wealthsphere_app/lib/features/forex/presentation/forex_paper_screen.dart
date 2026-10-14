import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../core/data/demo_support.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/forex_providers.dart';
import '../data/forex_repository.dart';
import '../domain/forex_models.dart';
import 'forex_widgets.dart';

/// PAPER TRADING and the journal (P13-T11.7): virtual money only, labelled on every view. The
/// server fills simulated orders at the stored bid or ask and computes every balance and P/L
/// (P13-T09); the app shows them and sends the user's requests, nothing more. In DEMO mode the
/// fixture's sample account is shown read-only.
class ForexPaperScreen extends ConsumerStatefulWidget {
  const ForexPaperScreen({super.key});

  @override
  ConsumerState<ForexPaperScreen> createState() => _ForexPaperScreenState();
}

class _ForexPaperScreenState extends ConsumerState<ForexPaperScreen> {
  bool _showOpen = true;

  void _refresh(String accountId) => ref
    ..invalidate(paperAccountsProvider)
    ..invalidate(paperPositionsProvider(accountId))
    ..invalidate(journalProvider(accountId))
    ..invalidate(paperPerformanceProvider(accountId));

  Future<void> _attempt(
    Future<void> Function() action,
    String accountId,
  ) async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final failed = l10n.errorGenericTitle;
    try {
      await action();
      _refresh(accountId);
    } on DemoDataException {
      messenger.showSnackBar(SnackBar(content: Text(l10n.fxDemoReadOnly)));
    } on Object {
      messenger.showSnackBar(SnackBar(content: Text(failed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.fxPaperTitle),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: AsyncValueView(
        value: ref.watch(paperAccountsProvider),
        onRetry: () => ref.invalidate(paperAccountsProvider),
        data: (accounts) => ListView(
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          children: [
            const PaperTradingBanner(),
            const SizedBox(height: AppSpacing.m),
            if (accounts.isEmpty)
              _NoAccount(
                onOpen: (name) => _attempt(
                  () => ref
                      .read(forexRepositoryProvider)
                      .openPaperAccount(name, 'USD'),
                  '',
                ),
              )
            else
              ..._account(context, accounts.first),
          ],
        ),
      ),
    );
  }

  List<Widget> _account(BuildContext context, PaperAccount a) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final c = a.currency;
    final repo = ref.read(forexRepositoryProvider);
    return [
      WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(a.name, style: text.title),
            Text(l10n.fxBalanceLine('${a.balance} $c', '${a.equity} $c')),
            Text(l10n.fxMarginLine('${a.usedMargin} $c', '${a.freeMargin} $c')),
            Text(l10n.fxUnrealised('${a.unrealised} $c')),
            for (final w in a.warnings) Text('• $w', style: text.caption),
          ],
        ),
      ),
      ForexHeading(l10n.fxPositions),
      SegmentedButton<bool>(
        segments: [
          ButtonSegment(value: true, label: Text(l10n.fxOpen)),
          ButtonSegment(value: false, label: Text(l10n.fxClosed)),
        ],
        selected: {_showOpen},
        onSelectionChanged: (s) => setState(() => _showOpen = s.first),
      ),
      const SizedBox(height: AppSpacing.s),
      AsyncValueView(
        value: ref.watch(paperPositionsProvider(a.id)),
        onRetry: () => ref.invalidate(paperPositionsProvider(a.id)),
        data: (positions) {
          final shown = positions.where((p) => p.open == _showOpen).toList();
          if (shown.isEmpty) return Text(l10n.fxNoPositions);
          return Column(
            children: [
              for (final p in shown)
                _PositionCard(
                  p,
                  currency: c,
                  onClose: p.open
                      ? () => _attempt(
                          () => repo.closePaperPosition(a.id, p.id),
                          a.id,
                        )
                      : null,
                ),
            ],
          );
        },
      ),
      const SizedBox(height: AppSpacing.s),
      OutlinedButton.icon(
        onPressed: a.active
            ? () async {
                final order = await showModalBottomSheet<PaperOrderRequest>(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => const _OrderSheet(),
                );
                if (order != null) {
                  await _attempt(() async {
                    final placed = await repo.placePaperOrder(a.id, order);
                    if (!context.mounted) return;
                    await showDialog<void>(
                      context: context,
                      builder: (_) => AlertDialog(
                        title: Text(l10n.fxOrderPlaced),
                        content: SingleChildScrollView(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const PaperTradingBanner(),
                              for (final w in placed.warnings) Text('• $w'),
                              for (final d in placed.disclosures)
                                Text('• $d', style: context.wealthText.caption),
                            ],
                          ),
                        ),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.of(context).pop(),
                            child: Text(
                              MaterialLocalizations.of(context).okButtonLabel,
                            ),
                          ),
                        ],
                      ),
                    );
                  }, a.id);
                }
              }
            : null,
        icon: const Icon(Icons.add),
        label: Text(l10n.fxNewOrder),
      ),
      ForexHeading(l10n.fxPerformance),
      AsyncValueView(
        value: ref.watch(paperPerformanceProvider(a.id)),
        onRetry: () => ref.invalidate(paperPerformanceProvider(a.id)),
        data: (perf) => WealthCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                l10n.fxPerformanceLine(
                  '${perf.trades}',
                  '${perf.netPnl} ${perf.currency}',
                  '${perf.returnOnStart.shift(2)}',
                ),
              ),
              Text(perf.seriesNote, style: text.caption),
            ],
          ),
        ),
      ),
      ForexHeading(l10n.fxJournal),
      AsyncValueView(
        value: ref.watch(journalProvider(a.id)),
        onRetry: () => ref.invalidate(journalProvider(a.id)),
        data: (notes) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (notes.isEmpty) Text(l10n.fxNoJournal),
            for (final n in notes)
              Padding(
                padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
                child: WealthCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(n.note),
                      if (n.tags.isNotEmpty)
                        Wrap(
                          spacing: AppSpacing.xs,
                          children: [
                            for (final t in n.tags) Chip(label: Text(t)),
                          ],
                        ),
                    ],
                  ),
                ),
              ),
            TextButton.icon(
              onPressed: () async {
                final note = await showDialog<(String, List<String>)>(
                  context: context,
                  builder: (_) => const _NoteDialog(),
                );
                if (note != null) {
                  await _attempt(
                    () => repo.addJournalEntry(a.id, note.$1, note.$2),
                    a.id,
                  );
                }
              },
              icon: const Icon(Icons.edit_note_outlined),
              label: Text(l10n.fxAddNote),
            ),
          ],
        ),
      ),
    ];
  }
}

class _PositionCard extends StatelessWidget {
  const _PositionCard(this.p, {required this.currency, this.onClose});

  final PaperPosition p;
  final String currency;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
      child: WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(p.pair, style: text.title)),
                PriceKindChip(kind: p.kind),
              ],
            ),
            Text(
              l10n.fxPositionLine(
                p.long ? l10n.fxLong : l10n.fxShort,
                '${p.lots}',
                '${p.entryPrice}',
              ),
            ),
            Text(
              '${l10n.fxStop} ${p.stop}${p.target == null ? '' : ' · ${p.target}'}',
              style: text.caption,
            ),
            if (p.open && p.unrealised != null)
              Text(l10n.fxUnrealised('${p.unrealised} $currency')),
            if (!p.open && p.realised != null)
              Text(
                l10n.fxRealised('${p.realised} $currency', p.exitReason ?? ''),
              ),
            if (onClose != null)
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: TextButton(
                  onPressed: onClose,
                  child: Text(l10n.fxClosePosition),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _NoAccount extends StatefulWidget {
  const _NoAccount({required this.onOpen});

  final void Function(String name) onOpen;

  @override
  State<_NoAccount> createState() => _NoAccountState();
}

class _NoAccountState extends State<_NoAccount> {
  final _name = TextEditingController(text: 'Practice');

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.fxNoAccounts),
          const SizedBox(height: AppSpacing.s),
          TextField(
            controller: _name,
            decoration: InputDecoration(labelText: l10n.fxAccountName),
          ),
          const SizedBox(height: AppSpacing.s),
          FilledButton(
            onPressed: () => widget.onOpen(_name.text.trim()),
            child: Text(l10n.fxOpenAccount),
          ),
        ],
      ),
    );
  }
}

class _OrderSheet extends StatefulWidget {
  const _OrderSheet();

  @override
  State<_OrderSheet> createState() => _OrderSheetState();
}

class _OrderSheetState extends State<_OrderSheet> {
  final _form = GlobalKey<FormState>();
  final _pair = TextEditingController(text: 'EUR_USD');
  final _lots = TextEditingController(text: '0.1');
  final _stop = TextEditingController();
  final _target = TextEditingController();
  final _limit = TextEditingController();
  bool _long = true;

  @override
  void dispose() {
    for (final c in [_pair, _lots, _stop, _target, _limit]) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    String? number(String? v, {bool optional = false}) {
      if (optional && (v ?? '').trim().isEmpty) return null;
      return parseDecimalInput(v ?? '') == null ? l10n.fxInvalidNumber : null;
    }

    return Padding(
      padding: EdgeInsetsDirectional.only(
        start: AppSpacing.m,
        end: AppSpacing.m,
        top: AppSpacing.m,
        bottom: MediaQuery.viewInsetsOf(context).bottom + AppSpacing.m,
      ),
      child: Form(
        key: _form,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const PaperTradingBanner(),
              const SizedBox(height: AppSpacing.s),
              TextFormField(
                controller: _pair,
                decoration: InputDecoration(labelText: l10n.fxPair),
              ),
              SegmentedButton<bool>(
                segments: [
                  ButtonSegment(value: true, label: Text(l10n.fxLong)),
                  ButtonSegment(value: false, label: Text(l10n.fxShort)),
                ],
                selected: {_long},
                onSelectionChanged: (s) => setState(() => _long = s.first),
              ),
              for (final (c, label, optional) in [
                (_lots, l10n.fxLots, false),
                (_stop, l10n.fxStop, false),
                (_target, l10n.fxTarget, true),
                (_limit, l10n.fxLimitPrice, true),
              ])
                TextFormField(
                  controller: c,
                  decoration: InputDecoration(labelText: label),
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  validator: (v) => number(v, optional: optional),
                ),
              const SizedBox(height: AppSpacing.m),
              FilledButton(
                onPressed: () {
                  if (!(_form.currentState?.validate() ?? false)) return;
                  Navigator.of(context).pop(
                    PaperOrderRequest(
                      instrument: _pair.text.trim().toUpperCase(),
                      long: _long,
                      lots: parseDecimalInput(_lots.text)!,
                      stop: parseDecimalInput(_stop.text)!,
                      target: parseDecimalInput(_target.text),
                      limitPrice: parseDecimalInput(_limit.text),
                    ),
                  );
                },
                child: Text(l10n.fxPlaceOrder),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NoteDialog extends StatefulWidget {
  const _NoteDialog();

  @override
  State<_NoteDialog> createState() => _NoteDialogState();
}

class _NoteDialogState extends State<_NoteDialog> {
  final _note = TextEditingController();
  final _tags = TextEditingController();

  @override
  void dispose() {
    _note.dispose();
    _tags.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return AlertDialog(
      title: Text(l10n.fxAddNote),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _note,
            decoration: InputDecoration(labelText: l10n.fxNote),
            maxLines: 4,
          ),
          TextField(
            controller: _tags,
            decoration: InputDecoration(labelText: l10n.fxTags),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(l10n.fxCancel),
        ),
        FilledButton(
          onPressed: () {
            final note = _note.text.trim();
            if (note.isEmpty) return;
            final tags = [
              for (final t in _tags.text.split(','))
                if (t.trim().isNotEmpty) t.trim().toLowerCase(),
            ];
            Navigator.of(context).pop((note, tags));
          },
          child: Text(l10n.fxSave),
        ),
      ],
    );
  }
}

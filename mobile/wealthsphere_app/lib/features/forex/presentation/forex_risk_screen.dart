import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../data/forex_repository.dart';
import '../domain/forex_models.dart';
import 'forex_widgets.dart';

/// Trade setup and the risk calculator (P13-T11.5). The server sizes the position and computes
/// every figure (P13-T07); the form only checks that each field is a plain number. Warnings and
/// the disclosures (a stop can slip or gap) are always shown with the result. Nothing is placed.
class ForexRiskScreen extends ConsumerStatefulWidget {
  const ForexRiskScreen({this.instrument = 'EUR_USD', super.key});

  final String instrument;

  @override
  ConsumerState<ForexRiskScreen> createState() => _ForexRiskScreenState();
}

class _ForexRiskScreenState extends ConsumerState<ForexRiskScreen> {
  final _form = GlobalKey<FormState>();
  late final _pair = TextEditingController(text: widget.instrument);
  final _entry = TextEditingController();
  final _stop = TextEditingController();
  final _target = TextEditingController();
  final _balance = TextEditingController(text: '10000');
  final _currency = TextEditingController(text: 'USD');
  final _risk = TextEditingController(text: '1');
  bool _long = true;
  bool _busy = false;
  ForexRiskResult? _result;
  Object? _error;

  @override
  void dispose() {
    for (final c in [
      _pair,
      _entry,
      _stop,
      _target,
      _balance,
      _currency,
      _risk,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _number(String? text, {bool optional = false}) {
    final value = text ?? '';
    if (optional && value.trim().isEmpty) return null;
    return parseDecimalInput(value) == null
        ? AppLocalizations.of(context).fxInvalidNumber
        : null;
  }

  Future<void> _calculate() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await ref.read(forexRepositoryProvider).calculateRisk({
        'instrument': _pair.text.trim().toUpperCase(),
        'direction': _long ? 'long' : 'short',
        'entry': _entry.text.trim(),
        'stop': _stop.text.trim(),
        if (_target.text.trim().isNotEmpty) 'target': _target.text.trim(),
        'balance': _balance.text.trim(),
        'account_currency': _currency.text.trim().toUpperCase(),
        'risk_percent': _risk.text.trim(),
      });
      setState(() => _result = result);
    } on Object catch (e) {
      setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    InputDecoration field(String label) =>
        InputDecoration(labelText: label, border: const OutlineInputBorder());
    const gap = SizedBox(height: AppSpacing.s);
    final result = _result;
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.fxRiskTitle),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: ListView(
        padding: const EdgeInsetsDirectional.all(AppSpacing.m),
        children: [
          Form(
            key: _form,
            child: Column(
              children: [
                TextFormField(
                  controller: _pair,
                  decoration: field(l10n.fxPair),
                ),
                gap,
                SegmentedButton<bool>(
                  segments: [
                    ButtonSegment(value: true, label: Text(l10n.fxLong)),
                    ButtonSegment(value: false, label: Text(l10n.fxShort)),
                  ],
                  selected: {_long},
                  onSelectionChanged: (s) => setState(() => _long = s.first),
                ),
                gap,
                for (final (c, label, optional) in [
                  (_entry, l10n.fxEntry, false),
                  (_stop, l10n.fxStop, false),
                  (_target, l10n.fxTarget, true),
                  (_balance, l10n.fxBalance, false),
                  (_risk, l10n.fxRiskPercent, false),
                ]) ...[
                  TextFormField(
                    controller: c,
                    decoration: field(label),
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    validator: (v) => _number(v, optional: optional),
                  ),
                  gap,
                ],
                TextFormField(
                  controller: _currency,
                  decoration: field(l10n.fxAccountCurrency),
                ),
                gap,
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _busy ? null : _calculate,
                    child: Text(l10n.fxCalculate),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.m),
          if (_error != null) LoadErrorView(error: _error, onRetry: _calculate),
          if (result != null) _Result(result),
        ],
      ),
    );
  }
}

class _Result extends StatelessWidget {
  const _Result(this.r);

  final ForexRiskResult r;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final c = r.accountCurrency;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        WealthCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.fxSize('${r.lots}', '${r.units}'), style: text.title),
              Text(l10n.fxPipValue('${r.pipValuePerLot}', c)),
              Text(l10n.fxLoss('${r.lossAfterCosts} $c')),
              if (r.profitAfterCosts != null)
                Text(l10n.fxProfit('${r.profitAfterCosts} $c')),
              if (r.riskRewardAfterCosts != null)
                Text(l10n.fxRiskReward('${r.riskRewardAfterCosts}')),
              Text(l10n.fxCosts('${r.costsTotal} $c')),
              Text(l10n.fxMargin('${r.margin} $c', '${r.leverage}')),
              Text(r.conversionPath, style: text.caption),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.s),
        LinesCard(
          title: l10n.fxWarnings,
          lines: r.warnings,
          icon: Icons.warning_amber_outlined,
        ),
        const SizedBox(height: AppSpacing.s),
        LinesCard(title: l10n.fxDisclosures, lines: r.disclosures),
      ],
    );
  }
}

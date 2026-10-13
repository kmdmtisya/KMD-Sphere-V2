import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../core/data/demo_support.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/money.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/currency_providers.dart';
import '../data/currency_repository.dart';
import '../domain/currency_models.dart';
import 'currency_widgets.dart';

final _demoExamplesProvider = FutureProvider<List<(Money, String)>>((
  ref,
) async {
  final repo = ref.watch(currencyRepositoryProvider);
  return repo is DemoCurrencyRepository ? repo.examples() : const [];
});

/// Converts an amount between two currencies with the server's current rate (P11-T07). Shows the
/// rate, its time and path, and the indicative-rate notice. The app never computes the amount.
class CurrencyConverterScreen extends ConsumerStatefulWidget {
  const CurrencyConverterScreen({super.key});

  @override
  ConsumerState<CurrencyConverterScreen> createState() =>
      _CurrencyConverterScreenState();
}

class _CurrencyConverterScreenState
    extends ConsumerState<CurrencyConverterScreen> {
  final _amount = TextEditingController(text: '100');
  String? _from;
  String? _to;
  Conversion? _result;
  String? _error;
  bool _busy = false;
  final List<Conversion> _recent = [];

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  void _defaults(List<SupportedCurrency> all, String reporting) {
    if (_from != null || all.isEmpty) return;
    _to = reporting;
    _from = all
        .firstWhere((c) => c.code != reporting, orElse: () => all.first)
        .code;
  }

  void _swap() => setState(() {
    final from = _from;
    _from = _to;
    _to = from;
    _result = null;
  });

  Future<void> _convert() async {
    final l10n = AppLocalizations.of(context);
    final from = _from;
    final to = _to;
    final amount = Decimal.tryParse(_amount.text.trim().replaceAll(',', ''));
    if (amount == null || amount <= Decimal.zero) {
      setState(() => _error = l10n.converterInvalidAmount);
      return;
    }
    if (from == null || to == null || from == to) {
      setState(() => _error = l10n.converterSameCurrency);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final conversion = await ref
          .read(currencyRepositoryProvider)
          .convert(Money(amount, from), to);
      if (!mounted) return;
      setState(() {
        _result = conversion;
        _recent.insert(0, conversion);
        if (_recent.length > 5) _recent.removeLast();
      });
    } on Object {
      if (mounted) setState(() => _error = l10n.converterFailed);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _refresh() async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await refreshRates(ref);
    } on Object {
      messenger.showSnackBar(SnackBar(content: Text(l10n.fxRefreshFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final currencies = ref.watch(currenciesProvider);
    final reporting = ref.watch(reportingCurrencyProvider).value;
    final demo = ref.watch(dataSourceModeProvider) == DataSourceMode.demo;
    final examples = ref.watch(_demoExamplesProvider).value ?? const [];

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.converterTitle),
        actions: [
          IconButton(
            tooltip: l10n.fxRefresh,
            icon: const Icon(Icons.refresh_rounded),
            onPressed: _refresh,
          ),
          const DataSourceBadge(),
          const SizedBox(width: AppSpacing.m),
        ],
      ),
      body: AsyncValueView<List<SupportedCurrency>>(
        value: currencies,
        onRetry: () => ref.invalidate(currenciesProvider),
        data: (all) {
          _defaults(all, reporting?.reportingCurrency ?? all.first.code);
          final items = [
            for (final c in all)
              DropdownMenuItem(
                value: c.code,
                child: Text('${c.code} · ${c.name}'),
              ),
          ];
          return ListView(
            padding: const EdgeInsetsDirectional.all(AppSpacing.m),
            children: [
              const FxStatusLine(),
              const SizedBox(height: AppSpacing.xxs),
              Text(
                l10n.converterInformationOnly,
                key: const ValueKey('converter-information-only'),
                style: context.wealthText.caption.copyWith(
                  color: context.wealthColors.textMuted,
                ),
              ),
              const SizedBox(height: AppSpacing.m),
              TextField(
                key: const ValueKey('converter-amount'),
                controller: _amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: InputDecoration(labelText: l10n.converterAmount),
              ),
              const SizedBox(height: AppSpacing.s),
              DropdownButtonFormField<String>(
                key: ValueKey('converter-from-$_from'),
                initialValue: _from,
                isExpanded: true,
                decoration: InputDecoration(labelText: l10n.converterFrom),
                items: items,
                onChanged: (v) => setState(() {
                  _from = v;
                  _result = null;
                }),
              ),
              Align(
                alignment: AlignmentDirectional.center,
                child: IconButton(
                  tooltip: l10n.converterSwap,
                  icon: const Icon(Icons.swap_vert_rounded),
                  onPressed: _swap,
                ),
              ),
              DropdownButtonFormField<String>(
                key: ValueKey('converter-to-$_to'),
                initialValue: _to,
                isExpanded: true,
                decoration: InputDecoration(labelText: l10n.converterTo),
                items: items,
                onChanged: (v) => setState(() {
                  _to = v;
                  _result = null;
                }),
              ),
              const SizedBox(height: AppSpacing.m),
              FilledButton(
                onPressed: _busy ? null : _convert,
                child: Text(l10n.converterConvert),
              ),
              if (_busy) ...[
                const SizedBox(height: AppSpacing.s),
                const LinearProgressIndicator(minHeight: 2),
              ],
              if (_error case final error?) ...[
                const SizedBox(height: AppSpacing.s),
                Text(
                  error,
                  key: const ValueKey('converter-error'),
                  style: context.wealthText.body.copyWith(
                    color: context.wealthColors.negativeText,
                  ),
                ),
              ],
              if (_result case final result?) ...[
                const SizedBox(height: AppSpacing.m),
                _ResultCard(result: result),
              ],
              if (demo && examples.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.l),
                Text(
                  l10n.converterDemoExamples,
                  style: context.wealthText.label,
                ),
                Wrap(
                  spacing: AppSpacing.xs,
                  children: [
                    for (final (money, to) in examples)
                      ActionChip(
                        label: Text(
                          '${money.amount} ${money.currencyCode} → $to',
                        ),
                        onPressed: () => setState(() {
                          _amount.text = money.amount.toString();
                          _from = money.currencyCode;
                          _to = to;
                          _result = null;
                        }),
                      ),
                  ],
                ),
              ],
              if (_recent.length > 1) ...[
                const SizedBox(height: AppSpacing.l),
                Semantics(
                  header: true,
                  child: Text(
                    l10n.converterRecent,
                    style: context.wealthText.label,
                  ),
                ),
                for (final c in _recent.skip(1))
                  ListTile(
                    contentPadding: EdgeInsetsDirectional.zero,
                    title: CurrencyAmount(money: c.converted),
                    subtitle: CurrencyAmount(money: c.source),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _ResultCard extends StatelessWidget {
  const _ResultCard({required this.result});

  final Conversion result;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final when = result.rateTimestamp == null
        ? ''
        : dataAsOfText(
            l10n,
            result.rateTimestamp!,
            now: DateTime.now(),
            locale: context.formatLocale,
          );
    return WealthCard(
      key: const ValueKey('converter-result'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CurrencyAmount(money: result.source, style: text.body),
          CurrencyAmount(money: result.converted, style: text.displayAmount),
          const SizedBox(height: AppSpacing.xs),
          Text(
            l10n.converterRate(
              result.source.currencyCode,
              result.rate.toString(),
              result.converted.currencyCode,
            ),
            style: text.body,
          ),
          if (result.path case final path?)
            Text(l10n.converterVia(path.join(' → ')), style: text.caption),
          if (result.rateTimestamp case final at?) DataAsOfLabel(asOf: at),
          if (result.providers.isNotEmpty)
            Text(
              fxSourceText(l10n, result.providers),
              key: const ValueKey('converter-source'),
              style: text.caption,
            ),
          if (result.status != FxRateStatus.current)
            Text(
              switch (result.status) {
                FxRateStatus.cached => l10n.fxStatusCached(when),
                FxRateStatus.stale => l10n.fxStatusStale(when),
                _ => l10n.fxStatusUnavailable,
              },
              style: text.caption.copyWith(color: context.wealthColors.warning),
            ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            result.notice,
            style: text.caption.copyWith(color: context.wealthColors.textMuted),
          ),
        ],
      ),
    );
  }
}

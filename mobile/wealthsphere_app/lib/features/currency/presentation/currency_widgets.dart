import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/currency_providers.dart';
import '../domain/currency_models.dart';

/// Opens the reporting-currency selector: search, recent currencies, every supported currency,
/// and when the rates were last updated. Choosing one saves it and refreshes every figure.
Future<void> showCurrencySelector(BuildContext context) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => const _CurrencySelectorSheet(),
    );

class _CurrencySelectorSheet extends ConsumerStatefulWidget {
  const _CurrencySelectorSheet();

  @override
  ConsumerState<_CurrencySelectorSheet> createState() =>
      _CurrencySelectorSheetState();
}

class _CurrencySelectorSheetState
    extends ConsumerState<_CurrencySelectorSheet> {
  final _search = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _choose(String code) async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);
    setState(() => _saving = true);
    try {
      await ref.read(reportingCurrencyProvider.notifier).select(code);
      navigator.pop();
    } on Object {
      messenger.showSnackBar(SnackBar(content: Text(l10n.currencySaveFailed)));
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final currencies = ref.watch(currenciesProvider);
    final selected = ref.watch(reportingCurrencyProvider).value;
    final query = _search.text;

    Widget row(SupportedCurrency c) {
      final isSelected = c.code == selected?.reportingCurrency;
      return Semantics(
        inMutuallyExclusiveGroup: true,
        checked: isSelected,
        child: ListTile(
          key: ValueKey('currency-${c.code}'),
          enabled: !_saving,
          leading: SizedBox(
            width: 48,
            child: Text(
              c.symbol,
              style: text.title,
              textAlign: TextAlign.center,
            ),
          ),
          title: Text(c.code),
          subtitle: Text(c.name),
          trailing: isSelected ? const Icon(Icons.check_rounded) : null,
          onTap: () => _choose(c.code),
        ),
      );
    }

    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.85,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: AppSpacing.m,
              ),
              child: Semantics(
                header: true,
                child: Text(l10n.currencySelectorTitle, style: text.title),
              ),
            ),
            const Padding(
              padding: EdgeInsetsDirectional.symmetric(
                horizontal: AppSpacing.m,
                vertical: AppSpacing.xxs,
              ),
              child: FxStatusLine(),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.all(AppSpacing.m),
              child: TextField(
                controller: _search,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search_rounded),
                  hintText: l10n.currencySearchHint,
                ),
              ),
            ),
            if (_saving) const LinearProgressIndicator(minHeight: 2),
            Flexible(
              child: AsyncValueView<List<SupportedCurrency>>(
                value: currencies,
                onRetry: () => ref.invalidate(currenciesProvider),
                data: (all) {
                  final matching = [
                    for (final c in all)
                      if (c.matches(query)) c,
                  ];
                  final recent = query.isEmpty
                      ? [
                          for (final code
                              in selected?.recentCurrencies ?? const <String>[])
                            ...all.where((c) => c.code == code),
                        ]
                      : const <SupportedCurrency>[];
                  if (matching.isEmpty) {
                    return EmptyState(
                      icon: Icons.search_off_rounded,
                      message: l10n.currencyNoMatch(query),
                    );
                  }
                  return ListView(
                    shrinkWrap: true,
                    children: [
                      if (recent.isNotEmpty) ...[
                        _SheetHeading(l10n.currencyRecent),
                        for (final c in recent) row(c),
                        _SheetHeading(l10n.currencyAll),
                      ],
                      for (final c in matching) row(c),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SheetHeading extends StatelessWidget {
  const _SheetHeading(this.label);

  final String label;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.fromSTEB(
      AppSpacing.m,
      AppSpacing.s,
      AppSpacing.m,
      AppSpacing.xxs,
    ),
    child: Semantics(
      header: true,
      child: Text(
        label,
        style: context.wealthText.label.copyWith(
          color: context.wealthColors.textMuted,
        ),
      ),
    ),
  );
}

/// "USD ▾" next to Total Wealth: the reporting currency, tap to change it.
class ReportingCurrencyChip extends ConsumerWidget {
  const ReportingCurrencyChip({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final code = ref.watch(reportingCurrencyProvider).value?.reportingCurrency;
    if (code == null) return const SizedBox.shrink();
    return Semantics(
      button: true,
      label: l10n.currencyChipSpoken(code),
      excludeSemantics: true,
      child: Tooltip(
        message: l10n.currencyChipTooltip,
        child: ActionChip(
          key: const ValueKey('reporting-currency-chip'),
          avatar: const Icon(Icons.currency_exchange_rounded, size: 18),
          label: Row(
            mainAxisSize: MainAxisSize.min,
            children: [Text(code), const Icon(Icons.arrow_drop_down_rounded)],
          ),
          onPressed: () => showCurrencySelector(context),
        ),
      ),
    );
  }
}

/// How fresh the rates behind the figures are: current, cached, old or unavailable, with when.
/// Cached rates are never presented as current.
class FxStatusLine extends ConsumerWidget {
  const FxStatusLine({this.now, super.key});

  /// Injectable clock for tests.
  final DateTime? now;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final status = ref.watch(fxStatusProvider);
    final colors = context.wealthColors;
    final style = context.wealthText.caption;
    return status.when(
      loading: () => const SizedBox(height: 16),
      error: (_, _) => Text(l10n.fxStatusUnavailable, style: style),
      data: (s) {
        final updated = s.lastUpdated;
        final when = updated == null
            ? ''
            : dataAsOfText(
                l10n,
                updated,
                now: now ?? DateTime.now(),
                locale: context.formatLocale,
              );
        final (label, icon, color) = switch (s.overall) {
          FxRateStatus.current => (
            l10n.fxStatusCurrent(when),
            Icons.check_circle_outline_rounded,
            colors.textMuted,
          ),
          FxRateStatus.cached => (
            l10n.fxStatusCached(when),
            Icons.history_rounded,
            colors.warning,
          ),
          FxRateStatus.stale => (
            l10n.fxStatusStale(when),
            Icons.warning_amber_rounded,
            colors.warning,
          ),
          FxRateStatus.unavailable => (
            l10n.fxStatusUnavailable,
            Icons.cloud_off_rounded,
            colors.negativeText,
          ),
        };
        return Row(
          key: ValueKey('fx-status-${s.overall.name}'),
          children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: AppSpacing.xxs),
            Flexible(child: Text(label, style: style)),
          ],
        );
      },
    );
  }
}

/// The Settings row for the reporting currency.
class ReportingCurrencyTile extends ConsumerWidget {
  const ReportingCurrencyTile({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final preferences = ref.watch(reportingCurrencyProvider);
    final currencies = ref.watch(currenciesProvider).value ?? const [];
    final demo = ref.watch(dataSourceModeProvider) == DataSourceMode.demo;
    final code = preferences.value?.reportingCurrency;
    final name = currencies
        .where((c) => c.code == code)
        .map((c) => c.name)
        .firstOrNull;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ListTile(
          key: const ValueKey('reporting-currency-tile'),
          contentPadding: EdgeInsetsDirectional.zero,
          leading: const Icon(Icons.currency_exchange_rounded),
          title: Text(l10n.currencyReportingTitle),
          subtitle: code == null
              ? null
              : Text(
                  name == null
                      ? code
                      : l10n.currencyReportingSubtitle(code, name),
                ),
          trailing: const Icon(Icons.chevron_right_rounded),
          onTap: preferences.hasValue
              ? () => showCurrencySelector(context)
              : null,
        ),
        if (demo)
          Text(
            l10n.currencyDemoNote,
            style: context.wealthText.caption.copyWith(
              color: context.wealthColors.textMuted,
            ),
          ),
      ],
    );
  }
}

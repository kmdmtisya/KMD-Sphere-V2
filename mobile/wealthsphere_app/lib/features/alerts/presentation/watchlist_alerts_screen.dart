import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/alerts_providers.dart';
import '../data/alerts_repository.dart';
import '../domain/alert_models.dart';
import 'alert_preferences_card.dart';

/// The investments the user follows, with their latest stored prices, and the alerts they set
/// (and the ones that fired). Prices are stored, delayed prices with their time and provider; an
/// old one is labelled, a missing one says so. Nothing here trades.
class WatchlistAlertsScreen extends ConsumerWidget {
  const WatchlistAlertsScreen({this.onOpenInvestment, super.key});

  /// Opens an investment (by asset id live, symbol in DEMO).
  final void Function(String assetKey)? onOpenInvestment;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.watchlistAlertsTitle),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref
          ..invalidate(watchlistItemsProvider)
          ..invalidate(alertsProvider)
          ..invalidate(alertEventsProvider)
          ..invalidate(alertPreferencesProvider),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          children: [
            _Header(l10n.watchlistTitle),
            _Watchlist(onOpen: onOpenInvestment),
            const SizedBox(height: AppSpacing.l),
            _Header(l10n.alertsTitle),
            const _Alerts(),
            const SizedBox(height: AppSpacing.l),
            _Header(l10n.alertEventsTitle),
            const _Events(),
            const SizedBox(height: AppSpacing.l),
            _Header(l10n.alertPrefsTitle),
            const AlertPreferencesCard(),
            const SizedBox(height: AppSpacing.m),
            Text(
              l10n.alertsFootnote,
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

class _Header extends StatelessWidget {
  const _Header(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
    child: Semantics(
      header: true,
      child: Text(text, style: context.wealthText.title),
    ),
  );
}

class _Watchlist extends ConsumerWidget {
  const _Watchlist({required this.onOpen});

  final void Function(String assetKey)? onOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return AsyncValueView<List<WatchItem>>(
      value: ref.watch(watchlistItemsProvider),
      onRetry: () => ref.invalidate(watchlistItemsProvider),
      isEmpty: (items) => items.isEmpty,
      empty: _Muted(l10n.watchlistEmpty),
      data: (items) => WealthCard(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            for (final i in items)
              _WatchRow(
                item: i,
                onTap: onOpen == null ? null : () => onOpen!(i.assetKey),
              ),
          ],
        ),
      ),
    );
  }
}

class _WatchRow extends StatelessWidget {
  const _WatchRow({required this.item, required this.onTap});

  final WatchItem item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final price = item.price;
    final asOf = item.priceAsOf;
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: AppTouchTarget.android),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: AppSpacing.m,
            vertical: AppSpacing.s,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.symbol ?? item.name, style: text.title),
                    if (item.symbol != null)
                      Text(
                        item.name,
                        style: text.caption.copyWith(color: colors.textMuted),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.s),
              Flexible(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    if (price == null)
                      Text(
                        l10n.investNoPriceYet,
                        style: text.caption.copyWith(color: colors.textMuted),
                      )
                    else
                      Text(
                        context.moneyFormatter.format(
                          price,
                          fractionDigits: price.amount.scale > 2 ? 4 : null,
                        ),
                        style: text.amount,
                      ),
                    if (asOf != null) DataAsOfLabel(asOf: asOf),
                    if (item.stale) StaleChip(label: l10n.priceOutOfDate),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _condition(AppLocalizations l10n, BuildContext context, PriceAlert a) {
  final money = context.moneyFormatter;
  final percents = context.percentFormatter;
  return switch (a.type) {
    AlertType.priceAbove when a.thresholdPrice != null => l10n.alertWhenAbove(
      money.format(a.thresholdPrice!),
    ),
    AlertType.priceBelow when a.thresholdPrice != null => l10n.alertWhenBelow(
      money.format(a.thresholdPrice!),
    ),
    AlertType.allocationAbove when a.thresholdPercent != null =>
      l10n.alertWhenShareAbove(
        a.assetClass ?? '',
        percents.format(a.thresholdPercent!),
      ),
    _ => '',
  };
}

String _status(AppLocalizations l10n, AlertStatus s) => switch (s) {
  AlertStatus.active => l10n.alertStatusActive,
  AlertStatus.triggered => l10n.alertStatusTriggered,
  AlertStatus.paused => l10n.alertStatusPaused,
};

class _Alerts extends ConsumerWidget {
  const _Alerts();

  Future<void> _run(
    BuildContext context,
    WidgetRef ref,
    Future<void> Function(AlertRepository repo) action,
  ) async {
    final l10n = AppLocalizations.of(context);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await action(ref.read(alertRepositoryProvider));
      ref.invalidate(alertsProvider);
    } on Object {
      messenger.showSnackBar(SnackBar(content: Text(l10n.alertSaveFailed)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    return AsyncValueView<List<PriceAlert>>(
      value: ref.watch(alertsProvider),
      onRetry: () => ref.invalidate(alertsProvider),
      isEmpty: (a) => a.isEmpty,
      empty: _Muted(l10n.alertsEmpty),
      data: (alerts) => WealthCard(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            for (final a in alerts)
              Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  horizontal: AppSpacing.m,
                  vertical: AppSpacing.s,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            a.assetSymbol ?? a.assetName ?? a.assetClass ?? '',
                            style: text.title,
                          ),
                          Text(_condition(l10n, context, a), style: text.body),
                          Text(
                            _status(l10n, a.status),
                            style: text.caption.copyWith(
                              color: context.wealthColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (a.status == AlertStatus.active)
                      TextButton(
                        onPressed: () => unawaited(
                          _run(
                            context,
                            ref,
                            (r) => r.setActive(a.id, active: false),
                          ),
                        ),
                        child: Text(l10n.alertPause),
                      )
                    else
                      TextButton(
                        onPressed: () => unawaited(
                          _run(
                            context,
                            ref,
                            (r) => r.setActive(a.id, active: true),
                          ),
                        ),
                        child: Text(
                          a.status == AlertStatus.triggered
                              ? l10n.alertRearm
                              : l10n.alertResume,
                        ),
                      ),
                    IconButton(
                      tooltip: l10n.alertDelete,
                      icon: const Icon(Icons.delete_outline_rounded),
                      onPressed: () =>
                          unawaited(_run(context, ref, (r) => r.delete(a.id))),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _Events extends ConsumerWidget {
  const _Events();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final locale = context.formatLocale;
    return AsyncValueView<List<AlertEvent>>(
      value: ref.watch(alertEventsProvider),
      onRetry: () => ref.invalidate(alertEventsProvider),
      isEmpty: (e) => e.isEmpty,
      empty: _Muted(l10n.alertEventsEmpty),
      data: (events) => WealthCard(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            for (final e in events)
              ListTile(
                title: Text(
                  e.type == AlertType.allocationAbove
                      ? l10n.alertFiredShare(
                          context.percentFormatter.format(e.observedValue),
                        )
                      : l10n.alertFiredPrice(e.observedValue.toString()),
                  style: text.body,
                ),
                subtitle: Text(
                  DateLabels.dateTime(e.triggeredAt.toLocal(), locale: locale),
                ),
                trailing: e.seen
                    ? null
                    : TextButton(
                        onPressed: () async {
                          await ref
                              .read(alertRepositoryProvider)
                              .markSeen(e.id);
                          ref.invalidate(alertEventsProvider);
                        },
                        child: Text(l10n.alertMarkSeen),
                      ),
              ),
          ],
        ),
      ),
    );
  }
}

class _Muted extends StatelessWidget {
  const _Muted(this.message);

  final String message;

  @override
  Widget build(BuildContext context) => WealthCard(
    child: Text(
      message,
      style: context.wealthText.body.copyWith(
        color: context.wealthColors.textMuted,
      ),
    ),
  );
}

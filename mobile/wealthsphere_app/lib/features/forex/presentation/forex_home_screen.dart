import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/forex_alerts.dart';
import '../application/forex_providers.dart';
import '../data/forex_stream.dart';
import 'forex_stream_scope.dart';
import 'forex_widgets.dart';

/// The forex section's home (P13-T11.1, T11.2): the notice, the live markets list (streamed,
/// each price with its type and freshness), links to the other forex screens, the notices and
/// the notification settings. Nothing here trades.
class ForexHomeScreen extends ConsumerWidget {
  const ForexHomeScreen({
    required this.onOpenPair,
    required this.onOpenOpportunities,
    required this.onOpenRisk,
    required this.onOpenCalendar,
    required this.onOpenPaper,
    required this.onOpenCopilot,
    super.key,
  });

  final void Function(String instrument) onOpenPair;
  final VoidCallback onOpenOpportunities;
  final VoidCallback onOpenRisk;
  final VoidCallback onOpenCalendar;
  final VoidCallback onOpenPaper;
  final VoidCallback onOpenCopilot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    return ForexStreamScope(
      child: Scaffold(
        appBar: AppBar(
          title: Text(l10n.fxTitle),
          actions: const [
            DataSourceBadge(),
            SizedBox(width: AppSpacing.m),
          ],
        ),
        body: RefreshIndicator(
          onRefresh: () async => ref
            ..invalidate(quoteBoardProvider)
            ..invalidate(forexNoticesProvider),
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsetsDirectional.all(AppSpacing.m),
            children: [
              Text(
                l10n.fxNotice,
                style: text.caption.copyWith(
                  color: context.wealthColors.textMuted,
                ),
              ),
              ForexHeading(l10n.fxMarkets),
              _Markets(onOpenPair: onOpenPair),
              ForexHeading(l10n.fxExplore),
              _Link(
                icon: Icons.leaderboard_outlined,
                title: l10n.fxOpportunitiesTitle,
                subtitle: l10n.fxOpportunitiesSubtitle,
                onTap: onOpenOpportunities,
              ),
              _Link(
                icon: Icons.calculate_outlined,
                title: l10n.fxRiskTitle,
                subtitle: l10n.fxRiskSubtitle,
                onTap: onOpenRisk,
              ),
              _Link(
                icon: Icons.event_outlined,
                title: l10n.fxCalendarTitle,
                subtitle: l10n.fxCalendarSubtitle,
                onTap: onOpenCalendar,
              ),
              _Link(
                icon: Icons.science_outlined,
                title: l10n.fxPaperTitle,
                subtitle: l10n.fxPaperSubtitle,
                onTap: onOpenPaper,
              ),
              _Link(
                icon: Icons.auto_awesome_outlined,
                title: l10n.fxCopilotTitle,
                subtitle: l10n.fxCopilotSubtitle,
                onTap: onOpenCopilot,
              ),
              ForexHeading(l10n.fxNoticesTitle),
              const _Notices(),
              ForexHeading(l10n.fxAlertsTitle),
              const _AlertSettings(),
            ],
          ),
        ),
      ),
    );
  }
}

class _Markets extends ConsumerWidget {
  const _Markets({required this.onOpenPair});

  final void Function(String instrument) onOpenPair;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final board = ref.watch(quoteBoardProvider);
    final live = ref.watch(liveQuotesProvider);
    final state =
        ref.watch(streamStateProvider).value ?? StreamState.connecting;
    return AsyncValueView(
      value: board,
      onRetry: () => ref.invalidate(quoteBoardProvider),
      data: (b) => WealthCard(
        child: Column(
          children: [
            StreamStateBanner(state: state),
            for (final q in b.items)
              QuoteRow(
                quote: live[q.instrument] ?? q,
                onTap: () => onOpenPair(q.instrument),
              ),
          ],
        ),
      ),
    );
  }
}

class _Link extends StatelessWidget {
  const _Link({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
    child: WealthCard(
      onTap: onTap,
      semanticLabel: '$title. $subtitle',
      child: Row(
        children: [
          Icon(icon),
          const SizedBox(width: AppSpacing.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: context.wealthText.title),
                Text(
                  subtitle,
                  style: context.wealthText.caption.copyWith(
                    color: context.wealthColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right),
        ],
      ),
    ),
  );
}

class _Notices extends ConsumerWidget {
  const _Notices();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return AsyncValueView(
      value: ref.watch(forexNoticesProvider),
      onRetry: () => ref.invalidate(forexNoticesProvider),
      isEmpty: (n) => n.isEmpty,
      empty: Text(l10n.fxNoNotices),
      data: (notices) => WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final n in notices)
              Padding(
                padding: const EdgeInsetsDirectional.only(
                  bottom: AppSpacing.xs,
                ),
                child: Row(
                  children: [
                    Icon(switch (n) {
                      EventSoonNotice() => Icons.event_available_outlined,
                      PaperClosedNotice() => Icons.science_outlined,
                    }, size: 18),
                    const SizedBox(width: AppSpacing.s),
                    Expanded(
                      child: Text(switch (n) {
                        EventSoonNotice(:final event, :final minutes) =>
                          l10n.fxNoticeEventSoon(
                            event.name,
                            '$minutes',
                            event.currencies.join(', '),
                          ),
                        PaperClosedNotice(:final position) =>
                          '${l10n.fxPaperTrading}: ${l10n.fxNoticePaperClosed(position.pair, position.exitReason ?? '', '${position.realised ?? ''}')}',
                      }),
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

class _AlertSettings extends ConsumerWidget {
  const _AlertSettings();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final prefs = ref.watch(forexAlertPrefsProvider);
    return AsyncValueView(
      value: prefs,
      data: (p) => WealthCard(
        child: Column(
          children: [
            SwitchListTile(
              contentPadding: EdgeInsetsDirectional.zero,
              title: Text(l10n.fxAlertsEventReminders),
              value: p.eventReminders,
              onChanged: (v) => ref
                  .read(forexAlertPrefsProvider.notifier)
                  .set(p.copyWith(eventReminders: v)),
            ),
            SwitchListTile(
              contentPadding: EdgeInsetsDirectional.zero,
              title: Text(l10n.fxAlertsPaperExits),
              value: p.paperExits,
              onChanged: (v) => ref
                  .read(forexAlertPrefsProvider.notifier)
                  .set(p.copyWith(paperExits: v)),
            ),
          ],
        ),
      ),
    );
  }
}

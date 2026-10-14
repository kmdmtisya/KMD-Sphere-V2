import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/forex_providers.dart';
import '../domain/forex_models.dart';
import 'forex_widgets.dart';

/// The economic calendar (P13-T11.6): scheduled events with importance, the consensus (labelled
/// as an expectation, not a fact), previous and actual values, and DEMO events marked as such.
class ForexCalendarScreen extends ConsumerWidget {
  const ForexCalendarScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.fxCalendarTitle),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(forexCalendarProvider),
        child: AsyncValueView(
          value: ref.watch(forexCalendarProvider),
          onRetry: () => ref.invalidate(forexCalendarProvider),
          isEmpty: (e) => e.isEmpty,
          empty: EmptyState(
            icon: Icons.event_busy_outlined,
            title: l10n.fxNoEvents,
          ),
          data: (events) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsetsDirectional.all(AppSpacing.m),
            children: [
              for (final e in [
                ...events,
              ]..sort((a, b) => a.scheduledAt.compareTo(b.scheduledAt)))
                _EventCard(e),
            ],
          ),
        ),
      ),
    );
  }
}

class _EventCard extends StatelessWidget {
  const _EventCard(this.e);

  final ForexEvent e;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final unit = e.unit ?? '';
    final high = e.importance == 'high';
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
      child: WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(e.name, style: text.title)),
                if (e.demo) ForexTagChip(text: l10n.fxDemoEvent),
              ],
            ),
            Text(
              '${DateLabels.dateTime(e.scheduledAt.toLocal(), locale: context.formatLocale)} · ${e.currencies.join(', ')}',
              style: text.caption,
            ),
            Row(
              children: [
                Icon(
                  high ? Icons.priority_high : Icons.info_outline,
                  size: 16,
                  color: high ? colors.warningText : colors.textMuted,
                ),
                const SizedBox(width: AppSpacing.xs),
                Flexible(child: Text(l10n.fxImportance(e.importance))),
              ],
            ),
            if (e.actual != null) Text(l10n.fxActual('${e.actual}$unit')),
            if (e.forecast != null)
              Text(l10n.fxConsensus('${e.forecast}$unit')),
            if (e.previous != null) Text(l10n.fxPrevious('${e.previous}$unit')),
          ],
        ),
      ),
    );
  }
}

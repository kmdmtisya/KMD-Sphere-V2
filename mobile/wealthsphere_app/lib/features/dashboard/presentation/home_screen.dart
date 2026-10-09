import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/app_routes.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/charts/charts.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../../shared/domain/chart_mapping.dart';
import '../../../shared/domain/wealth_models.dart';
import '../application/dashboard_providers.dart';
import '../domain/dashboard_layout.dart';

String sectionName(AppLocalizations l10n, DashboardSection s) => switch (s) {
  DashboardSection.wealthSummary => l10n.sectionWealthSummary,
  DashboardSection.metrics => l10n.sectionMetrics,
  DashboardSection.insight => l10n.sectionInsight,
  DashboardSection.goals => l10n.sectionGoals,
};

/// The Home tab: wealth summary with chart, key figures, AI insight and goals. Every section
/// loads independently, the layout can be personalised, and pulling down refreshes everything.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  bool _editing = false;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final name = ref.watch(greetingNameProvider);
    final layout = ref.watch(dashboardLayoutProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(
          name.maybeWhen(data: l10n.homeGreeting, orElse: () => l10n.appTitle),
        ),
        actions: [
          const DemoBadge(),
          IconButton(
            tooltip: l10n.notificationsTooltip,
            // Inert until notifications exist (P09-T08).
            onPressed: null,
            icon: const Icon(Icons.notifications_none_rounded),
          ),
          IconButton(
            tooltip: _editing ? l10n.customiseDone : l10n.customise,
            onPressed: () => setState(() => _editing = !_editing),
            icon: Icon(_editing ? Icons.check_rounded : Icons.tune_rounded),
          ),
        ],
      ),
      body: layout.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const _Sections(layout: null),
        data: (value) =>
            _editing ? _CustomiseList(layout: value) : _Sections(layout: value),
      ),
    );
  }
}

class _Sections extends ConsumerWidget {
  const _Sections({required this.layout});

  final DashboardLayout? layout;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sections = (layout ?? DashboardLayout.initial()).visible;
    return RefreshIndicator(
      onRefresh: () async => refreshDashboard(ref),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsetsDirectional.all(AppSpacing.m),
        children: [
          for (final s in sections) ...[
            switch (s) {
              DashboardSection.wealthSummary => const _WealthSummarySection(),
              DashboardSection.metrics => const _MetricsSection(),
              DashboardSection.insight => const _InsightSection(),
              DashboardSection.goals => const _GoalsSection(),
            },
            const SizedBox(height: AppSpacing.m),
          ],
        ],
      ),
    );
  }
}

// ----------------------------------------------------------------------- wealth summary
class _WealthSummarySection extends ConsumerWidget {
  const _WealthSummarySection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final summary = ref.watch(homeSummaryProvider);
    final period = ref.watch(homePeriodProvider);
    final series = ref.watch(homeSeriesProvider(period));

    return AsyncValueView<PortfolioSummary>(
      value: summary,
      onRetry: () => ref.invalidate(homeSummaryProvider),
      data: (s) => WealthSummaryCard(
        label: l10n.homeTotalWealth,
        amount: CurrencyAmount(
          money: s.value,
          style: context.wealthText.displayAmount,
        ),
        change: ChangeIndicator(percent: s.returnPercent, amount: s.profitLoss),
        chart: series.when(
          loading: () => PerformanceLineChart(
            series: ChartSeries(
              id: 'loading',
              label: l10n.homeTotalWealth,
              currencyCode: s.value.currencyCode,
              points: const [],
            ),
            loading: true,
          ),
          error: (_, _) => ErrorState(
            onRetry: () => ref.invalidate(homeSeriesProvider(period)),
          ),
          data: (data) => PerformanceLineChart(
            series: data.toChartSeries(l10n.homeTotalWealth),
            rangeLabel: period.spokenLabel(l10n),
          ),
        ),
        periodSelector: PeriodSelector(
          periods: homePeriods,
          selected: period,
          onChanged: ref.read(homePeriodProvider.notifier).select,
        ),
        footer: DataAsOfLabel(asOf: s.asOf),
      ),
    );
  }
}

// ----------------------------------------------------------------------------- metrics
class _MetricsSection extends ConsumerWidget {
  const _MetricsSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final summary = ref.watch(homeSummaryProvider);
    final netWorth = ref.watch(dashboardNetWorthProvider);
    final income = ref.watch(dashboardIncomeProvider);
    final goals = ref.watch(dashboardGoalsProvider);

    final tiles = <Widget>[
      _MetricTile<PortfolioSummary>(
        value: summary,
        retry: () => ref.invalidate(homeSummaryProvider),
        builder: (s) => MetricCard(
          icon: Icons.pie_chart_outline_rounded,
          label: l10n.homePortfolioValue,
          value: CurrencyAmount(money: s.value),
          onTap: () => context.go(AppRoutes.portfolio),
        ),
      ),
      _MetricTile<NetWorthSummary>(
        value: netWorth,
        retry: () => ref.invalidate(dashboardNetWorthProvider),
        builder: (n) => MetricCard(
          icon: Icons.account_balance_wallet_outlined,
          label: l10n.homeNetWorth,
          value: CurrencyAmount(money: n.netWorth),
          onTap: () => context.go(AppRoutes.portfolio),
        ),
      ),
      _MetricTile<IncomeSummary>(
        value: income,
        retry: () => ref.invalidate(dashboardIncomeProvider),
        builder: (i) => MetricCard(
          icon: Icons.savings_outlined,
          label: l10n.homeMonthlyIncome,
          value: CurrencyAmount(money: i.monthly),
          onTap: () => context.go(AppRoutes.portfolio),
        ),
      ),
      _MetricTile<GoalsSummary>(
        value: goals,
        retry: () => ref.invalidate(dashboardGoalsProvider),
        builder: (g) => MetricCard(
          icon: Icons.flag_outlined,
          label: l10n.homeGoals,
          value: Text(
            l10n.goalsOnTrack(g.onTrack),
            style: context.wealthText.amount,
          ),
          subValue: '${g.onTrack} / ${g.total}',
          onTap: () => context.go(AppRoutes.goals),
        ),
      ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = MediaQuery.textScalerOf(context).scale(1) <= 1.3;
        final width = wide
            ? (constraints.maxWidth - AppSpacing.s) / 2
            : constraints.maxWidth;
        return Wrap(
          spacing: AppSpacing.s,
          runSpacing: AppSpacing.s,
          children: [for (final t in tiles) SizedBox(width: width, child: t)],
        );
      },
    );
  }
}

class _MetricTile<T> extends StatelessWidget {
  const _MetricTile({
    required this.value,
    required this.retry,
    required this.builder,
  });

  final AsyncValue<T> value;
  final VoidCallback retry;
  final Widget Function(T data) builder;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return value.when(
      data: builder,
      loading: () => const SkeletonLoader(
        child: SkeletonBox(height: 96, radius: AppRadii.medium),
      ),
      error: (_, _) => WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.sectionFailed, style: context.wealthText.caption),
            TextButton(onPressed: retry, child: Text(l10n.retry)),
          ],
        ),
      ),
    );
  }
}

// ----------------------------------------------------------------------------- insight
class _InsightSection extends ConsumerWidget {
  const _InsightSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final insight = ref.watch(dashboardInsightProvider);
    return AsyncValueView<InsightSummary>(
      value: insight,
      onRetry: () => ref.invalidate(dashboardInsightProvider),
      data: (i) => WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.auto_awesome_outlined,
                  size: 20,
                  color: context.wealthColors.primary,
                ),
                const SizedBox(width: AppSpacing.xs),
                Expanded(child: Text(l10n.homeInsightTitle, style: text.title)),
              ],
            ),
            const SizedBox(height: AppSpacing.s),
            Text(i.text, style: text.body),
            const SizedBox(height: AppSpacing.s),
            DataAsOfLabel(asOf: i.asOf),
            Wrap(
              spacing: AppSpacing.xs,
              children: [
                for (final s in i.sources)
                  EvidenceSourceChip(source: s.toView()),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
            FilledButton.icon(
              onPressed: () => context.go(AppRoutes.ai),
              icon: const Icon(Icons.auto_awesome_rounded),
              label: Text(l10n.askWealthAi),
            ),
          ],
        ),
      ),
    );
  }
}

// ------------------------------------------------------------------------------- goals
class _GoalsSection extends ConsumerWidget {
  const _GoalsSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final percents = context.percentFormatter;
    final goals = ref.watch(dashboardGoalsProvider);
    return AsyncValueView<GoalsSummary>(
      value: goals,
      onRetry: () => ref.invalidate(dashboardGoalsProvider),
      isEmpty: (g) => g.items.isEmpty,
      data: (g) => WealthCard(
        onTap: () => context.go(AppRoutes.goals),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.homeGoals, style: text.title),
            const SizedBox(height: AppSpacing.s),
            for (final goal in g.items)
              _GoalRow(
                goal: goal,
                percents: percents,
                l10n: l10n,
                colors: colors,
              ),
          ],
        ),
      ),
    );
  }
}

class _GoalRow extends StatelessWidget {
  const _GoalRow({
    required this.goal,
    required this.percents,
    required this.l10n,
    required this.colors,
  });

  final GoalProgress goal;
  final PercentFormatter percents;
  final AppLocalizations l10n;
  final WealthColors colors;

  @override
  Widget build(BuildContext context) {
    final text = context.wealthText;
    final onTrack = goal.status == GoalStatus.onTrack;
    final status = onTrack ? l10n.goalStatusOnTrack : l10n.goalStatusBehind;
    final percent = percents.format(goal.progressPercent, fractionDigits: 0);
    // Progress bar fill only: a drawing fraction, not money.
    final fraction = (goal.progressPercent.toDouble() / 100).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
      child: Semantics(
        label: l10n.goalsProgressSpoken(goal.name, percent, status),
        excludeSemantics: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(goal.name, style: text.body),
            Row(
              children: [
                Icon(
                  onTrack
                      ? Icons.check_circle_outline_rounded
                      : Icons.schedule_rounded,
                  size: 16,
                  color: onTrack ? colors.positiveText : colors.warningText,
                ),
                const SizedBox(width: AppSpacing.xxs),
                Expanded(
                  child: Text('$percent · $status', style: text.caption),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xxs),
            LinearProgressIndicator(
              value: fraction,
              minHeight: 6,
              borderRadius: BorderRadius.circular(3),
            ),
          ],
        ),
      ),
    );
  }
}

// -------------------------------------------------------------------------- customise
class _CustomiseList extends ConsumerWidget {
  const _CustomiseList({required this.layout});

  final DashboardLayout layout;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final notifier = ref.read(dashboardLayoutProvider.notifier);
    final order = layout.order;
    return ListView(
      padding: const EdgeInsetsDirectional.all(AppSpacing.m),
      children: [
        Text(l10n.customiseTitle, style: context.wealthText.headline),
        const SizedBox(height: AppSpacing.s),
        for (var i = 0; i < order.length; i++)
          _CustomiseRow(
            key: ValueKey(order[i]),
            section: order[i],
            position: i + 1,
            total: order.length,
            visible: !layout.hidden.contains(order[i]),
            onMove: (delta) => notifier.move(order[i], delta),
            onVisible: (v) => notifier.setVisible(order[i], visible: v),
          ),
      ],
    );
  }
}

class _CustomiseRow extends StatelessWidget {
  const _CustomiseRow({
    required this.section,
    required this.position,
    required this.total,
    required this.visible,
    required this.onMove,
    required this.onVisible,
    super.key,
  });

  final DashboardSection section;
  final int position;
  final int total;
  final bool visible;
  final ValueChanged<int> onMove;
  final ValueChanged<bool> onVisible;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final name = sectionName(l10n, section);
    // Reordering never needs a drag: buttons for everyone, plus custom actions for screen readers.
    return Semantics(
      container: true,
      label: l10n.sectionPosition(name, '$position', '$total'),
      customSemanticsActions: {
        if (position > 1)
          CustomSemanticsAction(label: l10n.moveUp): () => onMove(-1),
        if (position < total)
          CustomSemanticsAction(label: l10n.moveDown): () => onMove(1),
      },
      child: WealthCard(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: AppSpacing.s,
          vertical: AppSpacing.xs,
        ),
        child: Row(
          children: [
            Expanded(child: Text(name, style: context.wealthText.title)),
            IconButton(
              tooltip: l10n.moveUp,
              onPressed: position > 1 ? () => onMove(-1) : null,
              icon: const Icon(Icons.arrow_upward_rounded),
            ),
            IconButton(
              tooltip: l10n.moveDown,
              onPressed: position < total ? () => onMove(1) : null,
              icon: const Icon(Icons.arrow_downward_rounded),
            ),
            Switch(value: visible, onChanged: onVisible),
          ],
        ),
      ),
    );
  }
}

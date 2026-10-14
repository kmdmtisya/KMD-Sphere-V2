import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/forex_providers.dart';
import '../domain/forex_models.dart';
import 'forex_widgets.dart';

/// The Opportunity Ranking Dashboard and scanner (P13-T11.4): research candidates from the
/// published rules and score, filtered by timeframe, setup, risk and tier. Each one shows its
/// label, score, scenario, risk, illustrative levels, every factor and its risks. None is a
/// recommendation.
class ForexOpportunitiesScreen extends ConsumerStatefulWidget {
  const ForexOpportunitiesScreen({required this.onOpenPair, super.key});

  final void Function(String instrument) onOpenPair;

  @override
  ConsumerState<ForexOpportunitiesScreen> createState() =>
      _ForexOpportunitiesScreenState();
}

class _ForexOpportunitiesScreenState
    extends ConsumerState<ForexOpportunitiesScreen> {
  static const _frames = ['15m', '1H', '4H', '1D'];
  static const _setups = [
    'trend_continuation',
    'breakout',
    'reversal',
    'range',
    'momentum',
    'mean_reversion',
  ];
  static const _risks = ['low', 'medium', 'medium_high', 'high'];
  static const _tiers = ['major', 'minor', 'exotic'];

  String _frame = '1H';
  String? _setup;
  String? _risk;
  String? _tier;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final filter = (timeframe: _frame, setup: _setup, risk: _risk, tier: _tier);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.fxOpportunitiesTitle),
        actions: const [
          DataSourceBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(rankingProvider(filter)),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsetsDirectional.all(AppSpacing.m),
          children: [
            Text(l10n.fxScanner, style: context.wealthText.title),
            const SizedBox(height: AppSpacing.s),
            _Choice(
              label: l10n.fxTimeframe,
              values: _frames,
              selected: _frame,
              allowNone: false,
              onSelected: (v) => setState(() => _frame = v ?? '1H'),
            ),
            _Choice(
              label: l10n.fxFilterSetup,
              values: _setups,
              selected: _setup,
              onSelected: (v) => setState(() => _setup = v),
            ),
            _Choice(
              label: l10n.fxFilterRisk,
              values: _risks,
              selected: _risk,
              onSelected: (v) => setState(() => _risk = v),
            ),
            _Choice(
              label: l10n.fxFilterTier,
              values: _tiers,
              selected: _tier,
              onSelected: (v) => setState(() => _tier = v),
            ),
            const SizedBox(height: AppSpacing.m),
            AsyncValueView(
              value: ref.watch(rankingProvider(filter)),
              onRetry: () => ref.invalidate(rankingProvider(filter)),
              data: (ranking) => Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    ranking.notice,
                    style: context.wealthText.caption.copyWith(
                      color: context.wealthColors.textMuted,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.s),
                  if (ranking.items.isEmpty) Text(l10n.fxNoCandidates),
                  for (final o in ranking.items)
                    _Candidate(
                      o,
                      onOpen: () => widget.onOpenPair(o.instrument),
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

class _Choice extends StatelessWidget {
  const _Choice({
    required this.label,
    required this.values,
    required this.selected,
    required this.onSelected,
    this.allowNone = true,
  });

  final String label;
  final List<String> values;
  final String? selected;
  final ValueChanged<String?> onSelected;
  final bool allowNone;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Semantics(
      label: label,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            if (allowNone)
              Padding(
                padding: const EdgeInsetsDirectional.only(end: AppSpacing.xs),
                child: ChoiceChip(
                  label: Text(l10n.fxFilterAny),
                  selected: selected == null,
                  onSelected: (_) => onSelected(null),
                ),
              ),
            for (final v in values)
              Padding(
                padding: const EdgeInsetsDirectional.only(end: AppSpacing.xs),
                child: ChoiceChip(
                  label: Text(v.replaceAll('_', ' ')),
                  selected: selected == v,
                  onSelected: (_) => onSelected(v),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _Candidate extends StatelessWidget {
  const _Candidate(this.o, {required this.onOpen});

  final ForexOpportunity o;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
      child: WealthCard(
        onTap: onOpen,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (o.rank != null) Text('#${o.rank}  ', style: text.title),
                Expanded(child: Text(o.pair, style: text.title)),
                Flexible(
                  child: Text(
                    l10n.fxScore('${o.score}'),
                    style: text.amount,
                    textAlign: TextAlign.end,
                  ),
                ),
              ],
            ),
            Text('${o.label} · ${o.scenario} · ${o.type.replaceAll('_', ' ')}'),
            Text(l10n.fxRiskLevel(o.risk.replaceAll('_', ' '))),
            Text(
              l10n.fxLevels(
                '${o.entry}',
                '${o.stop}',
                '${o.target}',
                '${o.riskReward}',
              ),
              style: text.caption,
            ),
            if (o.forecastLabel != null)
              Text(o.forecastLabel!, style: text.caption),
            ExpansionTile(
              tilePadding: EdgeInsetsDirectional.zero,
              title: Text(l10n.fxFactors),
              children: [
                for (final f in o.factors)
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: Text(
                      '${f.name.replaceAll('_', ' ')}: ${f.contribution} · ${f.detail}',
                    ),
                  ),
              ],
            ),
            LinesCard(
              title: l10n.fxRisks,
              lines: o.risks,
              icon: Icons.warning_amber_outlined,
            ),
          ],
        ),
      ),
    );
  }
}

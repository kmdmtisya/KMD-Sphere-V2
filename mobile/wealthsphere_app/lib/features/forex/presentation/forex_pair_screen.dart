import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/data_source_badge.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/forex_providers.dart';
import 'forex_stream_scope.dart';
import 'forex_widgets.dart';

/// One pair (P13-T11.3): the live price, the chart, indicators, support and resistance, the
/// model forecasts with their calibration labels, and the backtested rules. Every figure is the
/// server's; forecasts are never shown as what will happen.
class ForexPairScreen extends ConsumerStatefulWidget {
  const ForexPairScreen({
    required this.instrument,
    required this.onSetUpTrade,
    super.key,
  });

  final String instrument;
  final void Function(String instrument) onSetUpTrade;

  @override
  ConsumerState<ForexPairScreen> createState() => _ForexPairScreenState();
}

class _ForexPairScreenState extends ConsumerState<ForexPairScreen> {
  static const _frames = ['15m', '1H', '4H', '1D'];
  static const _horizons = ['4h', '24h'];
  String _frame = '1H';

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final pair = widget.instrument.replaceAll('_', '/');
    final key = (instrument: widget.instrument, timeframe: _frame);
    final quote = ref.watch(liveQuotesProvider)[widget.instrument];
    return ForexStreamScope(
      child: Scaffold(
        appBar: AppBar(
          title: Text(pair),
          actions: const [
            DataSourceBadge(),
            SizedBox(width: AppSpacing.m),
          ],
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => widget.onSetUpTrade(widget.instrument),
          icon: const Icon(Icons.calculate_outlined),
          label: Text(l10n.fxSetUpTrade),
        ),
        body: ListView(
          padding: const EdgeInsetsDirectional.fromSTEB(
            AppSpacing.m,
            AppSpacing.m,
            AppSpacing.m,
            AppSpacing.xxl,
          ),
          children: [
            if (quote != null) WealthCard(child: QuoteRow(quote: quote)),
            const SizedBox(height: AppSpacing.m),
            Semantics(
              label: l10n.fxTimeframe,
              child: SegmentedButton<String>(
                segments: [
                  for (final f in _frames)
                    ButtonSegment(value: f, label: Text(f)),
                ],
                selected: {_frame},
                onSelectionChanged: (s) => setState(() => _frame = s.first),
              ),
            ),
            ForexHeading(l10n.fxChartTitle),
            AsyncValueView(
              value: ref.watch(candlesProvider(key)),
              onRetry: () => ref.invalidate(candlesProvider(key)),
              isEmpty: (c) => c.isEmpty,
              empty: Text(l10n.fxNoBars),
              data: (candles) => ForexPriceChart(pair: pair, candles: candles),
            ),
            ForexHeading(l10n.fxIndicatorsTitle),
            AsyncValueView(
              value: ref.watch(indicatorsProvider(key)),
              onRetry: () => ref.invalidate(indicatorsProvider(key)),
              isEmpty: (v) => v.isEmpty,
              empty: Text(l10n.fxNoBars),
              data: (values) => WealthCard(
                child: Column(
                  children: [
                    for (final v in values)
                      _ValueRow(
                        v.name.toUpperCase(),
                        v.value?.toString() ?? '—',
                      ),
                  ],
                ),
              ),
            ),
            ForexHeading(l10n.fxLevelsTitle),
            AsyncValueView(
              value: ref.watch(levelsProvider(key)),
              onRetry: () => ref.invalidate(levelsProvider(key)),
              isEmpty: (v) => v.isEmpty,
              empty: Text(l10n.fxNoBars),
              data: (levels) => WealthCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final lv in levels)
                      Text(
                        l10n.fxLevelRow(
                          lv.role,
                          '${lv.price}',
                          '${lv.touches}',
                        ),
                      ),
                  ],
                ),
              ),
            ),
            ForexHeading(l10n.fxForecastTitle),
            for (final h in _horizons)
              _ForecastCard(instrument: widget.instrument, horizon: h),
            ForexHeading(l10n.fxBacktestsTitle),
            _Backtests(instrument: widget.instrument),
          ],
        ),
      ),
    );
  }
}

class _ValueRow extends StatelessWidget {
  const _ValueRow(this.name, this.value);

  final String name;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.symmetric(vertical: 2),
    child: Row(
      children: [
        Expanded(child: Text(name, style: context.wealthText.body)),
        Text(value, style: context.wealthText.amount),
      ],
    ),
  );
}

class _ForecastCard extends ConsumerWidget {
  const _ForecastCard({required this.instrument, required this.horizon});

  final String instrument;
  final String horizon;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final key = (instrument: instrument, horizon: horizon);
    final locale = context.formatLocale;
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
      child: AsyncValueView(
        value: ref.watch(forexForecastProvider(key)),
        onRetry: () => ref.invalidate(forexForecastProvider(key)),
        data: (f) => WealthCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(horizon, style: context.wealthText.title),
              if (!f.available)
                Text(l10n.fxForecastUnavailable(f.reason ?? ''))
              else ...[
                Text(
                  l10n.fxForecastProbUp(_percent(f.probUp!), horizon),
                  style: context.wealthText.body,
                ),
                Row(
                  children: [
                    Icon(
                      f.calibrated
                          ? Icons.verified_outlined
                          : Icons.warning_amber_outlined,
                      size: 16,
                      color: f.calibrated
                          ? context.wealthColors.positiveText
                          : context.wealthColors.warningText,
                    ),
                    const SizedBox(width: AppSpacing.xs),
                    Flexible(
                      child: Text(
                        f.calibrated
                            ? l10n.fxCalibrated
                            : l10n.fxRequiresCalibration,
                      ),
                    ),
                  ],
                ),
                Text(
                  l10n.fxForecastInterval(
                    '${f.low80}',
                    '${f.high80}',
                    '${f.priceMedian}',
                  ),
                ),
                Text(
                  l10n.fxForecastModel(
                    f.modelName ?? '',
                    f.modelVersion ?? '',
                    DateLabels.dateTime(f.generatedAt!, locale: locale),
                  ),
                  style: context.wealthText.caption,
                ),
                if (f.statement != null)
                  Text(f.statement!, style: context.wealthText.caption),
              ],
              const SizedBox(height: AppSpacing.xs),
              Text(
                f.notice,
                style: context.wealthText.caption.copyWith(
                  color: context.wealthColors.textMuted,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// "0.5612" -> "56.12": the server's probability shown as a percentage.
  static String _percent(Decimal p) => (p * Decimal.fromInt(100)).toString();
}

class _Backtests extends ConsumerWidget {
  const _Backtests({required this.instrument});

  final String instrument;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return AsyncValueView(
      value: ref.watch(backtestsProvider(instrument)),
      onRetry: () => ref.invalidate(backtestsProvider(instrument)),
      isEmpty: (b) => b.isEmpty,
      empty: Text(l10n.fxBacktestNote),
      data: (rows) => WealthCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final b in rows) ...[
              Text(b.rule, style: context.wealthText.title),
              Text(
                l10n.fxBacktestRow(
                  '${b.trades}',
                  (b.oosReturn * Decimal.fromInt(100)).toString(),
                  b.profitFactor?.toString() ?? '—',
                ),
              ),
              if (!b.auditPassed) Text(l10n.fxAuditFailed),
              const SizedBox(height: AppSpacing.s),
            ],
            Text(l10n.fxBacktestNote, style: context.wealthText.caption),
          ],
        ),
      ),
    );
  }
}

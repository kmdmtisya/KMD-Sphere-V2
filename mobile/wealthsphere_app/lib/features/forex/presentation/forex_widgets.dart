import 'package:decimal/decimal.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/charts/chart_frame.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/formatting/formatting.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../data/forex_stream.dart';
import '../domain/forex_models.dart';

/// Shared pieces of the forex screens (P13-T11). They take plain values (no providers), so each
/// can be tested and shown in the gallery on its own.

String priceKindLabel(AppLocalizations l10n, PriceKind kind) => switch (kind) {
  PriceKind.simulated => l10n.fxKindSimulated,
  PriceKind.indicative => l10n.fxKindIndicative,
  PriceKind.delayed => l10n.fxKindDelayed,
  PriceKind.tradable => l10n.fxKindTradable,
  PriceKind.unknown => l10n.fxKindUnknown,
};

/// Always-visible PAPER TRADING label (QG-20.4, design section 11).
class PaperTradingBanner extends StatelessWidget {
  const PaperTradingBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    return Semantics(
      container: true,
      label: '${l10n.fxPaperTrading}. ${l10n.fxPaperTradingNote}',
      child: ExcludeSemantics(
        child: Container(
          width: double.infinity,
          padding: const EdgeInsetsDirectional.all(AppSpacing.s),
          decoration: BoxDecoration(
            color: colors.demoBadge,
            borderRadius: AppRadii.smallRadius,
          ),
          child: Row(
            children: [
              Icon(Icons.science_outlined, color: colors.onDemoBadge, size: 18),
              const SizedBox(width: AppSpacing.s),
              Expanded(
                child: Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: '${l10n.fxPaperTrading}  ',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      TextSpan(text: l10n.fxPaperTradingNote),
                    ],
                  ),
                  style: context.wealthText.caption.copyWith(
                    color: colors.onDemoBadge,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The price type, always shown next to a price: no price here is an executable quote.
class PriceKindChip extends StatelessWidget {
  const PriceKindChip({required this.kind, super.key});

  final PriceKind kind;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    return Tooltip(
      message: l10n.fxNotExecutable,
      child: Container(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: AppSpacing.xs,
          vertical: 2,
        ),
        decoration: BoxDecoration(
          border: Border.all(color: colors.border),
          borderRadius: AppRadii.smallRadius,
        ),
        child: Text(
          priceKindLabel(l10n, kind),
          style: context.wealthText.caption.copyWith(color: colors.textMuted),
        ),
      ),
    );
  }
}

/// A small outlined label, for example "DEMO event" on an item the server marks as demo data.
class ForexTagChip extends StatelessWidget {
  const ForexTagChip({required this.text, super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = context.wealthColors;
    return Container(
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: AppSpacing.xs,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: colors.demoBadge,
        borderRadius: AppRadii.smallRadius,
      ),
      child: Text(
        text,
        style: context.wealthText.caption.copyWith(color: colors.onDemoBadge),
      ),
    );
  }
}

/// One pair on the markets list. A stale or missing price says so instead of looking current.
class QuoteRow extends StatelessWidget {
  const QuoteRow({required this.quote, this.onTap, super.key});

  final ForexQuote quote;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final text = context.wealthText;
    final price = quote.mid?.toString();
    final status = switch (quote.freshness) {
      QuoteFreshness.fresh => null,
      QuoteFreshness.stale => l10n.fxStale,
      QuoteFreshness.unavailable => l10n.fxUnavailable,
    };
    return Semantics(
      button: onTap != null,
      label: l10n.fxPairSemantics(
        quote.label,
        status ?? price ?? l10n.fxUnavailable,
        priceKindLabel(l10n, quote.kind),
      ),
      child: ExcludeSemantics(
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsetsDirectional.symmetric(
              vertical: AppSpacing.s,
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(quote.label, style: text.title),
                      const SizedBox(height: 2),
                      PriceKindChip(kind: quote.kind),
                    ],
                  ),
                ),
                const SizedBox(width: AppSpacing.s),
                Flexible(
                  flex: 2,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      if (status != null)
                        StaleChip(label: status)
                      else ...[
                        Text(
                          price ?? '',
                          style: text.amount,
                          textAlign: TextAlign.end,
                        ),
                        if (quote.bid != null && quote.ask != null)
                          Text(
                            l10n.fxBidAsk('${quote.bid}', '${quote.ask}'),
                            style: text.caption.copyWith(
                              color: colors.textMuted,
                            ),
                            textAlign: TextAlign.end,
                          ),
                      ],
                      if (quote.ageSeconds != null)
                        Text(
                          l10n.fxAge('${quote.ageSeconds}'),
                          style: text.caption.copyWith(color: colors.textMuted),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The live stream's state. Hidden while live.
class StreamStateBanner extends StatelessWidget {
  const StreamStateBanner({required this.state, super.key});

  final StreamState state;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final message = switch (state) {
      StreamState.live || StreamState.idle => null,
      StreamState.connecting => l10n.fxStreamConnecting,
      StreamState.reconnecting => l10n.fxStreamReconnecting,
      StreamState.paused => l10n.fxStreamPaused,
      StreamState.stopped => l10n.fxStreamStopped,
    };
    if (message == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
      child: StatusBanner(icon: Icons.sync_problem_outlined, message: message),
    );
  }
}

/// Closing prices of a pair as a line, in a [ChartFrame] (accessible summary and a table).
/// Wrapped in a [RepaintBoundary] so stream updates elsewhere on the screen never redraw it.
class ForexPriceChart extends StatelessWidget {
  const ForexPriceChart({
    required this.pair,
    required this.candles,
    this.height = 200,
    super.key,
  });

  final String pair;
  final List<ForexCandle> candles;
  final double height;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final locale = context.formatLocale;
    final last = candles.isEmpty ? '' : '${candles.last.close}';
    return RepaintBoundary(
      child: ChartFrame(
        summary: l10n.fxChartSemantics(pair, '${candles.length}', last),
        height: height,
        isEmpty: candles.isEmpty,
        tableHeaders: [l10n.chartTableDate, l10n.chartTableValue],
        tableRows: [
          for (final c in candles)
            [DateLabels.dateTime(c.start, locale: locale), '${c.close}'],
        ],
        chart: candles.isEmpty
            ? const SizedBox.shrink()
            : LineChart(
                LineChartData(
                  gridData: FlGridData(
                    drawVerticalLine: false,
                    getDrawingHorizontalLine: (_) =>
                        FlLine(color: colors.chartGrid, strokeWidth: 1),
                  ),
                  titlesData: const FlTitlesData(show: false),
                  borderData: FlBorderData(show: false),
                  lineTouchData: const LineTouchData(enabled: false),
                  lineBarsData: [
                    LineChartBarData(
                      spots: [
                        for (var i = 0; i < candles.length; i++)
                          FlSpot(i.toDouble(), _plot(candles[i].close)),
                      ],
                      color: colors.chartGrowth,
                      barWidth: 2,
                      dotData: const FlDotData(show: false),
                    ),
                  ],
                ),
                duration: Duration.zero,
              ),
      ),
    );
  }

  /// Drawing only: a pixel position, never a figure shown or used in a calculation.
  static double _plot(Decimal value) => value.toDouble();
}

/// A titled block of short lines (warnings, disclosures, risks).
class LinesCard extends StatelessWidget {
  const LinesCard({
    required this.title,
    required this.lines,
    this.icon = Icons.info_outline,
    super.key,
  });

  final String title;
  final List<String> lines;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    if (lines.isEmpty) return const SizedBox.shrink();
    final text = context.wealthText;
    return WealthCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 18),
              const SizedBox(width: AppSpacing.s),
              Expanded(child: Text(title, style: text.title)),
            ],
          ),
          const SizedBox(height: AppSpacing.s),
          for (final l in lines)
            Padding(
              padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.xs),
              child: Text('• $l', style: text.body),
            ),
        ],
      ),
    );
  }
}

/// A heading inside a forex screen.
class ForexHeading extends StatelessWidget {
  const ForexHeading(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.only(
      top: AppSpacing.l,
      bottom: AppSpacing.s,
    ),
    child: Semantics(
      header: true,
      child: Text(text, style: context.wealthText.headline),
    ),
  );
}

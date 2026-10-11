import 'dart:math' as math;

import 'package:decimal/decimal.dart';
import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'cards.dart';
import 'context_locale.dart';

/// Where a goal stands under its stated assumptions. It is always an estimate.
enum GoalProgressStatus { onTrack, behind, reached }

/// A goal: a progress ring with its **number in the middle**, the name, target and date, and a
/// status shown as an icon **and** a word, never colour alone. The estimate wording is part of
/// the card, so a status is never presented as certain.
///
/// The percentage, status and amounts come from the backend (docs/design/goals.md); nothing is
/// calculated here.
class GoalProgressCard extends StatelessWidget {
  const GoalProgressCard({
    required this.name,
    required this.progressPercent,
    required this.status,
    required this.target,
    required this.targetDate,
    this.current,
    this.onTap,
    super.key,
  });

  final String name;

  /// 0 to 100 (percentage points); values outside are clamped for drawing.
  final Decimal progressPercent;
  final GoalProgressStatus status;
  final Money target;
  final DateTime targetDate;
  final Money? current;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    final percent = context.percentFormatter.format(
      progressPercent,
      fractionDigits: 0,
    );
    final (statusText, statusIcon, statusColor) = switch (status) {
      GoalProgressStatus.onTrack => (
        l10n.goalStatusOnTrack,
        Icons.check_circle_outline_rounded,
        colors.positiveText,
      ),
      GoalProgressStatus.behind => (
        l10n.goalStatusBehind,
        Icons.schedule_rounded,
        colors.warningText,
      ),
      GoalProgressStatus.reached => (
        l10n.goalStatusReached,
        Icons.flag_rounded,
        colors.positiveText,
      ),
    };
    final targetLine = l10n.goalCardTarget(
      context.moneyFormatter.format(target),
      DateLabels.date(targetDate, locale: context.formatLocale),
    );
    final nowLine = current == null
        ? null
        : l10n.goalCardNow(context.moneyFormatter.format(current!));
    final fraction = (progressPercent.toDouble() / 100).clamp(0.0, 1.0);

    return WealthCard(
      onTap: onTap,
      semanticLabel: [
        l10n.goalsProgressSpoken(name, percent, statusText),
        targetLine,
        ?nowLine,
        l10n.goalCardEstimate,
      ].join('. '),
      child: Row(
        children: [
          ExcludeSemantics(
            child: SizedBox.square(
              dimension: 72,
              child: CustomPaint(
                painter: _RingPainter(
                  fraction: fraction,
                  track: colors.divider,
                  progress: colors.primary,
                ),
                child: Center(child: Text(percent, style: text.label)),
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.m),
          Expanded(
            child: ExcludeSemantics(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: text.title),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(statusIcon, size: 16, color: statusColor),
                      const SizedBox(width: AppSpacing.xxs),
                      Flexible(
                        child: Text(
                          statusText,
                          style: text.label.copyWith(color: statusColor),
                        ),
                      ),
                    ],
                  ),
                  Text(
                    targetLine,
                    style: text.caption.copyWith(color: colors.textMuted),
                  ),
                  if (nowLine != null) Text(nowLine, style: text.body),
                  const SizedBox(height: AppSpacing.xxs),
                  Text(
                    l10n.goalCardEstimate,
                    style: text.caption.copyWith(color: colors.textMuted),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  const _RingPainter({
    required this.fraction,
    required this.track,
    required this.progress,
  });

  final double fraction;
  final Color track;
  final Color progress;

  static const double _stroke = 8;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final arc = rect.deflate(_stroke / 2);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = _stroke
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(arc, 0, math.pi * 2, false, paint..color = track);
    if (fraction > 0) {
      canvas.drawArc(
        arc,
        -math.pi / 2,
        math.pi * 2 * fraction,
        false,
        paint..color = progress,
      );
    }
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.fraction != fraction ||
      old.track != track ||
      old.progress != progress;
}

import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../theme/wealth_typography.dart';
import '../tokens/tokens.dart';
import 'context_locale.dart';
import 'data_as_of_label.dart';

/// Where a fact came from. All fields are plain text from the backend.
@immutable
class EvidenceSource {
  const EvidenceSource({
    required this.label,
    required this.provider,
    required this.asOf,
  });

  final String label;
  final String provider;
  final DateTime asOf;
}

/// A small chip naming the source of a figure or statement. Tapping opens a sheet with the source,
/// provider and when the data was current.
///
/// It deliberately has **no link**: content-supplied URLs are never opened from the app.
class EvidenceSourceChip extends StatelessWidget {
  const EvidenceSourceChip({required this.source, this.now, super.key});

  final EvidenceSource source;

  /// Injectable clock for tests.
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final colors = context.wealthColors;
    final asOf = dataAsOfText(
      l10n,
      source.asOf,
      now: now ?? DateTime.now(),
      locale: context.formatLocale,
    );
    return Semantics(
      button: true,
      label: l10n.evidenceSourceSpoken(source.label, source.provider, asOf),
      excludeSemantics: true,
      onTap: () => _open(context),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: AppTouchTarget.android),
        child: Center(
          widthFactor: 1,
          child: ActionChip(
            avatar: Icon(
              Icons.fact_check_outlined,
              size: 18,
              color: colors.textMuted,
            ),
            label: Text(source.label, overflow: TextOverflow.ellipsis),
            onPressed: () => _open(context),
          ),
        ),
      ),
    );
  }

  void _open(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (_) => _EvidenceSheet(source: source, now: now),
    );
  }
}

class _EvidenceSheet extends StatelessWidget {
  const _EvidenceSheet({required this.source, this.now});

  final EvidenceSource source;
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final colors = context.wealthColors;
    Widget row(String label, String value) => Padding(
      padding: const EdgeInsetsDirectional.only(bottom: AppSpacing.s),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: text.caption.copyWith(color: colors.textMuted)),
          Text(value, style: text.body),
        ],
      ),
    );

    return SafeArea(
      child: Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: AppSpacing.m,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.evidenceSheetTitle, style: text.title),
            const SizedBox(height: AppSpacing.m),
            row(l10n.evidenceSource, source.label),
            row(l10n.evidenceProvider, source.provider),
            DataAsOfLabel(asOf: source.asOf, now: now),
            const SizedBox(height: AppSpacing.m),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: Text(l10n.close),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

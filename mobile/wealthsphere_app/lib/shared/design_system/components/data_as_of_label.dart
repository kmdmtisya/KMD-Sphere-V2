import 'package:flutter/material.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../formatting/formatting.dart';
import '../theme/wealth_typography.dart';
import 'context_locale.dart';

/// The localised freshness text for [asOf]: "As of 2 hours ago", or "As of Mar 12, 2024" once the
/// data is a week old or the timestamp is in the future (bad data or clock skew).
String dataAsOfText(
  AppLocalizations l10n,
  DateTime asOf, {
  required DateTime now,
  required String locale,
}) {
  final age = RelativeAge.between(asOf, now: now);
  if (age.isFuture && age.unit != AgeUnit.justNow) {
    return l10n.asOfDate(DateLabels.dateTime(asOf, locale: locale));
  }
  return switch (age.unit) {
    AgeUnit.justNow => l10n.asOfJustNow,
    AgeUnit.minutes => l10n.asOfMinutes(age.value),
    AgeUnit.hours => l10n.asOfHours(age.value),
    AgeUnit.days => l10n.asOfDays(age.value),
    AgeUnit.older => l10n.asOfDate(DateLabels.date(asOf, locale: locale)),
  };
}

/// Shows when a figure was last updated. Every price, valuation and research item carries a
/// timestamp (provenance); this is how it is displayed. The full date and time are available on
/// long-press (tooltip) and to screen readers.
class DataAsOfLabel extends StatelessWidget {
  const DataAsOfLabel({required this.asOf, this.now, this.style, super.key});

  final DateTime asOf;

  /// Injectable clock for tests and previews; defaults to the current time.
  final DateTime? now;

  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final locale = context.formatLocale;
    final text = dataAsOfText(
      l10n,
      asOf,
      now: now ?? DateTime.now(),
      locale: locale,
    );
    final exact = DateLabels.dateTime(asOf, locale: locale);
    return Semantics(
      label: '$text, $exact',
      excludeSemantics: true,
      child: Tooltip(
        message: exact,
        excludeFromSemantics: true,
        child: Text(text, style: style ?? context.wealthText.caption),
      ),
    );
  }
}

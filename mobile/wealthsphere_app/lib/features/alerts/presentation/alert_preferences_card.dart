import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../application/alerts_providers.dart';
import '../data/alerts_repository.dart';
import '../domain/alert_models.dart';

/// What the user wants to be told about: all alerts, price alerts, allocation alerts. Turning one
/// off stops those alerts being checked; they stay as they are and nothing is queued.
class AlertPreferencesCard extends ConsumerWidget {
  const AlertPreferencesCard({super.key});

  Future<void> _save(
    BuildContext context,
    WidgetRef ref,
    AlertPreferences next,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final failed = AppLocalizations.of(context).alertSaveFailed;
    try {
      await ref.read(alertRepositoryProvider).savePreferences(next);
    } on Object {
      messenger.showSnackBar(SnackBar(content: Text(failed)));
    }
    ref.invalidate(alertPreferencesProvider);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return AsyncValueView<AlertPreferences>(
      value: ref.watch(alertPreferencesProvider),
      onRetry: () => ref.invalidate(alertPreferencesProvider),
      data: (p) => WealthCard(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            SwitchListTile(
              title: Text(l10n.alertPrefsAll),
              subtitle: Text(l10n.alertPrefsAllHelp),
              value: p.alertsEnabled,
              onChanged: (v) =>
                  unawaited(_save(context, ref, p.copyWith(alertsEnabled: v))),
            ),
            SwitchListTile(
              title: Text(l10n.alertPrefsPrice),
              value: p.priceAlertsEnabled,
              onChanged: p.alertsEnabled
                  ? (v) => unawaited(
                      _save(context, ref, p.copyWith(priceAlertsEnabled: v)),
                    )
                  : null,
            ),
            SwitchListTile(
              title: Text(l10n.alertPrefsAllocation),
              value: p.allocationAlertsEnabled,
              onChanged: p.alertsEnabled
                  ? (v) => unawaited(
                      _save(
                        context,
                        ref,
                        p.copyWith(allocationAlertsEnabled: v),
                      ),
                    )
                  : null,
            ),
          ],
        ),
      ),
    );
  }
}

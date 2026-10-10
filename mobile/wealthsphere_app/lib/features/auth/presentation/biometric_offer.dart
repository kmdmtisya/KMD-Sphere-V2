import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/preferences/preferences_store.dart';
import '../../../core/security/app_lock_settings.dart';
import '../../../core/security/device_authenticator.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/theme/wealth_typography.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../application/auth_flow.dart';

/// After the first sign-in on this device, asks once whether returning visits should unlock
/// with biometrics (the app lock). Turning it on needs a successful device check; "Not now" is
/// the user's explicit choice right after a full sign-in. On a device without a screen lock the
/// sheet explains what returning will require instead.
Future<void> offerBiometricsOnce(BuildContext context, WidgetRef ref) async {
  final store = ref.read(preferencesStoreProvider);
  if (await biometricOfferShown(store)) return;
  await markBiometricOfferShown(store);
  final device = ref.read(deviceAuthenticatorProvider);
  final available = await device.isAvailable();
  if (!context.mounted) return;
  final l10n = AppLocalizations.of(context);
  final accept = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (sheet) => _OfferSheet(available: available),
  );
  if (!available || accept == null) return;
  final settings = ref.read(appLockSettingsProvider.notifier);
  final current = ref.read(appLockSettingsProvider);
  if (accept) {
    final outcome = await device.authenticate(l10n.lockReason);
    if (outcome == UnlockOutcome.success) {
      await settings.set(current.copyWith(enabled: true));
    }
  } else {
    await settings.set(current.copyWith(enabled: false));
  }
}

class _OfferSheet extends StatelessWidget {
  const _OfferSheet({required this.available});

  final bool available;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsetsDirectional.fromSTEB(
          AppSpacing.m,
          0,
          AppSpacing.m,
          AppSpacing.m,
        ),
        child: Column(
          key: const ValueKey('biometric-offer'),
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ExcludeSemantics(
              child: Icon(
                available ? Icons.fingerprint : Icons.phonelink_lock,
                size: 48,
                color: context.wealthColors.primary,
              ),
            ),
            const SizedBox(height: AppSpacing.s),
            Semantics(
              header: true,
              child: Text(
                available
                    ? l10n.biometricOfferTitle
                    : l10n.biometricOfferNoDeviceTitle,
                style: context.wealthText.title,
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: AppSpacing.s),
            Text(
              available
                  ? l10n.biometricOfferBody
                  : l10n.biometricOfferNoDeviceBody,
              style: context.wealthText.body,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.m),
            if (available) ...[
              FilledButton(
                key: const ValueKey('biometric-accept'),
                onPressed: () => Navigator.of(context).pop(true),
                child: Text(l10n.biometricOfferAccept),
              ),
              const SizedBox(height: AppSpacing.xs),
              TextButton(
                key: const ValueKey('biometric-decline'),
                onPressed: () => Navigator.of(context).pop(false),
                child: Text(l10n.biometricOfferDecline),
              ),
            ] else
              FilledButton(
                key: const ValueKey('biometric-ok'),
                onPressed: () => Navigator.of(context).pop(),
                child: Text(l10n.biometricOfferOk),
              ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/security/app_lock_settings.dart';
import '../../../core/security/device_authenticator.dart';
import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/theme/wealth_typography.dart';
import '../../../shared/design_system/tokens/tokens.dart';

/// Whether this device can verify the user (biometrics or a screen lock).
final deviceCanAuthenticateProvider = FutureProvider.autoDispose<bool>(
  (ref) => ref.watch(deviceAuthenticatorProvider).isAvailable(),
);

/// App-lock switch and timeout. Changing either needs the device to verify the user first, so
/// someone holding an unlocked phone cannot quietly weaken the lock. On a device that cannot
/// verify anyone, the lock can only be turned off (it could never be unlocked).
class AppLockSettingsTile extends ConsumerWidget {
  const AppLockSettingsTile({super.key});

  Future<void> _change(
    BuildContext context,
    WidgetRef ref,
    AppLockSettings next, {
    required bool deviceAvailable,
  }) async {
    final current = ref.read(appLockSettingsProvider);
    final turningOffUnusableLock = !deviceAvailable && !next.enabled;
    if (!turningOffUnusableLock) {
      if (!deviceAvailable) return;
      final outcome = await ref
          .read(deviceAuthenticatorProvider)
          .authenticate(AppLocalizations.of(context).appLockConfirmReason);
      if (outcome != UnlockOutcome.success) return;
    }
    if (ref.read(appLockSettingsProvider) == current) {
      await ref.read(appLockSettingsProvider.notifier).set(next);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final settings = ref.watch(appLockSettingsProvider);
    final available = ref.watch(deviceCanAuthenticateProvider).value;
    final known = available != null;
    final canUse = available ?? false;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SwitchListTile(
          key: const ValueKey('app-lock-switch'),
          contentPadding: EdgeInsets.zero,
          title: Text(l10n.appLockSetting),
          subtitle: known && !canUse ? Text(l10n.appLockUnavailableHint) : null,
          value: settings.enabled,
          onChanged: !known || (!canUse && !settings.enabled)
              ? null
              : (on) => _change(
                  context,
                  ref,
                  settings.copyWith(enabled: on),
                  deviceAvailable: canUse,
                ),
        ),
        if (settings.enabled && canUse) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(l10n.appLockTimeoutLabel, style: context.wealthText.caption),
          const SizedBox(height: AppSpacing.xs),
          SegmentedButton<LockTimeout>(
            key: const ValueKey('app-lock-timeout'),
            showSelectedIcon: false,
            segments: [
              ButtonSegment(
                value: LockTimeout.immediately,
                label: Text(l10n.appLockImmediately),
              ),
              ButtonSegment(
                value: LockTimeout.oneMinute,
                label: Text(l10n.appLockOneMinute),
              ),
              ButtonSegment(
                value: LockTimeout.fiveMinutes,
                label: Text(l10n.appLockFiveMinutes),
              ),
            ],
            selected: {settings.timeout},
            onSelectionChanged: (s) => _change(
              context,
              ref,
              settings.copyWith(timeout: s.first),
              deviceAvailable: canUse,
            ),
          ),
        ],
      ],
    );
  }
}

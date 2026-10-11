import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../../../shared/design_system/components/components.dart';
import '../../../shared/design_system/theme/theme.dart';
import '../../../shared/design_system/tokens/tokens.dart';
import '../../account/presentation/account_section.dart';
import '../../account/presentation/app_lock_settings_tile.dart';

/// Settings: the account, appearance, app lock, and the preferences that are not available yet
/// (listed as "Coming soon" rather than hidden).
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final text = context.wealthText;
    final mode = ref.watch(themeModeProvider);
    final muted = text.caption.copyWith(color: context.wealthColors.textMuted);

    Widget heading(String label) => Padding(
      padding: const EdgeInsetsDirectional.only(
        top: AppSpacing.l,
        bottom: AppSpacing.xs,
      ),
      child: Semantics(header: true, child: Text(label, style: text.title)),
    );

    Widget soon(String label) => Semantics(
      container: true,
      label: l10n.moreComingSoonSpoken(label),
      excludeSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: AppTouchTarget.android),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              label,
              style: text.body.copyWith(color: context.wealthColors.textMuted),
            ),
            Text(l10n.moreComingSoon, style: muted),
          ],
        ),
      ),
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.moreSettings),
        actions: const [
          DemoBadge(),
          SizedBox(width: AppSpacing.m),
        ],
      ),
      body: ListView(
        padding: const EdgeInsetsDirectional.all(AppSpacing.m),
        children: [
          const AccountSection(),
          heading(l10n.settingsAppearance),
          SegmentedButton<ThemeMode>(
            segments: [
              ButtonSegment(
                value: ThemeMode.system,
                label: Text(l10n.themeSystem),
                icon: const Icon(Icons.brightness_auto),
              ),
              ButtonSegment(
                value: ThemeMode.light,
                label: Text(l10n.themeLight),
                icon: const Icon(Icons.light_mode),
              ),
              ButtonSegment(
                value: ThemeMode.dark,
                label: Text(l10n.themeDark),
                icon: const Icon(Icons.dark_mode),
              ),
            ],
            selected: {mode},
            onSelectionChanged: (selection) =>
                ref.read(themeModeProvider.notifier).setMode(selection.first),
          ),
          heading(l10n.settingsSecurity),
          const AppLockSettingsTile(),
          heading(l10n.settingsPreferences),
          soon(l10n.settingsCurrency),
          soon(l10n.settingsNotifications),
          heading(l10n.settingsAbout),
          Text(l10n.settingsAboutBody, style: text.body),
          const SizedBox(height: AppSpacing.xs),
          Text(l10n.settingsDemoBuild, style: muted),
        ],
      ),
    );
  }
}

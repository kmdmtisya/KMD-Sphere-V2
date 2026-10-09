import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../l10n/generated/app_localizations.dart';
import '../shared/design_system/theme/theme.dart';
import '../shared/design_system/tokens/tokens.dart';

/// Central route table. The five-tab shell replaces this placeholder in P02-T07.
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => const _PlaceholderScreen(),
      ),
    ],
  );
});

/// Temporary home screen: shows the brand text and a theme-mode switch so the light/dark/system
/// themes can be checked on a device. Replaced by the real shell and the Settings screen.
class _PlaceholderScreen extends ConsumerWidget {
  const _PlaceholderScreen();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final mode = ref.watch(themeModeProvider);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.appTitle)),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsetsDirectional.all(AppSpacing.l),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(l10n.appTagline, style: context.wealthText.title),
              const SizedBox(height: AppSpacing.xs),
              Text(
                l10n.placeholderBody,
                style: context.wealthText.body,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.xl),
              Text(l10n.themeLabel, style: context.wealthText.caption),
              const SizedBox(height: AppSpacing.xs),
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
                onSelectionChanged: (selection) => ref
                    .read(themeModeProvider.notifier)
                    .setMode(selection.first),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/account/presentation/account_section.dart';
import '../l10n/generated/app_localizations.dart';
import '../shared/design_system/components/components.dart';
import '../shared/design_system/theme/theme.dart';
import '../shared/design_system/tokens/tokens.dart';
import 'app_routes.dart';

/// Temporary screens for every route. Each is replaced by its real feature screen in P03 and P07
/// (see the registry in `router.dart`); they exist so the navigation shell, deep links and back
/// behaviour can be built and tested first.
class _PlaceholderPage extends StatelessWidget {
  const _PlaceholderPage({
    required this.title,
    required this.children,
    this.showBackButton = false,
  });

  final String title;
  final List<Widget> children;
  final bool showBackButton;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        automaticallyImplyLeading: showBackButton,
        actions: const [
          Padding(
            padding: EdgeInsetsDirectional.only(end: AppSpacing.m),
            child: Center(child: DemoBadge()),
          ),
        ],
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsetsDirectional.all(AppSpacing.l),
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: AppBreakpoints.maxContentWidth,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: children,
            ),
          ),
        ),
      ),
    );
  }
}

Widget _comingSoon(BuildContext context) => Text(
  AppLocalizations.of(context).comingSoon,
  style: context.wealthText.body,
  textAlign: TextAlign.center,
);

class HomePlaceholder extends StatelessWidget {
  const HomePlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _PlaceholderPage(
      title: l10n.appTitle,
      children: [
        Text(
          l10n.appTagline,
          style: context.wealthText.title,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          l10n.placeholderBody,
          style: context.wealthText.body,
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

class PortfolioPlaceholder extends StatelessWidget {
  const PortfolioPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _PlaceholderPage(
      title: l10n.tabPortfolio,
      children: [
        _comingSoon(context),
        const SizedBox(height: AppSpacing.l),
        OutlinedButton(
          onPressed: () => context.push(AppRoutes.holdings),
          child: Text(l10n.holdingsTitle),
        ),
      ],
    );
  }
}

class HoldingsPlaceholder extends StatelessWidget {
  const HoldingsPlaceholder({super.key});

  @override
  Widget build(BuildContext context) => _PlaceholderPage(
    title: AppLocalizations.of(context).holdingsTitle,
    showBackButton: true,
    children: [_comingSoon(context)],
  );
}

class AiPlaceholder extends StatelessWidget {
  const AiPlaceholder({this.scope, super.key});

  /// Parsed from the `scope` query parameter; null when absent or invalid.
  final AiScope? scope;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _PlaceholderPage(
      title: l10n.tabAiWealth,
      children: [
        if (scope != null) ...[
          Chip(label: Text(l10n.aiContextLabel(scope!.encoded))),
          const SizedBox(height: AppSpacing.m),
        ],
        _comingSoon(context),
      ],
    );
  }
}

class GoalsPlaceholder extends StatelessWidget {
  const GoalsPlaceholder({super.key});

  @override
  Widget build(BuildContext context) => _PlaceholderPage(
    title: AppLocalizations.of(context).tabGoals,
    children: [_comingSoon(context)],
  );
}

/// The More tab. Hosts the temporary theme switch until the real Settings screen exists.
class MorePlaceholder extends ConsumerWidget {
  const MorePlaceholder({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final mode = ref.watch(themeModeProvider);
    return _PlaceholderPage(
      title: l10n.tabMore,
      children: [
        const AccountSection(),
        const SizedBox(height: AppSpacing.l),
        OutlinedButton(
          onPressed: () => context.push(AppRoutes.calculator),
          child: Text(l10n.moreCalculator),
        ),
        if (kDebugMode) ...[
          const SizedBox(height: AppSpacing.s),
          OutlinedButton(
            onPressed: () => context.push(AppRoutes.gallery),
            child: const Text('Component gallery (debug)'),
          ),
        ],
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
          onSelectionChanged: (selection) =>
              ref.read(themeModeProvider.notifier).setMode(selection.first),
        ),
      ],
    );
  }
}

class CalculatorPlaceholder extends StatelessWidget {
  const CalculatorPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return _PlaceholderPage(
      title: l10n.calculatorTitle,
      showBackButton: true,
      children: [
        _comingSoon(context),
        const SizedBox(height: AppSpacing.l),
        OutlinedButton(
          onPressed: () => context.push(AppRoutes.forecast),
          child: Text(l10n.forecastTitle),
        ),
      ],
    );
  }
}

class ForecastPlaceholder extends StatelessWidget {
  const ForecastPlaceholder({super.key});

  @override
  Widget build(BuildContext context) => _PlaceholderPage(
    title: AppLocalizations.of(context).forecastTitle,
    showBackButton: true,
    children: [_comingSoon(context)],
  );
}

/// Shown for any unknown path (a stale deep link or notification).
class NotFoundScreen extends StatelessWidget {
  const NotFoundScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.notFoundTitle)),
      body: EmptyState(
        icon: Icons.explore_off_outlined,
        title: l10n.notFoundTitle,
        message: l10n.notFoundBody,
        actionLabel: l10n.goHome,
        onAction: () => context.go(AppRoutes.home),
      ),
    );
  }
}

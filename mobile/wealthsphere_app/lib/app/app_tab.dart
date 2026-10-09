import 'package:flutter/material.dart';

import '../l10n/generated/app_localizations.dart';
import '../shared/design_system/components/wealth_bottom_nav.dart';
import 'app_routes.dart';

/// The five primary tabs, in navigation order (ADR-0002).
enum AppTab {
  home(AppRoutes.home, Icons.home_outlined, Icons.home_rounded),
  portfolio(
    AppRoutes.portfolio,
    Icons.pie_chart_outline_rounded,
    Icons.pie_chart_rounded,
  ),
  ai(AppRoutes.ai, Icons.auto_awesome_outlined, Icons.auto_awesome_rounded),
  goals(AppRoutes.goals, Icons.flag_outlined, Icons.flag_rounded),
  more(AppRoutes.more, Icons.menu_rounded, Icons.menu_open_rounded);

  const AppTab(this.path, this.icon, this.selectedIcon);

  /// Root path of the tab's navigation stack.
  final String path;
  final IconData icon;
  final IconData selectedIcon;

  String label(AppLocalizations l10n) => switch (this) {
    AppTab.home => l10n.tabHome,
    AppTab.portfolio => l10n.tabPortfolio,
    AppTab.ai => l10n.tabAiWealth,
    AppTab.goals => l10n.tabGoals,
    AppTab.more => l10n.tabMore,
  };

  WealthNavDestination destination(AppLocalizations l10n) =>
      WealthNavDestination(
        icon: icon,
        selectedIcon: selectedIcon,
        label: label(l10n),
      );
}

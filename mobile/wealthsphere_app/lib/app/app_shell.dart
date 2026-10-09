import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../l10n/generated/app_localizations.dart';
import '../shared/design_system/components/wealth_bottom_nav.dart';
import 'app_tab.dart';

/// The frame around the five tabs: the active tab's navigator above the bottom navigation.
///
/// Each tab keeps its own back stack (indexed stack), so switching tabs never loses where the
/// user was. Re-tapping the active tab returns it to its root screen.
class AppShell extends StatelessWidget {
  const AppShell({required this.navigationShell, super.key});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: WealthBottomNav(
        destinations: [for (final tab in AppTab.values) tab.destination(l10n)],
        selectedIndex: navigationShell.currentIndex,
        onSelected: (index) => navigationShell.goBranch(index),
        onReselected: (index) =>
            navigationShell.goBranch(index, initialLocation: true),
      ),
    );
  }
}

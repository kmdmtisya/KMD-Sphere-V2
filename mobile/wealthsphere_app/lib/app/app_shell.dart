import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/offline/connectivity_banner.dart';
import '../l10n/generated/app_localizations.dart';
import '../shared/design_system/components/wealth_bottom_nav.dart';
import 'app_tab.dart';

/// The frame around the five tabs: the active tab's navigator above the bottom navigation.
///
/// Each tab keeps its own back stack (indexed stack), so switching tabs never loses where the
/// user was. Re-tapping the active tab returns it to its root screen.
class AppShell extends ConsumerWidget {
  const AppShell({required this.navigationShell, super.key});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      body: connectivityBannerVisible(ref)
          ? Column(
              children: [
                // Says when the app is offline and showing saved data (P09-T06).
                const SafeArea(bottom: false, child: ConnectivityBanner()),
                Expanded(
                  // The banner took the status-bar inset; the tab must not add it again.
                  child: MediaQuery.removePadding(
                    context: context,
                    removeTop: true,
                    child: navigationShell,
                  ),
                ),
              ],
            )
          : navigationShell,
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

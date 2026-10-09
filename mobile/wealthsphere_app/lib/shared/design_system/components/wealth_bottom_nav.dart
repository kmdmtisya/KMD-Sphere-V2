import 'package:flutter/material.dart';

/// One destination of the bottom navigation.
@immutable
class WealthNavDestination {
  const WealthNavDestination({
    required this.icon,
    required this.selectedIcon,
    required this.label,
  });

  final IconData icon;
  final IconData selectedIcon;
  final String label;
}

/// The primary bottom navigation (`Home | Portfolio | AI Wealth | Goals | More`).
///
/// - Labels are always visible (icons alone are not an accessible cue).
/// - The selected destination is announced as selected, and has a filled icon and an indicator.
/// - Re-tapping the active destination calls [onReselected] so the app can return that tab to its
///   root; tapping another calls [onSelected].
/// - Safe areas, 48 dp targets and text scaling come from the themed `NavigationBar`.
class WealthBottomNav extends StatelessWidget {
  const WealthBottomNav({
    required this.destinations,
    required this.selectedIndex,
    required this.onSelected,
    this.onReselected,
    super.key,
  }) : assert(
         destinations.length >= 2,
         'A navigation bar needs at least two destinations',
       );

  final List<WealthNavDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelected;
  final ValueChanged<int>? onReselected;

  @override
  Widget build(BuildContext context) {
    return NavigationBar(
      selectedIndex: selectedIndex,
      onDestinationSelected: (index) {
        if (index == selectedIndex) {
          onReselected?.call(index);
        } else {
          onSelected(index);
        }
      },
      destinations: [
        for (final d in destinations)
          NavigationDestination(
            icon: Icon(d.icon),
            selectedIcon: Icon(d.selectedIcon),
            label: d.label,
          ),
      ],
    );
  }
}

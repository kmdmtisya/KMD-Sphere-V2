import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/calculator/presentation/calculator_screen.dart';
import '../features/calculator/presentation/forecast/forecast_screen.dart';
import '../features/dashboard/presentation/home_screen.dart';
import '../features/portfolios/presentation/portfolio_overview_screen.dart';
import 'app_routes.dart';
import 'app_shell.dart';
import 'app_tab.dart';
import 'gallery/gallery_screen.dart';
import 'placeholder_screens.dart';

/// The route registry.
///
/// **Contract for features:** every tab owns a root route plus any nested routes, listed in
/// [tabRoutes]. A feature replaces its placeholder by changing only its own entry here (its
/// screens live in `features/<name>/presentation`). Paths come from [AppRoutes]; widgets navigate
/// with those constants and never build path strings.
final Map<AppTab, RouteBase Function()> tabRoutes =
    <AppTab, RouteBase Function()>{
      AppTab.home: () => GoRoute(
        path: AppRoutes.home,
        builder: (context, state) => const HomeScreen(),
      ),
      AppTab.portfolio: () => GoRoute(
        path: AppRoutes.portfolio,
        builder: (context, state) => const PortfolioOverviewScreen(),
        routes: [
          GoRoute(
            path: 'holdings',
            builder: (context, state) => const HoldingsPlaceholder(),
          ),
        ],
      ),
      AppTab.ai: () => GoRoute(
        path: AppRoutes.ai,
        builder: (context, state) => AiPlaceholder(
          scope: AiScope.tryParse(
            state.uri.queryParameters[AppRoutes.aiScopeParam],
          ),
        ),
      ),
      AppTab.goals: () => GoRoute(
        path: AppRoutes.goals,
        builder: (context, state) => const GoalsPlaceholder(),
      ),
      AppTab.more: () => GoRoute(
        path: AppRoutes.more,
        builder: (context, state) => const MorePlaceholder(),
        routes: [
          GoRoute(
            path: 'calculator',
            builder: (context, state) => const CalculatorScreen(),
            routes: [
              GoRoute(
                path: 'forecast',
                builder: (context, state) => const ForecastScreen(),
              ),
            ],
          ),
        ],
      ),
    };

/// Builds the app router. Exposed as a function so tests can start at any location.
GoRouter createRouter({
  String initialLocation = AppRoutes.home,
  bool enableGallery = kDebugMode,
}) {
  return GoRouter(
    initialLocation: initialLocation,
    // The bare host opens Home.
    redirect: (context, state) => state.uri.path == '/' ? AppRoutes.home : null,
    errorBuilder: (context, state) => const NotFoundScreen(),
    routes: [
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            AppShell(navigationShell: navigationShell),
        branches: [
          for (final tab in AppTab.values)
            StatefulShellBranch(routes: [tabRoutes[tab]!()]),
        ],
      ),
      if (enableGallery)
        GoRoute(
          path: AppRoutes.gallery,
          builder: (context, state) => const GalleryScreen(),
        ),
    ],
  );
}

final routerProvider = Provider<GoRouter>((ref) {
  final router = createRouter();
  ref.onDispose(router.dispose);
  return router;
});

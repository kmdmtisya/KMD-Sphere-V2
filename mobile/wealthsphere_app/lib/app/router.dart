import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/ai_wealth/doctor/presentation/doctor_screen.dart';
import '../features/ai_wealth/opportunities/presentation/compare_screen.dart';
import '../features/ai_wealth/opportunities/presentation/opportunities_screen.dart';
import '../features/ai_wealth/presentation/ai_wealth_screen.dart';
import '../features/auth/application/auth_flow.dart';
import '../features/auth/presentation/sign_in_screen.dart';
import '../features/auth/presentation/welcome_screen.dart';
import '../features/calculator/presentation/calculator_screen.dart';
import '../features/calculator/presentation/forecast/forecast_screen.dart';
import '../features/dashboard/presentation/home_screen.dart';
import '../features/goals/presentation/goal_detail_screen.dart';
import '../features/goals/presentation/goal_form_screen.dart';
import '../features/goals/presentation/goals_screen.dart';
import '../features/investments/presentation/investment_detail_screen.dart';
import '../features/more/presentation/income_screen.dart';
import '../features/more/presentation/more_screen.dart';
import '../features/more/presentation/net_worth_screen.dart';
import '../features/more/presentation/settings_screen.dart';
import '../features/portfolios/presentation/holdings_screen.dart';
import '../features/portfolios/presentation/portfolio_overview_screen.dart';
import '../features/transactions/domain/ledger_entry.dart';
import '../features/transactions/presentation/add_transaction_screen.dart';
import '../features/transactions/presentation/transaction_detail_screen.dart';
import '../features/transactions/presentation/transactions_screen.dart';
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
            builder: (context, state) => HoldingsScreen(
              onOpen: (holding) =>
                  context.go(AppRoutes.investment(holding.symbol)),
            ),
            routes: [
              GoRoute(
                path: ':symbol',
                builder: (context, state) => InvestmentDetailScreen(
                  symbol: state.pathParameters['symbol']!,
                  // Pushed, so Back returns to this investment (not the whole ledger).
                  onOpenTransaction: (entry) =>
                      context.push(AppRoutes.transaction(entry.id)),
                ),
              ),
            ],
          ),
          GoRoute(
            path: 'transactions',
            builder: (context, state) => TransactionsScreen(
              onOpen: (entry) => context.go(AppRoutes.transaction(entry.id)),
              onAdd: () => context.go(AppRoutes.addTransaction),
            ),
            routes: [
              // Registered before ':id' so "add" is never read as an entry id.
              GoRoute(
                path: 'add',
                builder: (context, state) => AddTransactionScreen(
                  correctionOf: state.extra is LedgerEntry
                      ? state.extra! as LedgerEntry
                      : null,
                  onOpenEntry: (id) => context.go(AppRoutes.transaction(id)),
                  onDone: () => context.go(AppRoutes.transactions),
                ),
              ),
              GoRoute(
                path: ':id',
                builder: (context, state) => TransactionDetailScreen(
                  entryId: state.pathParameters['id']!,
                  // Pushed, so Back returns to the entry the user came from.
                  onOpenEntry: (id) => context.push(AppRoutes.transaction(id)),
                  onAddCorrected: (entry) =>
                      context.go(AppRoutes.addTransaction, extra: entry),
                ),
              ),
            ],
          ),
        ],
      ),
      AppTab.ai: () => GoRoute(
        path: AppRoutes.ai,
        builder: (context, state) => AiWealthScreen(
          scope: AiScope.tryParse(
            state.uri.queryParameters[AppRoutes.aiScopeParam],
          ),
          onOpenDoctor: () => context.go(AppRoutes.doctor),
          onOpenOpportunities: () => context.go(AppRoutes.opportunities),
        ),
        routes: [
          GoRoute(
            path: 'opportunities',
            builder: (context, state) => OpportunitiesScreen(
              onCompare: () => context.go(AppRoutes.compareOpportunities),
              onSimulated: () => context.go(AppRoutes.calculator),
            ),
            routes: [
              GoRoute(
                path: 'compare',
                builder: (context, state) => CompareScreen(
                  onBack: () => context.go(AppRoutes.opportunities),
                ),
              ),
            ],
          ),
          GoRoute(
            path: 'doctor',
            builder: (context, state) => DoctorScreen(
              onAskAi: (portfolioId) => context.go(
                AppRoutes.aiWith(AiScope(AiScopeKind.portfolio, portfolioId)),
              ),
            ),
          ),
        ],
      ),
      AppTab.goals: () => GoRoute(
        path: AppRoutes.goals,
        builder: (context, state) => GoalsScreen(
          onOpen: (entry) => context.go(AppRoutes.goal(entry.goal.id)),
          onAdd: () => context.go(AppRoutes.addGoal),
        ),
        routes: [
          // Registered before ':id' so "add" is never read as a goal id.
          GoRoute(
            path: 'add',
            builder: (context, state) => GoalFormScreen(
              onSaved: (entry) => context.go(AppRoutes.goal(entry.goal.id)),
            ),
          ),
          GoRoute(
            path: ':id',
            builder: (context, state) => GoalDetailScreen(
              goalId: state.pathParameters['id']!,
              onEdit: (goal) => context.go(AppRoutes.editGoal(goal.id)),
              onAskAi: (goal) => context.go(
                AppRoutes.aiWith(AiScope(AiScopeKind.goal, goal.id)),
              ),
            ),
            routes: [
              GoRoute(
                path: 'edit',
                builder: (context, state) => GoalFormScreen(
                  goalId: state.pathParameters['id'],
                  onSaved: (entry) => context.go(AppRoutes.goal(entry.goal.id)),
                ),
              ),
            ],
          ),
        ],
      ),
      AppTab.more: () => GoRoute(
        path: AppRoutes.more,
        builder: (context, state) => MoreScreen(
          onOpenNetWorth: () => context.go(AppRoutes.netWorth),
          onOpenIncome: () => context.go(AppRoutes.income),
          onOpenCalculator: () => context.go(AppRoutes.calculator),
          onOpenSettings: () => context.go(AppRoutes.settings),
          onOpenGallery: () => context.push(AppRoutes.gallery),
        ),
        routes: [
          GoRoute(
            path: 'net-worth',
            builder: (context, state) => const NetWorthScreen(),
          ),
          GoRoute(
            path: 'income',
            builder: (context, state) => const IncomeScreen(),
          ),
          GoRoute(
            path: 'settings',
            builder: (context, state) => const SettingsScreen(),
          ),
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
      GoRoute(
        path: AppRoutes.welcome,
        builder: (context, state) => const WelcomeScreen(),
      ),
      GoRoute(
        path: AppRoutes.signIn,
        builder: (context, state) => const SignInScreen(),
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
  // First launch starts with the introduction (screen 1).
  final router = createRouter(
    initialLocation: ref.read(initialOnboardingCompleteProvider)
        ? AppRoutes.home
        : AppRoutes.welcome,
  );
  ref.onDispose(router.dispose);
  return router;
});

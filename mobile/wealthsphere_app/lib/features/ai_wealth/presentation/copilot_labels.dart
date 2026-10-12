import '../../../l10n/generated/app_localizations.dart';

/// The server names data tools by id (`get_net_worth`). These are the words the user sees.
String toolName(AppLocalizations l10n, String tool) => switch (tool) {
  'get_portfolio_summary' => l10n.aiToolNameSummary,
  'get_portfolio_allocation' => l10n.aiToolNameAllocation,
  'get_portfolio_performance' => l10n.aiToolNamePerformance,
  'get_net_worth' => l10n.aiToolNameNetWorth,
  'get_goal_progress' => l10n.aiToolNameGoals,
  'run_compound_forecast' => l10n.aiToolNameForecast,
  'run_goal_forecast' => l10n.aiToolNameGoalForecast,
  _ => l10n.aiToolNameOther,
};

/// An evidence chip label: a tool id becomes its name; anything else (the demo's own labels) is
/// shown as received.
String sourceLabel(AppLocalizations l10n, String label) => switch (label) {
  'get_portfolio_summary' => l10n.aiSourceSummary,
  'get_portfolio_allocation' => l10n.aiSourceAllocation,
  'get_portfolio_performance' => l10n.aiSourcePerformance,
  'get_net_worth' => l10n.aiSourceNetWorth,
  'get_goal_progress' => l10n.aiSourceGoals,
  'run_compound_forecast' => l10n.aiSourceForecast,
  'run_goal_forecast' => l10n.aiSourceGoalForecast,
  _ when _toolId.hasMatch(label) => l10n.aiSourceOther,
  _ => label,
};

final _toolId = RegExp(r'^[a-z]+(_[a-z]+)+$');

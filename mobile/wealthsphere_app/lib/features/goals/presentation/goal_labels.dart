import '../../../l10n/generated/app_localizations.dart';
import '../../calculator/presentation/calculator_screen.dart' show issueMessage;
import '../../forecast/domain/forecast_models.dart';
import '../application/goal_form.dart';
import '../domain/goal_models.dart';

String goalTypeLabel(AppLocalizations l10n, GoalType type) => switch (type) {
  GoalType.wealth => l10n.goalTypeWealth,
  GoalType.retirement => l10n.goalTypeRetirement,
  GoalType.education => l10n.goalTypeEducation,
  GoalType.houseDeposit => l10n.goalTypeHouseDeposit,
  GoalType.businessCapital => l10n.goalTypeBusinessCapital,
  GoalType.custom => l10n.goalTypeCustom,
};

/// "per month", "per quarter" or "per year".
String goalPeriodLabel(AppLocalizations l10n, Frequency f) => switch (f) {
  Frequency.monthly => l10n.goalPeriodMonthly,
  Frequency.quarterly => l10n.goalPeriodQuarterly,
  Frequency.yearly => l10n.goalPeriodYearly,
};

String scenarioLabel(AppLocalizations l10n, String kind) => switch (kind) {
  'conservative' => l10n.goalScenarioConservative,
  'growth' => l10n.goalScenarioGrowth,
  _ => l10n.goalScenarioBase,
};

/// The sentence for a problem with a goal form field.
String goalIssueText(AppLocalizations l10n, GoalIssue issue, String locale) =>
    switch (issue.kind) {
      GoalIssueKind.input => issueMessage(l10n, issue.input!, locale),
      GoalIssueKind.nameRequired => l10n.goalErrNameRequired,
      GoalIssueKind.nameTooLong => l10n.goalErrNameTooLong,
      GoalIssueKind.nameTaken => l10n.goalErrNameTaken,
      GoalIssueKind.dateRequired => l10n.goalErrDateRequired,
      GoalIssueKind.datePast => l10n.goalErrDatePast,
      GoalIssueKind.dateTooFar => l10n.goalErrDateTooFar,
    };

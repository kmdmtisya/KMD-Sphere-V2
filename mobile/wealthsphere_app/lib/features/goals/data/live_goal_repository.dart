import '../../../core/network/api_exception.dart';
import '../../../core/network/live_repository.dart';
import '../application/goal_form.dart';
import '../domain/goal_models.dart';
import 'goal_repository.dart';

/// Goals from the API. A goal's figures (progress, gap, scenarios, status, the assumption notice)
/// come from `GET /goals/{id}/progress`; the app never projects a goal itself. When the server
/// cannot measure a goal (for example its portfolio is archived) the goal is shown without
/// figures, as the screens already do for goals that have none.
class LiveGoalRepository extends LiveRepository implements GoalRepository {
  const LiveGoalRepository(super.dio);

  @override
  Future<List<GoalEntry>> goals() async {
    final list = await getList('/api/v1/goals', Goal.fromJson);
    final entries = await Future.wait(list.map(_withFigures));
    return entries
      ..sort((a, b) => a.goal.targetDate.compareTo(b.goal.targetDate));
  }

  @override
  Future<GoalEntry> goal(String id) async {
    final Goal goal;
    try {
      goal = await getObjectWithEtag(
        '/api/v1/goals/$id',
        (json, etag) => Goal.fromJson(json, etag: etag),
      );
    } on ApiException catch (e) {
      if (e.kind == ApiErrorKind.notFound) {
        throw const GoalRuleException(GoalRule.notFound);
      }
      rethrow;
    }
    return _withFigures(goal);
  }

  @override
  Future<GoalEntry> create(GoalInput input) => _ruled(() async {
    final goal = await send(
      'POST',
      '/api/v1/goals',
      Goal.fromJson,
      body: toApi(input),
    );
    return _withFigures(goal);
  });

  @override
  Future<GoalEntry> update(String id, GoalInput input, {String? ifMatch}) =>
      _ruled(() async {
        final goal = await send(
          'PATCH',
          '/api/v1/goals/$id',
          Goal.fromJson,
          body: toApi(input),
          ifMatch: ifMatch,
        );
        return _withFigures(goal);
      });

  Future<GoalEntry> _withFigures(Goal goal) async {
    try {
      final figures = await getObject(
        '/api/v1/goals/${goal.id}/progress',
        GoalFigures.fromJson,
      );
      return GoalEntry(goal: goal, figures: figures);
    } on ApiException catch (e) {
      // The goal exists but cannot be measured now: show it without figures. Anything that is
      // not about this goal (offline, signed out) is the screen's error to show.
      if (e.kind == ApiErrorKind.validation ||
          e.kind == ApiErrorKind.notFound) {
        return GoalEntry(goal: goal);
      }
      rethrow;
    }
  }

  /// The server's refusals in the form's own terms.
  Future<T> _ruled<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on ApiException catch (e) {
      if (e.kind == ApiErrorKind.notFound) {
        throw const GoalRuleException(GoalRule.notFound);
      }
      if (e.status == 409) {
        if ((e.detail ?? '').contains('changed somewhere else')) {
          throw const GoalRuleException(GoalRule.changedElsewhere);
        }
        final tooMany = (e.detail ?? '').contains('at most');
        throw GoalRuleException(
          tooMany ? GoalRule.tooMany : GoalRule.nameTaken,
        );
      }
      rethrow;
    }
  }

  /// The request body for [input]: amounts and rates as strings (ADR-0003).
  static Map<String, Object?> toApi(GoalInput input) {
    final a = input.assumptions;
    final d = input.targetDate;
    return {
      'name': input.name,
      'goal_type': input.type.apiName,
      'target': input.target.toJson(),
      'target_date':
          '${d.year.toString().padLeft(4, '0')}-'
          '${d.month.toString().padLeft(2, '0')}-'
          '${d.day.toString().padLeft(2, '0')}',
      'target_in_todays_money': input.targetInTodaysMoney,
      'portfolio_id': input.portfolioId,
      'assumptions': {
        'contribution': a.contribution.toJson(),
        'contribution_frequency': a.contributionFrequency.name,
        'contribution_growth_percent': a.contributionGrowthPercent.toString(),
        'inflation_percent': a.inflationPercent.toString(),
        'annual_fee_percent': a.annualFeePercent.toString(),
        'returns': {
          'base': a.baseReturnPercent.toString(),
          'conservative': ?a.conservativeReturnPercent?.toString(),
          'growth': ?a.growthReturnPercent?.toString(),
        },
      },
    };
  }
}

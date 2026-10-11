import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/data/demo_support.dart';
import '../../../core/data/json_reader.dart';
import '../application/goal_form.dart';
import '../domain/goal_models.dart';

/// Why a goal could not be saved.
enum GoalRule { notFound, nameTaken, tooMany }

class GoalRuleException implements Exception {
  const GoalRuleException(this.rule);

  final GoalRule rule;

  @override
  String toString() => 'GoalRuleException: $rule';
}

/// The most goals one user can have (docs/design/goals.md).
const int maxGoals = 50;

abstract interface class GoalRepository {
  Future<List<GoalEntry>> goals();
  Future<GoalEntry> goal(String id);
  Future<GoalEntry> create(GoalInput input);
  Future<GoalEntry> update(String id, GoalInput input);
}

/// Reads `assets/demo/goals.json`. Goals that are added or changed live in memory for the
/// session only. The demo cannot calculate a goal's figures (that is the backend's job), so an
/// added or changed goal has none and the screens say so instead of inventing them.
class DemoGoalRepository implements GoalRepository {
  DemoGoalRepository(this._assets, this._gate);

  final DemoAssets _assets;
  final Future<void> Function() _gate;
  final Map<String, GoalEntry> _changed = {};
  final List<GoalEntry> _created = [];
  int _counter = 0;

  Future<List<GoalEntry>> _all() async {
    await _gate();
    final doc = JsonReader(await _assets.load('goals.json'));
    final base = doc.list('goals', GoalEntry.fromJson);
    return [
      for (final e in base) _changed[e.goal.id] ?? e,
      for (final e in _created) _changed[e.goal.id] ?? e,
    ];
  }

  @override
  Future<List<GoalEntry>> goals() async {
    final all = await _all();
    return [...all]
      ..sort((a, b) => a.goal.targetDate.compareTo(b.goal.targetDate));
  }

  @override
  Future<GoalEntry> goal(String id) async {
    final found = (await _all()).where((e) => e.goal.id == id).firstOrNull;
    if (found == null) throw const GoalRuleException(GoalRule.notFound);
    return found;
  }

  Goal _build(String id, GoalInput i) => Goal(
    id: id,
    name: i.name,
    type: i.type,
    target: i.target,
    targetDate: i.targetDate,
    targetInTodaysMoney: i.targetInTodaysMoney,
    portfolioId: i.portfolioId,
    assumptions: i.assumptions,
  );

  void _checkName(List<GoalEntry> all, String name, {String? exceptId}) {
    final taken = all.any(
      (e) =>
          e.goal.id != exceptId &&
          e.goal.name.trim().toLowerCase() == name.trim().toLowerCase(),
    );
    if (taken) throw const GoalRuleException(GoalRule.nameTaken);
  }

  @override
  Future<GoalEntry> create(GoalInput input) async {
    final all = await _all();
    if (all.length >= maxGoals) throw const GoalRuleException(GoalRule.tooMany);
    _checkName(all, input.name);
    _counter++;
    final entry = GoalEntry(goal: _build('demo-goal-$_counter', input));
    _created.add(entry);
    return entry;
  }

  @override
  Future<GoalEntry> update(String id, GoalInput input) async {
    final all = await _all();
    if (!all.any((e) => e.goal.id == id)) {
      throw const GoalRuleException(GoalRule.notFound);
    }
    _checkName(all, input.name, exceptId: id);
    // The figures belonged to the old assumptions; the demo cannot recalculate them.
    final entry = GoalEntry(goal: _build(id, input));
    _changed[id] = entry;
    return entry;
  }
}

final goalRepositoryProvider = Provider<GoalRepository>((ref) {
  switch (ref.watch(dataSourceModeProvider)) {
    case DataSourceMode.demo:
      return DemoGoalRepository(
        ref.watch(demoAssetsProvider),
        ref.read(demoBehaviorProvider.notifier).gate,
      );
  }
});

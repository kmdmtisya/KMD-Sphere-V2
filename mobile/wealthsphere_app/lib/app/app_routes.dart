import 'package:flutter/foundation.dart';

/// Every route path in one place. Widgets never hard-code path strings.
///
/// Navigation structure (ADR-0002): five tabs, each with its own back stack.
/// `Home | Portfolio | AI Wealth | Goals | More`; holdings hang off Portfolio and the
/// calculator and forecast off More.
abstract final class AppRoutes {
  static const String home = '/home';
  static const String portfolio = '/portfolio';
  static const String holdings = '/portfolio/holdings';
  static const String transactions = '/portfolio/transactions';
  static const String addTransaction = '/portfolio/transactions/add';
  static const String ai = '/ai';
  static const String doctor = '/ai/doctor';
  static const String opportunities = '/ai/opportunities';
  static const String compareOpportunities = '/ai/opportunities/compare';
  static const String goals = '/goals';
  static const String addGoal = '/goals/add';
  static const String more = '/more';
  static const String netWorth = '/more/net-worth';
  static const String income = '/more/income';
  static const String settings = '/more/settings';
  static const String calculator = '/more/calculator';
  static const String forecast = '/more/calculator/forecast';

  /// Screen 1 (first launch) and screen 2, outside the tab shell.
  static const String welcome = '/welcome';
  static const String signIn = '/sign-in';

  /// Debug-only component gallery. Not registered in release builds.
  static const String gallery = '/_gallery';

  /// One goal, and its edit form. The id is encoded so an odd id can never change the path.
  static String goal(String id) => '$goals/${Uri.encodeComponent(id)}';
  static String editGoal(String id) => '${goal(id)}/edit';

  /// One investment (an asset). The symbol is encoded, so an odd symbol never changes the path.
  static String investment(String symbol) =>
      '$holdings/${Uri.encodeComponent(symbol)}';

  /// One ledger entry. The id is encoded, so an odd id can never change the path.
  static String transaction(String id) =>
      '$transactions/${Uri.encodeComponent(id)}';

  /// The query parameter that carries the AI chat context.
  static const String aiScopeParam = 'scope';

  /// `/ai?scope=portfolio:<id>`: opens AI Wealth with an explicit, visible context.
  static String aiWith(AiScope scope) =>
      Uri(path: ai, queryParameters: {aiScopeParam: scope.encoded}).toString();
}

enum AiScopeKind { portfolio, forecast, goal }

/// The portfolio, forecast or goal an AI conversation was opened for.
///
/// Deep links and notifications can carry this value, so it is **untrusted input**: parsing is
/// strict and an invalid value is ignored (never guessed at). The backend still authorises every
/// resource the AI touches; this is only the client-side context shown to the user.
@immutable
class AiScope {
  const AiScope(this.kind, this.id);

  final AiScopeKind kind;
  final String id;

  static final RegExp _idPattern = RegExp(r'^[A-Za-z0-9_-]{1,64}$');

  /// `kind:id` with kind in {portfolio, forecast, goal}; null for anything else.
  static AiScope? tryParse(String? raw) {
    if (raw == null) return null;
    final separator = raw.indexOf(':');
    if (separator <= 0) return null;
    final kindName = raw.substring(0, separator);
    final id = raw.substring(separator + 1);
    final kind = AiScopeKind.values
        .where((k) => k.name == kindName)
        .firstOrNull;
    if (kind == null || !_idPattern.hasMatch(id)) return null;
    return AiScope(kind, id);
  }

  String get encoded => '${kind.name}:$id';

  @override
  bool operator ==(Object other) =>
      other is AiScope && other.kind == kind && other.id == id;

  @override
  int get hashCode => Object.hash(kind, id);

  @override
  String toString() => 'AiScope($encoded)';
}

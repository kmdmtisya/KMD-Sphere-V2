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
  static const String ai = '/ai';
  static const String goals = '/goals';
  static const String more = '/more';
  static const String calculator = '/more/calculator';
  static const String forecast = '/more/calculator/forecast';

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

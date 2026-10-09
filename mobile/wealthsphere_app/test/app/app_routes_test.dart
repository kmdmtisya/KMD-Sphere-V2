import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/app/app_routes.dart';
import 'package:wealthsphere_app/app/app_tab.dart';

void main() {
  group('route table', () {
    test('every path is absolute and unique', () {
      final paths = [
        AppRoutes.home,
        AppRoutes.portfolio,
        AppRoutes.holdings,
        AppRoutes.ai,
        AppRoutes.goals,
        AppRoutes.more,
        AppRoutes.calculator,
        AppRoutes.forecast,
      ]; // fmt: skip
      for (final p in paths) {
        expect(p, startsWith('/'));
      }
      expect(paths.toSet().length, paths.length);
    });

    test('nested routes sit under their tab root', () {
      expect(AppRoutes.holdings, startsWith('${AppRoutes.portfolio}/'));
      expect(AppRoutes.calculator, startsWith('${AppRoutes.more}/'));
      expect(AppRoutes.forecast, startsWith('${AppRoutes.calculator}/'));
    });

    test('there are exactly five tabs in the approved order (ADR-0002)', () {
      expect(AppTab.values.map((t) => t.name), [
        'home',
        'portfolio',
        'ai',
        'goals',
        'more',
      ]);
      expect(AppTab.values.map((t) => t.path), [
        AppRoutes.home,
        AppRoutes.portfolio,
        AppRoutes.ai,
        AppRoutes.goals,
        AppRoutes.more,
      ]); // fmt: skip
    });
  });

  group('AiScope (untrusted deep-link input)', () {
    test('parses the three supported kinds', () {
      expect(
        AiScope.tryParse('portfolio:abc-123'),
        const AiScope(AiScopeKind.portfolio, 'abc-123'),
      );
      expect(
        AiScope.tryParse('forecast:f_9'),
        const AiScope(AiScopeKind.forecast, 'f_9'),
      );
      expect(
        AiScope.tryParse('goal:7f9c1b2e'),
        const AiScope(AiScopeKind.goal, '7f9c1b2e'),
      );
    });

    test('round-trips through its encoded form', () {
      for (final kind in AiScopeKind.values) {
        final scope = AiScope(kind, 'id-1');
        expect(AiScope.tryParse(scope.encoded), scope);
      }
    });

    test(
      'rejects missing, malformed and unknown values instead of guessing',
      () {
        final bad = <String?>[
          null,
          '',
          ':',
          'portfolio',
          'portfolio:',
          ':abc',
          'asset:abc',
          'PORTFOLIO:abc',
          'portfolio:has space',
          'portfolio:a/b',
          'portfolio:a:b',
          'portfolio:../../etc',
          'portfolio:%2e%2e',
          'portfolio:<script>',
          "portfolio:' OR 1=1",
          'portfolio:ünï',
          'portfolio:${'x' * 65}',
          'portfolio:abc\n',
          'goal:abc;rm',
        ]; // fmt: skip
        for (final raw in bad) {
          expect(AiScope.tryParse(raw), isNull, reason: '$raw');
        }
      },
    );

    test('accepts ids up to 64 characters', () {
      expect(AiScope.tryParse('portfolio:${'a' * 64}'), isNotNull);
    });

    test('aiWith builds a link that parses back, and escapes the value', () {
      const scope = AiScope(AiScopeKind.portfolio, 'p-1');
      final link = AppRoutes.aiWith(scope);
      expect(Uri.parse(link).path, AppRoutes.ai);
      expect(
        AiScope.tryParse(
          Uri.parse(link).queryParameters[AppRoutes.aiScopeParam],
        ),
        scope,
      );
    });

    test('equality and hashing', () {
      expect(
        const AiScope(AiScopeKind.goal, 'g'),
        const AiScope(AiScopeKind.goal, 'g'),
      );
      expect(
        const AiScope(AiScopeKind.goal, 'g').hashCode,
        const AiScope(AiScopeKind.goal, 'g').hashCode,
      );
      expect(
        const AiScope(AiScopeKind.goal, 'g') ==
            const AiScope(AiScopeKind.forecast, 'g'),
        isFalse,
      );
    });
  });
}

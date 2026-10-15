import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:wealthsphere_app/shared/design_system/tokens/tokens.dart';

/// The shared token source (design/tokens/wealthsphere.tokens.json, P14-T03) generates
/// BrandPalette and the web CSS. This test proves the Dart role mapping in [WealthColors] matches the
/// source, so mobile and web show the same colour for the same role in both themes.
void main() {
  final source = jsonDecode(
    File('../../design/tokens/wealthsphere.tokens.json').readAsStringSync(),
  ) as Map<String, dynamic>;
  final palette = <String, Color>{
    for (final MapEntry(:key, :value)
        in (source['palette'] as Map<String, dynamic>).entries)
      if (!key.startsWith(r'$'))
        key: Color(
          int.parse(
            'FF${((value as Map<String, dynamic>)['value'] as String).substring(1)}',
            radix: 16,
          ),
        ),
  };

  final themes = <String, WealthColors>{
    'light': WealthColors.light,
    'dark': WealthColors.dark,
  };

  for (final MapEntry(key: theme, value: colors) in themes.entries) {
    final roles =
        (source['roles'] as Map<String, dynamic>)[theme]
            as Map<String, dynamic>;

    test('$theme: every WealthColors role matches the token source', () {
      final dartRoles = colors.roles;
      final sourceRoles = roles.keys.where((k) => !k.startsWith(r'$')).toSet();
      expect(dartRoles.keys.toSet(), sourceRoles);
      for (final role in sourceRoles) {
        expect(
          dartRoles[role],
          palette[roles[role] as String],
          reason: '$theme.$role should be ${roles[role]}',
        );
      }
    });

    test('$theme: the chart series match the token source', () {
      final series =
          ((source['chartSeries'] as Map<String, dynamic>)[theme]
                  as List<dynamic>)
              .map((ref) => palette[ref as String])
              .toList();
      expect(colors.chartSeries, series);
    });
  }
}

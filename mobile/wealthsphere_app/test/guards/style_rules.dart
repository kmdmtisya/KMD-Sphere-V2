import 'dart:io';

/// Source-level style rules enforced on `lib/` (see `style_guard_test.dart`).
///
/// - Colours come from semantic tokens: colour literals live only in `brand_palette.dart`.
/// - Layout is RTL-ready: use start/end (directional) APIs, never left/right ones.
/// - Money and formatting code never uses binary floating point (ADR-0003).
class StyleRule {
  const StyleRule(this.id, this.description, this.pattern, {this.appliesTo});

  final String id;
  final String description;
  final RegExp pattern;
  final bool Function(String path)? appliesTo;
}

class Violation {
  const Violation(this.path, this.line, this.rule, this.snippet);

  final String path;
  final int line;
  final String rule;
  final String snippet;

  @override
  String toString() => '$path:$line [$rule] $snippet';
}

bool _isBrandPalette(String p) =>
    p.endsWith('shared/design_system/tokens/brand_palette.dart');
bool _isMoneyOrFormatting(String p) =>
    p.contains('shared/design_system/formatting/');

final List<StyleRule> styleRules = <StyleRule>[
  StyleRule(
    'hardcoded-color',
    'Colour literals are only allowed in tokens/brand_palette.dart; use WealthColors roles.',
    RegExp(r'\bColor\(\s*0x'),
    appliesTo: (p) => !_isBrandPalette(p),
  ),
  StyleRule(
    'color-constructor',
    'Build colours from tokens, not Color.fromARGB / Color.fromRGBO.',
    RegExp(r'\bColor\.from(ARGB|RGBO)\('),
    appliesTo: (p) => !_isBrandPalette(p),
  ),
  StyleRule(
    'material-named-color',
    'Use WealthColors roles instead of Colors.<name> (Colors.transparent is allowed).',
    RegExp(r'\bColors\.(?!transparent\b)\w+'),
  ),
  StyleRule(
    'directional-edge-insets',
    'Use EdgeInsetsDirectional (start/end), not EdgeInsets.only(left/right) or fromLTRB.',
    RegExp(
      r'EdgeInsets\.only\([^;]{0,300}?\b(left|right)\s*:|\bEdgeInsets\.fromLTRB\(',
    ),
  ),
  StyleRule(
    'directional-alignment',
    'Use AlignmentDirectional (start/end), not Alignment.<left|right> variants.',
    RegExp(
      r'\bAlignment\.(centerLeft|centerRight|topLeft|topRight|bottomLeft|bottomRight)\b',
    ),
  ),
  StyleRule(
    'directional-text-align',
    'Use TextAlign.start / TextAlign.end, not left / right.',
    RegExp(r'\bTextAlign\.(left|right)\b'),
  ),
  StyleRule(
    'directional-positioned',
    'Use PositionedDirectional (start/end), not Positioned(left/right).',
    RegExp(r'\bPositioned\(\s*[^)]{0,200}?\b(left|right)\s*:'),
  ),
  StyleRule(
    'directional-border-radius',
    'Use BorderRadiusDirectional, not BorderRadius.only(topLeft/topRight/bottomLeft/bottomRight).',
    RegExp(
      r'BorderRadius\.only\([^;]{0,300}?\b(topLeft|topRight|bottomLeft|bottomRight)\s*:',
    ),
  ),
  StyleRule(
    'no-double-in-money-code',
    'Money and formatting code must not use double/num (ADR-0003); use Decimal.',
    RegExp(r'\bdouble\b|\bnum\b|\.toDouble\(\)'),
    appliesTo: _isMoneyOrFormatting,
  ),
];

/// Replaces comments with spaces (keeping newlines) so line numbers stay correct and commented
/// examples never count as violations.
String blankComments(String source) {
  final blanked = source.replaceAllMapped(
    RegExp(r'/\*[\s\S]*?\*/|(^|\s)//[^\n]*', multiLine: true),
    (m) => m.group(0)!.replaceAll(RegExp(r'[^\n]'), ' '),
  );
  return blanked;
}

List<Violation> scanSource(
  String path,
  String source, {
  List<StyleRule>? rules,
}) {
  final text = blankComments(source);
  final found = <Violation>[];
  for (final rule in rules ?? styleRules) {
    if (rule.appliesTo != null && !rule.appliesTo!(path)) continue;
    for (final match in rule.pattern.allMatches(text)) {
      final line = '\n'.allMatches(text.substring(0, match.start)).length + 1;
      found.add(
        Violation(
          path,
          line,
          rule.id,
          match.group(0)!.replaceAll(RegExp(r'\s+'), ' '),
        ),
      );
    }
  }
  return found;
}

bool _isGenerated(String path) =>
    path.endsWith('.g.dart') ||
    path.endsWith('.freezed.dart') ||
    path.contains('lib/l10n/generated/');

/// Scans every hand-written Dart file under [libDir].
List<Violation> scanLib(String libDir) {
  final violations = <Violation>[];
  final dir = Directory(libDir);
  for (final entity in dir.listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith('.dart')) continue;
    final path = entity.path.replaceAll('\\', '/');
    final relative = path.substring(path.indexOf('lib/'));
    if (_isGenerated(relative)) continue;
    violations.addAll(scanSource(relative, entity.readAsStringSync()));
  }
  return violations;
}

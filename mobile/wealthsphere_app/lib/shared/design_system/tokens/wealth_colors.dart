import 'package:flutter/material.dart';

import 'brand_palette.dart';

/// Semantic colour roles for WealthSphere, available as a [ThemeExtension].
///
/// Widgets use roles (`positiveText`, `surface`, ...) and never raw colours, so light and dark
/// themes stay consistent and contrast is guaranteed by `test/.../contrast_test.dart`:
/// every text role is at least 4.5:1 and every icon, border and chart role at least 3:1 against
/// the surfaces it is drawn on.
@immutable
class WealthColors extends ThemeExtension<WealthColors> {
  const WealthColors({
    required this.primary,
    required this.onPrimary,
    required this.accent,
    required this.onAccent,
    required this.scaffold,
    required this.surface,
    required this.surfaceElevated,
    required this.border,
    required this.divider,
    required this.textPrimary,
    required this.textMuted,
    required this.positive,
    required this.positiveText,
    required this.negative,
    required this.negativeText,
    required this.warning,
    required this.warningText,
    required this.riskLow,
    required this.riskMedium,
    required this.riskHigh,
    required this.demoBadge,
    required this.onDemoBadge,
    required this.staleBanner,
    required this.onStaleBanner,
    required this.chartSeries,
    required this.chartContributions,
    required this.chartGrowth,
    required this.chartGrid,
  });

  /// Primary call to action and selected navigation.
  final Color primary;
  final Color onPrimary;

  /// Premium accent (goal milestones, highlights).
  final Color accent;
  final Color onAccent;

  /// Page background, card surface and a raised surface (sheets, menus).
  final Color scaffold;
  final Color surface;
  final Color surfaceElevated;

  /// Component boundary (inputs, outlined buttons): at least 3:1. [divider] is decorative only.
  final Color border;
  final Color divider;

  final Color textPrimary;
  final Color textMuted;

  /// Gains. [positive] is for icons and fills; [positiveText] is for text.
  final Color positive;
  final Color positiveText;

  /// Losses and errors. Always shown with a sign, icon or text, never colour alone.
  final Color negative;
  final Color negativeText;

  final Color warning;
  final Color warningText;

  /// Risk labels (text and icon safe). Always shown with an icon and a word.
  final Color riskLow;
  final Color riskMedium;
  final Color riskHigh;

  /// "DEMO" badge and the stale-data banner.
  final Color demoBadge;
  final Color onDemoBadge;
  final Color staleBanner;
  final Color onStaleBanner;

  /// Categorical chart palette (at least six hues) and the two forecast series roles.
  final List<Color> chartSeries;
  final Color chartContributions;
  final Color chartGrowth;
  final Color chartGrid;

  static const WealthColors light = WealthColors(
    primary: BrandPalette.blue600,
    onPrimary: BrandPalette.surfaceLight,
    accent: BrandPalette.gold400,
    onAccent: BrandPalette.navy900,
    scaffold: BrandPalette.surfaceSubtle,
    surface: BrandPalette.surfaceLight,
    surfaceElevated: BrandPalette.surfaceLight,
    border: BrandPalette.slate500,
    divider: BrandPalette.slate200,
    textPrimary: BrandPalette.navy900,
    textMuted: BrandPalette.slate600,
    positive: BrandPalette.teal600,
    positiveText: BrandPalette.teal700,
    negative: BrandPalette.danger,
    negativeText: BrandPalette.red700,
    warning: BrandPalette.amber700,
    warningText: BrandPalette.amber700,
    riskLow: BrandPalette.teal700,
    riskMedium: BrandPalette.amber700,
    riskHigh: BrandPalette.red700,
    demoBadge: BrandPalette.gold400,
    onDemoBadge: BrandPalette.navy900,
    staleBanner: BrandPalette.amber100,
    onStaleBanner: BrandPalette.amber900,
    chartSeries: <Color>[
      BrandPalette.blue600,
      BrandPalette.teal600,
      BrandPalette.amber700,
      BrandPalette.violet600,
      BrandPalette.pink600,
      BrandPalette.slate600,
    ],
    chartContributions: BrandPalette.slate600,
    chartGrowth: BrandPalette.teal600,
    chartGrid: BrandPalette.slate200,
  );

  static const WealthColors dark = WealthColors(
    primary: BrandPalette.blue400,
    onPrimary: BrandPalette.navy950,
    accent: BrandPalette.gold400,
    onAccent: BrandPalette.navy900,
    scaffold: BrandPalette.navy950,
    surface: BrandPalette.navy900,
    surfaceElevated: BrandPalette.navy800,
    border: BrandPalette.slate450,
    divider: BrandPalette.navy800,
    textPrimary: BrandPalette.slate100,
    textMuted: BrandPalette.slate400,
    positive: BrandPalette.teal400,
    positiveText: BrandPalette.teal400,
    negative: BrandPalette.red400,
    negativeText: BrandPalette.red400,
    warning: BrandPalette.amber400,
    warningText: BrandPalette.amber400,
    riskLow: BrandPalette.teal400,
    riskMedium: BrandPalette.amber400,
    riskHigh: BrandPalette.red400,
    demoBadge: BrandPalette.gold400,
    onDemoBadge: BrandPalette.navy900,
    staleBanner: BrandPalette.amber950,
    onStaleBanner: BrandPalette.amber200,
    chartSeries: <Color>[
      BrandPalette.blue400,
      BrandPalette.teal400,
      BrandPalette.amber400,
      BrandPalette.violet400,
      BrandPalette.pink400,
      BrandPalette.slate300,
    ],
    chartContributions: BrandPalette.slate300,
    chartGrowth: BrandPalette.teal400,
    chartGrid: BrandPalette.navy800,
  );

  /// Every colour role as a name/value map. Used by tests (contrast, light/dark parity) and by
  /// [lerp]/[copyWith] so a newly added role cannot be forgotten in one of them.
  Map<String, Color> get roles => <String, Color>{
    'primary': primary,
    'onPrimary': onPrimary,
    'accent': accent,
    'onAccent': onAccent,
    'scaffold': scaffold,
    'surface': surface,
    'surfaceElevated': surfaceElevated,
    'border': border,
    'divider': divider,
    'textPrimary': textPrimary,
    'textMuted': textMuted,
    'positive': positive,
    'positiveText': positiveText,
    'negative': negative,
    'negativeText': negativeText,
    'warning': warning,
    'warningText': warningText,
    'riskLow': riskLow,
    'riskMedium': riskMedium,
    'riskHigh': riskHigh,
    'demoBadge': demoBadge,
    'onDemoBadge': onDemoBadge,
    'staleBanner': staleBanner,
    'onStaleBanner': onStaleBanner,
    'chartContributions': chartContributions,
    'chartGrowth': chartGrowth,
    'chartGrid': chartGrid,
  };

  @override
  WealthColors copyWith({
    Color? primary,
    Color? onPrimary,
    Color? accent,
    Color? onAccent,
    Color? scaffold,
    Color? surface,
    Color? surfaceElevated,
    Color? border,
    Color? divider,
    Color? textPrimary,
    Color? textMuted,
    Color? positive,
    Color? positiveText,
    Color? negative,
    Color? negativeText,
    Color? warning,
    Color? warningText,
    Color? riskLow,
    Color? riskMedium,
    Color? riskHigh,
    Color? demoBadge,
    Color? onDemoBadge,
    Color? staleBanner,
    Color? onStaleBanner,
    List<Color>? chartSeries,
    Color? chartContributions,
    Color? chartGrowth,
    Color? chartGrid,
  }) {
    return WealthColors(
      primary: primary ?? this.primary,
      onPrimary: onPrimary ?? this.onPrimary,
      accent: accent ?? this.accent,
      onAccent: onAccent ?? this.onAccent,
      scaffold: scaffold ?? this.scaffold,
      surface: surface ?? this.surface,
      surfaceElevated: surfaceElevated ?? this.surfaceElevated,
      border: border ?? this.border,
      divider: divider ?? this.divider,
      textPrimary: textPrimary ?? this.textPrimary,
      textMuted: textMuted ?? this.textMuted,
      positive: positive ?? this.positive,
      positiveText: positiveText ?? this.positiveText,
      negative: negative ?? this.negative,
      negativeText: negativeText ?? this.negativeText,
      warning: warning ?? this.warning,
      warningText: warningText ?? this.warningText,
      riskLow: riskLow ?? this.riskLow,
      riskMedium: riskMedium ?? this.riskMedium,
      riskHigh: riskHigh ?? this.riskHigh,
      demoBadge: demoBadge ?? this.demoBadge,
      onDemoBadge: onDemoBadge ?? this.onDemoBadge,
      staleBanner: staleBanner ?? this.staleBanner,
      onStaleBanner: onStaleBanner ?? this.onStaleBanner,
      chartSeries: chartSeries ?? this.chartSeries,
      chartContributions: chartContributions ?? this.chartContributions,
      chartGrowth: chartGrowth ?? this.chartGrowth,
      chartGrid: chartGrid ?? this.chartGrid,
    );
  }

  @override
  WealthColors lerp(ThemeExtension<WealthColors>? other, double t) {
    if (other is! WealthColors) return this;
    Color mix(Color a, Color b) => Color.lerp(a, b, t)!;
    final count = chartSeries.length < other.chartSeries.length
        ? chartSeries.length
        : other.chartSeries.length;
    return WealthColors(
      primary: mix(primary, other.primary),
      onPrimary: mix(onPrimary, other.onPrimary),
      accent: mix(accent, other.accent),
      onAccent: mix(onAccent, other.onAccent),
      scaffold: mix(scaffold, other.scaffold),
      surface: mix(surface, other.surface),
      surfaceElevated: mix(surfaceElevated, other.surfaceElevated),
      border: mix(border, other.border),
      divider: mix(divider, other.divider),
      textPrimary: mix(textPrimary, other.textPrimary),
      textMuted: mix(textMuted, other.textMuted),
      positive: mix(positive, other.positive),
      positiveText: mix(positiveText, other.positiveText),
      negative: mix(negative, other.negative),
      negativeText: mix(negativeText, other.negativeText),
      warning: mix(warning, other.warning),
      warningText: mix(warningText, other.warningText),
      riskLow: mix(riskLow, other.riskLow),
      riskMedium: mix(riskMedium, other.riskMedium),
      riskHigh: mix(riskHigh, other.riskHigh),
      demoBadge: mix(demoBadge, other.demoBadge),
      onDemoBadge: mix(onDemoBadge, other.onDemoBadge),
      staleBanner: mix(staleBanner, other.staleBanner),
      onStaleBanner: mix(onStaleBanner, other.onStaleBanner),
      chartSeries: <Color>[
        for (var i = 0; i < count; i++)
          mix(chartSeries[i], other.chartSeries[i]),
      ],
      chartContributions: mix(chartContributions, other.chartContributions),
      chartGrowth: mix(chartGrowth, other.chartGrowth),
      chartGrid: mix(chartGrid, other.chartGrid),
    );
  }
}

extension WealthColorsContext on BuildContext {
  /// The semantic colours of the active theme. Falls back to the matching built-in palette when
  /// the theme does not register the extension (for example in an isolated widget test).
  WealthColors get wealthColors {
    final theme = Theme.of(this);
    return theme.extension<WealthColors>() ??
        (theme.brightness == Brightness.dark
            ? WealthColors.dark
            : WealthColors.light);
  }
}

import 'package:flutter/material.dart';

import '../tokens/wealth_colors.dart';

/// WealthSphere's named type scale.
///
/// The font family is the platform's own (San Francisco on iOS, Roboto on Android), so text feels
/// native and follows the user's system text-size setting. Amounts use tabular figures so digits
/// do not jitter as values change.
@immutable
class WealthTypography extends ThemeExtension<WealthTypography> {
  const WealthTypography({
    required this.displayAmount,
    required this.amount,
    required this.headline,
    required this.title,
    required this.body,
    required this.label,
    required this.caption,
  });

  /// Builds the scale from a Material [TextTheme] (used only for the platform font family) and
  /// the semantic [colors].
  ///
  /// Sizes and line heights are defined here explicitly: a freshly built `ThemeData` text theme
  /// carries fonts and colours but no sizes until `MaterialApp` localises it, so relying on it
  /// would silently fall back to Flutter's defaults.
  factory WealthTypography.from(TextTheme t, WealthColors colors) {
    TextStyle style(
      TextStyle? family, {
      required double size,
      required double height,
      FontWeight weight = FontWeight.w400,
      Color? color,
      double? letterSpacing,
      bool tabular = false,
    }) => (family ?? const TextStyle()).copyWith(
      color: color ?? colors.textPrimary,
      fontSize: size,
      height: height,
      fontWeight: weight,
      letterSpacing: letterSpacing,
      fontFeatures: tabular ? const [FontFeature.tabularFigures()] : null,
    );
    final family = t.bodyLarge;
    return WealthTypography(
      displayAmount: style(
        family,
        size: 34,
        height: 1.15,
        weight: FontWeight.w700,
        letterSpacing: -0.5,
        tabular: true,
      ),
      amount: style(
        family,
        size: 16,
        height: 1.4,
        weight: FontWeight.w600,
        tabular: true,
      ),
      headline: style(family, size: 24, height: 1.33, weight: FontWeight.w600),
      title: style(family, size: 16, height: 1.4, weight: FontWeight.w600),
      body: style(family, size: 16, height: 1.5),
      label: style(family, size: 14, height: 1.43, weight: FontWeight.w600),
      caption: style(family, size: 12, height: 1.33, color: colors.textMuted),
    );
  }

  /// Hero figure, such as total wealth.
  final TextStyle displayAmount;

  /// Money in lists and cards (tabular figures).
  final TextStyle amount;

  final TextStyle headline;
  final TextStyle title;
  final TextStyle body;
  final TextStyle label;

  /// Secondary and supporting text (muted colour, still 4.5:1 or better).
  final TextStyle caption;

  List<TextStyle> get all => [
    displayAmount,
    amount,
    headline,
    title,
    body,
    label,
    caption,
  ];

  @override
  WealthTypography copyWith({
    TextStyle? displayAmount,
    TextStyle? amount,
    TextStyle? headline,
    TextStyle? title,
    TextStyle? body,
    TextStyle? label,
    TextStyle? caption,
  }) => WealthTypography(
    displayAmount: displayAmount ?? this.displayAmount,
    amount: amount ?? this.amount,
    headline: headline ?? this.headline,
    title: title ?? this.title,
    body: body ?? this.body,
    label: label ?? this.label,
    caption: caption ?? this.caption,
  );

  @override
  WealthTypography lerp(ThemeExtension<WealthTypography>? other, double t) {
    if (other is! WealthTypography) return this;
    TextStyle mix(TextStyle a, TextStyle b) => TextStyle.lerp(a, b, t)!;
    return WealthTypography(
      displayAmount: mix(displayAmount, other.displayAmount),
      amount: mix(amount, other.amount),
      headline: mix(headline, other.headline),
      title: mix(title, other.title),
      body: mix(body, other.body),
      label: mix(label, other.label),
      caption: mix(caption, other.caption),
    );
  }
}

extension WealthTypographyContext on BuildContext {
  /// The type scale of the active theme.
  WealthTypography get wealthText {
    final theme = Theme.of(this);
    return theme.extension<WealthTypography>() ??
        WealthTypography.from(theme.textTheme, wealthColors);
  }
}

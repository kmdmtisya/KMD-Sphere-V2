import 'package:flutter/widgets.dart';

/// 8-point spacing grid (4 for tight pairs). Use these instead of numeric literals.
abstract final class AppSpacing {
  static const double xxs = 4;
  static const double xs = 8;
  static const double s = 12;
  static const double m = 16;
  static const double l = 24;
  static const double xl = 32;
  static const double xxl = 40;
  static const double xxxl = 48;

  /// Horizontal page gutter.
  static const double gutter = m;

  static const List<double> scale = <double>[xxs, xs, s, m, l, xl, xxl, xxxl];
}

/// Card and control corner radii (12 to 20 dp per the specification).
abstract final class AppRadii {
  static const double small = 12;
  static const double medium = 16;
  static const double large = 20;

  static const BorderRadius smallRadius = BorderRadius.all(
    Radius.circular(small),
  );
  static const BorderRadius mediumRadius = BorderRadius.all(
    Radius.circular(medium),
  );
  static const BorderRadius largeRadius = BorderRadius.all(
    Radius.circular(large),
  );
}

/// Material elevation levels. Cards stay flat and rely on borders and tonal surfaces.
abstract final class AppElevation {
  static const double none = 0;
  static const double low = 1;
  static const double medium = 3;
  static const double high = 6;
}

/// Animation durations and curves. Always resolve durations through [resolve] so that
/// "reduce motion" (system animations disabled) removes the animation.
abstract final class AppMotion {
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration standard = Duration(milliseconds: 250);
  static const Duration slow = Duration(milliseconds: 400);
  static const Curve curve = Curves.easeOutCubic;

  /// [base], or [Duration.zero] when the platform asks for reduced motion.
  static Duration resolve(BuildContext context, Duration base) =>
      MediaQuery.disableAnimationsOf(context) ? Duration.zero : base;
}

/// Minimum interactive sizes (Material 48 dp, Apple HIG 44 pt).
abstract final class AppTouchTarget {
  static const double android = 48;
  static const double ios = 44;
}

enum WindowSizeClass { compact, medium, expanded }

/// Width breakpoints. Phones are `compact`; larger classes are handled by constraining content
/// width until adaptive tablet layouts arrive in a later phase.
abstract final class AppBreakpoints {
  static const double mediumMin = 600;
  static const double expandedMin = 840;

  /// Maximum width of a readable content column on larger screens.
  static const double maxContentWidth = 640;

  static WindowSizeClass classify(double width) {
    if (width >= expandedMin) return WindowSizeClass.expanded;
    if (width >= mediumMin) return WindowSizeClass.medium;
    return WindowSizeClass.compact;
  }

  static WindowSizeClass of(BuildContext context) =>
      classify(MediaQuery.sizeOf(context).width);
}

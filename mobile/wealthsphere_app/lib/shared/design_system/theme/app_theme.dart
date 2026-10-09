import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../tokens/tokens.dart';
import 'wealth_typography.dart';

/// Builds the light and dark Material 3 themes from the semantic tokens.
///
/// Everything visual comes from [WealthColors], [WealthTypography] and the scale tokens: there are
/// no colour or size literals here. Interactive controls are at least 48 dp, selection is never
/// shown by colour alone (check marks, indicators), and fields have a visible 3:1 boundary.
abstract final class AppTheme {
  static ThemeData light() => _build(WealthColors.light, Brightness.light);

  static ThemeData dark() => _build(WealthColors.dark, Brightness.dark);

  /// Material colour scheme derived from the WealthSphere roles. Exposed for tests.
  static ColorScheme colorScheme(WealthColors c, Brightness brightness) {
    final isLight = brightness == Brightness.light;
    // Text on solid secondary/error fills: white on the dark light-mode fills, navy on the
    // lighter dark-mode fills (both >= 4.5:1, verified in app_theme_test).
    final onFill = isLight ? c.surface : c.scaffold;
    Color tint(Color color, double alpha) =>
        Color.alphaBlend(color.withValues(alpha: alpha), c.surface);
    return ColorScheme(
      brightness: brightness,
      primary: c.primary,
      onPrimary: c.onPrimary,
      primaryContainer: tint(c.primary, 0.16),
      onPrimaryContainer: c.textPrimary,
      secondary: c.positiveText,
      onSecondary: onFill,
      secondaryContainer: tint(c.positive, 0.16),
      onSecondaryContainer: c.textPrimary,
      tertiary: c.accent,
      onTertiary: c.onAccent,
      tertiaryContainer: tint(c.accent, 0.28),
      onTertiaryContainer: c.textPrimary,
      error: c.negativeText,
      onError: onFill,
      errorContainer: tint(c.negative, 0.16),
      onErrorContainer: c.textPrimary,
      surface: c.surface,
      onSurface: c.textPrimary,
      onSurfaceVariant: c.textMuted,
      surfaceContainerLowest: c.scaffold,
      surfaceContainerLow: c.scaffold,
      surfaceContainer: c.surface,
      surfaceContainerHigh: c.surfaceElevated,
      surfaceContainerHighest: c.surfaceElevated,
      outline: c.border,
      outlineVariant: c.divider,
      inverseSurface: c.textPrimary,
      onInverseSurface: c.scaffold,
      // Action colour on the inverse surface (snack bars): gold on navy, brand blue on light grey.
      inversePrimary: isLight ? c.accent : BrandPalette.blue600,
    );
  }

  static ThemeData _build(WealthColors c, Brightness brightness) {
    final scheme = colorScheme(c, brightness);
    final base = ThemeData(brightness: brightness, useMaterial3: true);
    final textTheme = base.textTheme.apply(
      bodyColor: c.textPrimary,
      displayColor: c.textPrimary,
    );
    final type = WealthTypography.from(textTheme, c);

    const touchTarget = Size(AppTouchTarget.android, AppTouchTarget.android);
    const buttonShape = RoundedRectangleBorder(
      borderRadius: AppRadii.smallRadius,
    );
    const buttonPadding = EdgeInsetsDirectional.symmetric(
      horizontal: AppSpacing.l,
    );
    final fieldBorder = OutlineInputBorder(
      borderRadius: AppRadii.smallRadius,
      borderSide: BorderSide(color: c.border),
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: c.scaffold,
      canvasColor: c.surface,
      dividerColor: c.divider,
      textTheme: textTheme,
      visualDensity: VisualDensity.standard,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      extensions: <ThemeExtension<dynamic>>[c, type],
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: <TargetPlatform, PageTransitionsBuilder>{
          TargetPlatform.android: ZoomPageTransitionsBuilder(),
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
        },
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: c.scaffold,
        foregroundColor: c.textPrimary,
        elevation: AppElevation.none,
        scrolledUnderElevation: AppElevation.none,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: type.title,
      ),
      cardTheme: CardThemeData(
        color: c.surface,
        elevation: AppElevation.none,
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadii.mediumRadius,
          side: BorderSide(color: c.divider),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: touchTarget,
          padding: buttonPadding,
          shape: buttonShape,
          textStyle: type.label,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          minimumSize: touchTarget,
          padding: buttonPadding,
          shape: buttonShape,
          textStyle: type.label,
          elevation: AppElevation.none,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: touchTarget,
          padding: buttonPadding,
          shape: buttonShape,
          textStyle: type.label,
          side: BorderSide(color: c.border),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          minimumSize: touchTarget,
          padding: buttonPadding,
          shape: buttonShape,
          textStyle: type.label,
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(minimumSize: touchTarget),
      ),
      chipTheme: ChipThemeData(
        shape: const RoundedRectangleBorder(borderRadius: AppRadii.smallRadius),
        side: BorderSide(color: c.border),
        backgroundColor: c.surface,
        selectedColor: scheme.primaryContainer,
        labelStyle: type.label,
        checkmarkColor: c.textPrimary,
        showCheckmark: true,
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: AppSpacing.xxs,
        ),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll<Size>(
            Size(0, AppTouchTarget.android),
          ),
          shape: const WidgetStatePropertyAll<OutlinedBorder>(buttonShape),
          side: WidgetStatePropertyAll<BorderSide>(BorderSide(color: c.border)),
          textStyle: WidgetStatePropertyAll<TextStyle>(type.label),
          foregroundColor: WidgetStatePropertyAll<Color>(c.textPrimary),
          backgroundColor: WidgetStateProperty.resolveWith<Color>(
            (states) => states.contains(WidgetState.selected)
                ? scheme.primaryContainer
                : c.surface,
          ),
        ),
        // The selected segment always shows a check mark, so selection is not colour-only.
        selectedIcon: const Icon(Icons.check),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: c.surface,
        border: fieldBorder,
        enabledBorder: fieldBorder,
        focusedBorder: fieldBorder.copyWith(
          borderSide: BorderSide(color: c.primary, width: 2),
        ),
        errorBorder: fieldBorder.copyWith(
          borderSide: BorderSide(color: c.negativeText),
        ),
        focusedErrorBorder: fieldBorder.copyWith(
          borderSide: BorderSide(color: c.negativeText, width: 2),
        ),
        errorStyle: type.caption.copyWith(color: c.negativeText),
        helperStyle: type.caption,
        hintStyle: type.body.copyWith(color: c.textMuted),
        labelStyle: type.body.copyWith(color: c.textMuted),
        floatingLabelStyle: type.caption.copyWith(color: c.textPrimary),
        contentPadding: const EdgeInsetsDirectional.symmetric(
          horizontal: AppSpacing.m,
          vertical: AppSpacing.s,
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: c.surface,
        surfaceTintColor: Colors.transparent,
        elevation: AppElevation.none,
        indicatorColor: scheme.primaryContainer,
        // Labels are always visible: icons alone are not an accessible navigation cue.
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        labelTextStyle: WidgetStateProperty.resolveWith<TextStyle>(
          (states) => type.caption.copyWith(
            color: c.textPrimary,
            fontWeight: states.contains(WidgetState.selected)
                ? FontWeight.w700
                : FontWeight.w500,
          ),
        ),
        iconTheme: WidgetStateProperty.resolveWith<IconThemeData>(
          (states) => IconThemeData(
            color: states.contains(WidgetState.selected)
                ? c.primary
                : c.textMuted,
          ),
        ),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: c.surfaceElevated,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        clipBehavior: Clip.antiAlias,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppRadii.large),
          ),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: c.surfaceElevated,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(borderRadius: AppRadii.largeRadius),
        titleTextStyle: type.headline,
        contentTextStyle: type.body,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: scheme.inverseSurface,
        contentTextStyle: type.body.copyWith(color: scheme.onInverseSurface),
        actionTextColor: scheme.inversePrimary,
        shape: const RoundedRectangleBorder(borderRadius: AppRadii.smallRadius),
      ),
      dividerTheme: DividerThemeData(color: c.divider, thickness: 1, space: 1),
      listTileTheme: ListTileThemeData(
        iconColor: c.textMuted,
        textColor: c.textPrimary,
        titleTextStyle: type.body,
        subtitleTextStyle: type.caption,
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: c.primary,
        linearTrackColor: c.divider,
        circularTrackColor: c.divider,
      ),
      textSelectionTheme: TextSelectionThemeData(
        cursorColor: c.primary,
        selectionHandleColor: c.primary,
      ),
    );
  }
}

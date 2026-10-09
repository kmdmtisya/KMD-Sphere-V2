import 'package:flutter/painting.dart';

/// Raw colour values. **This is the only file allowed to contain colour literals**
/// (enforced by `test/guards/style_guard_test.dart`). Widgets never use these directly: they read
/// semantic roles from `WealthColors`, which map brand values to roles with checked contrast.
abstract final class BrandPalette {
  // ---- Approved brand tokens (UI/UX specification v1.1) -------------------------------------
  static const Color navy900 = Color(0xFF102A43);
  static const Color teal600 = Color(0xFF0D9488);
  static const Color gold400 = Color(0xFFF2B84B);
  static const Color blue600 = Color(0xFF2563EB);
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color surfaceSubtle = Color(0xFFF5F7FA);
  static const Color textMuted = Color(0xFF64748B);
  static const Color danger = Color(0xFFDC2626);

  // ---- Derived text-safe shades (measured with WCAG 2.x contrast; see docs/design) ----------
  // The brand teal (3.74:1 on white), the muted grey (4.43:1 on the subtle background) and the
  // brand danger red (4.50:1 on the subtle background) are too weak for body text, so text
  // roles use these darker shades while the brand values stay available for fills and icons.
  static const Color teal700 = Color(0xFF0F766E); // 5.47:1 on white
  static const Color red700 = Color(0xFFB91C1C); // 6.47:1 on white
  static const Color amber700 = Color(0xFFB45309); // 5.02:1 on white
  static const Color slate600 = Color(
    0xFF475569,
  ); // 7.06:1 on the subtle background
  static const Color slate500 = Color(
    0xFF64748B,
  ); // 4.43:1 on subtle; component borders (>= 3:1)
  static const Color slate200 = Color(0xFFE2E8F0); // decorative dividers
  static const Color amber100 = Color(0xFFFEF3C7);
  static const Color amber900 = Color(0xFF78350F); // 8.15:1 on amber100

  // ---- Dark-mode variants (the brand navy is too dark for accents on itself) ---------------
  static const Color navy950 = Color(0xFF0B1B2B); // dark scaffold
  static const Color navy800 = Color(0xFF14304C); // dark elevated surface
  static const Color blue400 = Color(0xFF60A5FA); // 5.76:1 on navy900
  static const Color teal400 = Color(0xFF2DD4BF); // 7.87:1 on navy900
  static const Color red400 = Color(0xFFF87171); // 5.29:1 on navy900
  static const Color amber400 = Color(0xFFFBBF24); // 8.77:1 on navy900
  static const Color slate450 = Color(
    0xFF7A8BA3,
  ); // dark component borders: 3.89:1 on navy800
  static const Color slate400 = Color(0xFF94A3B8); // 5.71:1 on navy900
  static const Color slate300 = Color(0xFFCBD5E1);
  static const Color slate100 = Color(0xFFF1F5F9); // 13.37:1 on navy900
  static const Color amber950 = Color(0xFF3B2A0A);
  static const Color amber200 = Color(0xFFFDE68A);

  // ---- Chart-only hues (3:1 or better against the card surface in each theme) ---------------
  static const Color violet600 = Color(0xFF7C3AED);
  static const Color violet400 = Color(0xFFA78BFA);
  static const Color pink600 = Color(0xFFDB2777);
  static const Color pink400 = Color(0xFFF472B6);
}

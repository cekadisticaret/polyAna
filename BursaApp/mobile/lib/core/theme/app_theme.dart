import 'package:flutter/material.dart';

class AppColors {
  static const bg = Color(0xFFDCE8DC);
  static const bgSoft = Color(0xFFE8F0E6);
  static const bgDeep = Color(0xFF3D5A4C);
  static const nav = Color(0xFF1A2E24);
  static const card = Color(0xFFFFFFFF);
  static const ink = Color(0xFF142018);
  static const muted = Color(0xFF5F6F64);
  static const accent = Color(0xFFC9B89A);
  static const accentDeep = Color(0xFF6B8F71);
  static const lime = Color(0xFFB8E986);
  static const coral = Color(0xFFFF6B6B);
  static const peach = Color(0xFFFFB4A2);
  static const sky = Color(0xFF7EB8FF);
  static const cream = Color(0xFFFFF3E0);
  static const amber = Color(0xFFFFB74D);
  static const pink = Color(0xFFFF8FAB);
}

class AppRadii {
  static const sm = 14.0;
  static const md = 22.0;
  static const lg = 28.0;
  static const xl = 36.0;
}

class AppShadows {
  static List<BoxShadow> soft = [
    BoxShadow(
      color: AppColors.ink.withValues(alpha: 0.08),
      blurRadius: 24,
      offset: const Offset(0, 12),
    ),
  ];

  static List<BoxShadow> card = [
    BoxShadow(
      color: AppColors.ink.withValues(alpha: 0.06),
      blurRadius: 18,
      offset: const Offset(0, 8),
    ),
  ];

  static List<BoxShadow> fab = [
    BoxShadow(
      color: AppColors.accentDeep.withValues(alpha: 0.45),
      blurRadius: 20,
      offset: const Offset(0, 10),
    ),
  ];
}

class AppTheme {
  static ThemeData get light {
    const scheme = ColorScheme.light(
      primary: AppColors.accentDeep,
      secondary: AppColors.lime,
      surface: AppColors.card,
      onSurface: AppColors.ink,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.bg,
      appBarTheme: const AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: Colors.transparent,
        foregroundColor: AppColors.ink,
      ),
      cardTheme: CardThemeData(
        color: AppColors.card,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadii.md)),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.card,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.lg),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      ),
    );
  }
}

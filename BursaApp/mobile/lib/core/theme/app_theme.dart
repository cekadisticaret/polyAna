import 'package:flutter/material.dart';

class AppColors {
  static const bg = Color(0xFFDCE8DC);
  static const bgSoft = Color(0xFFE8F0E6);
  static const card = Color(0xFFFFFFFF);
  static const ink = Color(0xFF142018);
  static const muted = Color(0xFF5F6F64);
  static const accent = Color(0xFFC9B89A);
  static const accentDeep = Color(0xFF8FA88A);
  static const coral = Color(0xFFFF7A6E);
  static const sky = Color(0xFF7EB8FF);
}

class AppTheme {
  static ThemeData get light {
    const scheme = ColorScheme.light(
      primary: AppColors.accentDeep,
      secondary: AppColors.accent,
      surface: AppColors.card,
      onSurface: AppColors.ink,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.bg,
      fontFamily: 'SF Pro Display',
      appBarTheme: const AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: Colors.transparent,
        foregroundColor: AppColors.ink,
      ),
      cardTheme: CardThemeData(
        color: AppColors.card,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: AppColors.ink,
        foregroundColor: Colors.white,
        elevation: 8,
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: Colors.transparent,
        selectedItemColor: AppColors.ink,
        unselectedItemColor: AppColors.muted,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),
    );
  }
}

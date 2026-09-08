import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';
import '../shell/main_shell.dart';

class BursaApp extends StatelessWidget {
  const BursaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BursaApp',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: const MainShell(),
    );
  }
}

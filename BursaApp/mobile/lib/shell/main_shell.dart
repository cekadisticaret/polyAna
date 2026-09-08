import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth/auth_store.dart';
import '../screens/create_event_screen.dart';
import '../screens/explore_screen.dart';
import '../screens/feed_screen.dart';
import '../screens/food_screen.dart';
import '../screens/profile_screen.dart';
import '../screens/visit_screen.dart';
import '../widgets/app_header.dart';
import '../widgets/floating_tab_bar.dart';
import '../widgets/login_sheet.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _tab = 0;

  late final _pages = [
    const FeedScreen(),
    const ExploreScreen(),
    const VisitScreen(),
    const FoodScreen(),
    const ProfileScreen(),
  ];

  void _openCreate() {
    requireAuth(context, () {
      Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => const CreateEventScreen()),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    context.watch<AuthStore>();
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: AppHeader(
                showGreeting: _tab == 0,
                onProfileTap: () => setState(() => _tab = 4),
              ),
            ),
            Expanded(child: _pages[_tab]),
          ],
        ),
      ),
      bottomNavigationBar: FloatingTabBar(
        index: _tab,
        onChanged: (i) => setState(() => _tab = i),
        onCreateTap: _openCreate,
      ),
    );
  }
}

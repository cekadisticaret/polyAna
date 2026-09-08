import 'package:flutter/material.dart';

import '../screens/explore_screen.dart';
import '../screens/feed_screen.dart';
import '../screens/food_screen.dart';
import '../screens/profile_screen.dart';
import '../screens/visit_screen.dart';
import '../widgets/app_header.dart';
import '../widgets/floating_tab_bar.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _tab = 0;
  late final _pages = [
    FeedScreen(onProfileTap: () => setState(() => _tab = 4)),
    ExploreScreen(onProfileTap: () => setState(() => _tab = 4)),
    VisitScreen(onProfileTap: () => setState(() => _tab = 4)),
    FoodScreen(onProfileTap: () => setState(() => _tab = 4)),
    ProfileScreen(onProfileTap: () => setState(() => _tab = 4)),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: AppHeader(
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
      ),
    );
  }
}

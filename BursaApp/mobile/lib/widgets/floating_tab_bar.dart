import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';

class FloatingTabBar extends StatelessWidget {
  const FloatingTabBar({
    super.key,
    required this.index,
    required this.onChanged,
    required this.onCreateTap,
  });

  final int index;
  final ValueChanged<int> onChanged;
  final VoidCallback onCreateTap;

  static const _left = [
    _TabItem(Icons.home_rounded, 'Akış'),
    _TabItem(Icons.map_rounded, 'Yakınım'),
  ];
  static const _right = [
    _TabItem(Icons.landscape_rounded, 'Gez'),
    _TabItem(Icons.restaurant_rounded, 'Lezzet'),
    _TabItem(Icons.person_rounded, 'Profil'),
  ];

  int _toPageIndex(int visual) {
    if (visual < 2) return visual;
    return visual - 1;
  }

  int _fromPageIndex(int page) {
    if (page < 2) return page;
    return page + 1;
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.paddingOf(context).bottom;
    final visualIndex = _fromPageIndex(index);

    return Padding(
      padding: EdgeInsets.fromLTRB(14, 0, 14, 8 + bottom),
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.topCenter,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 18),
            padding: const EdgeInsets.fromLTRB(8, 12, 8, 10),
            decoration: BoxDecoration(
              color: AppColors.nav,
              borderRadius: BorderRadius.circular(AppRadii.lg),
              boxShadow: AppShadows.soft,
            ),
            child: Row(
              children: [
                ...List.generate(2, (i) => _navItem(i, visualIndex, onChanged)),
                const Expanded(child: SizedBox(width: 56)),
                ...List.generate(3, (i) {
                  final vi = i + 3;
                  return _navItem(vi, visualIndex, (v) => onChanged(_toPageIndex(v)));
                }),
              ],
            ),
          ),
          Positioned(
            top: 0,
            child: GestureDetector(
              onTap: onCreateTap,
              child: Container(
                width: 58,
                height: 58,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [AppColors.lime, Color(0xFF9AD86A)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  shape: BoxShape.circle,
                  boxShadow: AppShadows.fab,
                  border: Border.all(color: Colors.white, width: 3),
                ),
                child: const Icon(Icons.add_rounded, color: AppColors.ink, size: 30),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _navItem(int visualIndex, int activeVisual, ValueChanged<int> tap) {
    final items = visualIndex < 2 ? _left : _right;
    final item = items[visualIndex < 2 ? visualIndex : visualIndex - 3];
    final on = visualIndex == activeVisual;
    return Expanded(
      child: GestureDetector(
        onTap: () => tap(visualIndex),
        behavior: HitTestBehavior.opaque,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(item.icon, size: 22, color: on ? AppColors.lime : Colors.white.withValues(alpha: 0.55)),
            const SizedBox(height: 2),
            Text(
              item.label,
              style: TextStyle(
                fontSize: 9,
                fontWeight: FontWeight.w700,
                color: on ? AppColors.lime : Colors.white.withValues(alpha: 0.55),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TabItem {
  const _TabItem(this.icon, this.label);
  final IconData icon;
  final String label;
}

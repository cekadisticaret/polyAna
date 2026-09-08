import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';

class FloatingTabBar extends StatelessWidget {
  const FloatingTabBar({
    super.key,
    required this.index,
    required this.onChanged,
  });

  final int index;
  final ValueChanged<int> onChanged;

  static const _items = [
    _TabItem(Icons.home_rounded, 'Akış'),
    _TabItem(Icons.near_me_rounded, 'Yakınım'),
    _TabItem(Icons.landscape_rounded, 'Gez'),
    _TabItem(Icons.restaurant_rounded, 'Lezzet'),
    _TabItem(Icons.person_rounded, 'Profil'),
  ];

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.paddingOf(context).bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 0, 16, 10 + bottom),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
        decoration: BoxDecoration(
          color: AppColors.card.withValues(alpha: 0.96),
          borderRadius: BorderRadius.circular(28),
          boxShadow: [
            BoxShadow(
              color: AppColors.ink.withValues(alpha: 0.12),
              blurRadius: 24,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Row(
          children: List.generate(_items.length, (i) {
            final item = _items[i];
            final on = i == index;
            return Expanded(
              child: GestureDetector(
                onTap: () => onChanged(i),
                behavior: HitTestBehavior.opaque,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: on ? AppColors.bgSoft : Colors.transparent,
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: Icon(
                        item.icon,
                        size: 22,
                        color: on ? AppColors.ink : AppColors.muted,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      item.label,
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: on ? FontWeight.w800 : FontWeight.w600,
                        color: on ? AppColors.ink : AppColors.muted,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
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

import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';

class CategoryPills extends StatelessWidget {
  const CategoryPills({
    super.key,
    required this.items,
    required this.selected,
    required this.onSelected,
  });

  final List<(String, String)> items;
  final String selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 42,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: items.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final (key, label) = items[i];
          final on = key == selected;
          return GestureDetector(
            onTap: () => onSelected(key),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: on ? AppColors.nav : AppColors.card,
                borderRadius: BorderRadius.circular(99),
                boxShadow: on ? null : AppShadows.card,
                border: on ? null : Border.all(color: AppColors.ink.withValues(alpha: 0.05)),
              ),
              child: Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 13,
                  color: on ? Colors.white : AppColors.muted,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

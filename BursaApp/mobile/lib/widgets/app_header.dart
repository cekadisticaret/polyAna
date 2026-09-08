import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth/auth_store.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';
import 'notifications_screen.dart';

class AppHeader extends StatelessWidget {
  const AppHeader({super.key, this.onProfileTap, this.showBell = true});

  final VoidCallback? onProfileTap;
  final bool showBell;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthStore>();
    final user = auth.user;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 8, 4, 12),
      child: Row(
        children: [
          const Text(
            'BursaApp',
            style: TextStyle(
              fontSize: 26,
              fontWeight: FontWeight.w900,
              letterSpacing: -0.8,
              color: AppColors.ink,
            ),
          ),
          const Spacer(),
          if (showBell)
            IconButton(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => const NotificationsScreen()),
                );
              },
              icon: Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: AppColors.card,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.ink.withValues(alpha: 0.08),
                      blurRadius: 16,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: const Icon(Icons.notifications_none_rounded, color: AppColors.ink),
              ),
            ),
          const SizedBox(width: 4),
          GestureDetector(
            onTap: onProfileTap,
            child: _Avatar(url: user?.avatarUrl, name: user?.name ?? 'B'),
          ),
        ],
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.url, required this.name});
  final String? url;
  final String name;

  @override
  Widget build(BuildContext context) {
    final letter = name.isNotEmpty ? name[0].toUpperCase() : 'B';
    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.accent, width: 2),
        boxShadow: [
          BoxShadow(
            color: AppColors.ink.withValues(alpha: 0.08),
            blurRadius: 12,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: url != null && url!.isNotEmpty
          ? CachedNetworkImage(
              imageUrl: url!.startsWith('http') ? url! : '${AppConfig.siteBase}$url',
              fit: BoxFit.cover,
              errorWidget: (_, __, ___) => _letter(letter),
            )
          : _letter(letter),
    );
  }

  Widget _letter(String letter) => ColoredBox(
        color: AppColors.accentDeep,
        child: Center(
          child: Text(
            letter,
            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 18),
          ),
        ),
      );
}

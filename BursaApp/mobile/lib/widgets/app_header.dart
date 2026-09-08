import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth/auth_store.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';
import 'notifications_screen.dart';

class AppHeader extends StatelessWidget {
  const AppHeader({
    super.key,
    this.onProfileTap,
    this.showGreeting = false,
  });

  final VoidCallback? onProfileTap;
  final bool showGreeting;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthStore>();
    final user = auth.user;
    final first = (user?.name ?? 'Misafir').split(' ').first;

    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 6, 4, 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (showGreeting) ...[
                  Text(
                    'Merhaba, $first 👋',
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.muted),
                  ),
                  const SizedBox(height: 2),
                ],
                const Text(
                  'BursaApp',
                  style: TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -0.8,
                    color: AppColors.ink,
                  ),
                ),
              ],
            ),
          ),
          _RoundBtn(
            icon: Icons.notifications_none_rounded,
            badge: true,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const NotificationsScreen()),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: onProfileTap,
            child: _Avatar(url: user?.avatarUrl, name: user?.name ?? 'B'),
          ),
        ],
      ),
    );
  }
}

class _RoundBtn extends StatelessWidget {
  const _RoundBtn({required this.icon, this.badge = false, this.onTap});
  final IconData icon;
  final bool badge;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: AppColors.card,
              shape: BoxShape.circle,
              boxShadow: AppShadows.card,
            ),
            child: Icon(icon, color: AppColors.ink),
          ),
          if (badge)
            Positioned(
              top: 8,
              right: 10,
              child: Container(
                width: 8,
                height: 8,
                decoration: const BoxDecoration(color: AppColors.coral, shape: BoxShape.circle),
              ),
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
      width: 46,
      height: 46,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.lime, width: 2.5),
        boxShadow: AppShadows.card,
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
          child: Text(letter, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 18)),
        ),
      );
}

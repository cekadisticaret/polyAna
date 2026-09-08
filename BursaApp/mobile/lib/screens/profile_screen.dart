import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';
import '../widgets/login_sheet.dart';
import 'create_event_screen.dart';
import 'leaders_screen.dart';
import 'okey_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  List<MenuGroup> _menu = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadMenu();
  }

  Future<void> _loadMenu() async {
    try {
      final auth = context.read<AuthStore>();
      final groups = await auth.api.mobileMenu();
      if (mounted) setState(() => _menu = groups);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthStore>();
    final user = auth.user;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
      children: [
        Column(
          children: [
            CircleAvatar(
              radius: 48,
              backgroundColor: AppColors.accentDeep,
              backgroundImage: user?.avatarUrl != null && user!.avatarUrl.isNotEmpty
                  ? NetworkImage(user.avatarUrl.startsWith('http') ? user.avatarUrl : '${AppConfig.siteBase}${user.avatarUrl}')
                  : null,
              child: user?.avatarUrl.isEmpty != false
                  ? Text(
                      (user?.name ?? 'B').substring(0, 1),
                      style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: Colors.white),
                    )
                  : null,
            ),
            const SizedBox(height: 12),
            Text(user?.name ?? 'Misafir', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
            Text(
              auth.isLoggedIn ? '${user?.points ?? 0} puan · Bursa rehberi' : 'Giriş yap, puan kazan',
              style: const TextStyle(color: AppColors.muted),
            ),
            const SizedBox(height: 12),
            if (auth.isLoggedIn)
              OutlinedButton(onPressed: () => auth.logout(), child: const Text('Çıkış'))
            else
              FilledButton(
                onPressed: () => showLoginSheet(context),
                style: FilledButton.styleFrom(backgroundColor: AppColors.nav, foregroundColor: AppColors.lime),
                child: const Text('Giriş / Kayıt'),
              ),
          ],
        ),
        const SizedBox(height: 20),
        Row(
          children: [
            Expanded(child: _QuickTile(icon: Icons.add_circle, label: 'Etkinlik', color: AppColors.pink, onTap: () => requireAuth(context, () => Navigator.push(context, MaterialPageRoute<void>(builder: (_) => const CreateEventScreen()))))),
            const SizedBox(width: 10),
            Expanded(child: _QuickTile(icon: Icons.emoji_events, label: 'Liderler', color: AppColors.sky, onTap: () => Navigator.push(context, MaterialPageRoute<void>(builder: (_) => const LeadersScreen())))),
            const SizedBox(width: 10),
            Expanded(child: _QuickTile(icon: Icons.grid_view, label: 'Okey', color: AppColors.accentDeep, onTap: () => Navigator.push(context, MaterialPageRoute<void>(builder: (_) => const OkeyScreen())))),
          ],
        ),
        const SizedBox(height: 20),
        if (_loading)
          const Center(child: CircularProgressIndicator())
        else
          ..._menu.map((g) => _MenuBlock(group: g)),
      ],
    );
  }
}

class _QuickTile extends StatelessWidget {
  const _QuickTile({required this.icon, required this.label, required this.color, required this.onTap});
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 18),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.18),
          borderRadius: BorderRadius.circular(AppRadii.md),
        ),
        child: Column(
          children: [
            Icon(icon, color: color),
            const SizedBox(height: 6),
            Text(label, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

class _MenuBlock extends StatelessWidget {
  const _MenuBlock({required this.group});
  final MenuGroup group;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppRadii.lg),
        boxShadow: AppShadows.card,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
            child: Text(group.title, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
          ),
          ...group.items.map(
            (item) => ListTile(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              title: Text(item.label, style: const TextStyle(fontWeight: FontWeight.w600)),
              trailing: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(color: AppColors.bgSoft, borderRadius: BorderRadius.circular(10)),
                child: const Icon(Icons.arrow_forward_ios_rounded, size: 14),
              ),
              onTap: () => launchUrl(Uri.parse('${AppConfig.siteBase}${item.path}'), mode: LaunchMode.externalApplication),
            ),
          ),
        ],
      ),
    );
  }
}

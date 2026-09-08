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
  const ProfileScreen({super.key, this.onProfileTap});
  final VoidCallback? onProfileTap;

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
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      children: [
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: AppColors.card,
            borderRadius: BorderRadius.circular(24),
            boxShadow: [
              BoxShadow(color: AppColors.ink.withValues(alpha: 0.06), blurRadius: 16, offset: const Offset(0, 8)),
            ],
          ),
          child: Row(
            children: [
              _ProfileAvatar(name: user?.name ?? 'Misafir', url: user?.avatarUrl),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      user?.name ?? 'Misafir',
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
                    ),
                    Text(
                      auth.isLoggedIn ? '${user?.points ?? 0} puan' : 'Giriş yap · puan kazan',
                      style: const TextStyle(color: AppColors.muted),
                    ),
                  ],
                ),
              ),
              if (auth.isLoggedIn)
                IconButton(
                  onPressed: () => auth.logout(),
                  icon: const Icon(Icons.logout_rounded),
                )
              else
                TextButton(
                  onPressed: () => showLoginSheet(context),
                  child: const Text('Giriş'),
                ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        _QuickActions(
          onCreateEvent: () {
            requireAuth(context, () {
              Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const CreateEventScreen()));
            });
          },
          onLeaders: () {
            Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const LeadersScreen()));
          },
          onOkey: () {
            Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const OkeyScreen()));
          },
        ),
        const SizedBox(height: 18),
        if (_loading)
          const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
        else
          ..._menu.map((g) => _MenuGroupCard(group: g)),
      ],
    );
  }
}

class _ProfileAvatar extends StatelessWidget {
  const _ProfileAvatar({required this.name, this.url});
  final String name;
  final String? url;

  @override
  Widget build(BuildContext context) {
    return CircleAvatar(
      radius: 34,
      backgroundColor: AppColors.accentDeep,
      backgroundImage: url != null && url!.isNotEmpty
          ? NetworkImage(url!.startsWith('http') ? url! : '${AppConfig.siteBase}$url')
          : null,
      child: url == null || url!.isEmpty
          ? Text(name.isNotEmpty ? name[0] : 'B', style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold))
          : null,
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.onCreateEvent, required this.onLeaders, required this.onOkey});
  final VoidCallback onCreateEvent;
  final VoidCallback onLeaders;
  final VoidCallback onOkey;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _ActionCard(
            icon: Icons.add_circle_outline,
            label: 'Etkinlik\noluştur',
            color: AppColors.coral,
            onTap: onCreateEvent,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _ActionCard(
            icon: Icons.emoji_events_outlined,
            label: 'Lider\nharitası',
            color: AppColors.sky,
            onTap: onLeaders,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _ActionCard(
            icon: Icons.grid_view_rounded,
            label: 'Okey\n4. arayan',
            color: AppColors.accentDeep,
            onTap: onOkey,
          ),
        ),
      ],
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({required this.icon, required this.label, required this.color, required this.onTap});
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Ink(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withValues(alpha: 0.25)),
        ),
        child: Column(
          children: [
            Icon(icon, color: color),
            const SizedBox(height: 8),
            Text(label, textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12, height: 1.2)),
          ],
        ),
      ),
    );
  }
}

class _MenuGroupCard extends StatelessWidget {
  const _MenuGroupCard({required this.group});
  final MenuGroup group;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(22),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
            child: Text(group.title, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
          ),
          ...group.items.map(
            (item) => ListTile(
              title: Text(item.label, style: const TextStyle(fontWeight: FontWeight.w600)),
              trailing: const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
              onTap: () {
                final url = Uri.parse('${AppConfig.siteBase}${item.path}');
                launchUrl(url, mode: LaunchMode.externalApplication);
              },
            ),
          ),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';

class LeadersScreen extends StatefulWidget {
  const LeadersScreen({super.key});

  @override
  State<LeadersScreen> createState() => _LeadersScreenState();
}

class _LeadersScreenState extends State<LeadersScreen> {
  List<LeaderRow> _rows = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final auth = context.read<AuthStore>();
      final rows = await auth.api.weeklyLeaders();
      setState(() => _rows = rows);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Haftanın liderleri')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(colors: [AppColors.sky.withValues(alpha: 0.25), AppColors.accent.withValues(alpha: 0.2)]),
                    borderRadius: BorderRadius.circular(22),
                  ),
                  child: const Text(
                    'En çok puan toplayan üyeler haritada öne çıkar. Etkinlik oluştur, paylaş, puan kazan.',
                    style: TextStyle(height: 1.4),
                  ),
                ),
                const SizedBox(height: 16),
                ..._rows.map((r) {
                  final medal = r.rank <= 3 ? ['🥇', '🥈', '🥉'][r.rank - 1] : '#${r.rank}';
                  return Container(
                    margin: const EdgeInsets.only(bottom: 10),
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: AppColors.card,
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: Row(
                      children: [
                        Text(medal, style: const TextStyle(fontSize: 22)),
                        const SizedBox(width: 10),
                        CircleAvatar(
                          backgroundImage: r.avatarUrl.isNotEmpty
                              ? NetworkImage(r.avatarUrl.startsWith('http') ? r.avatarUrl : '${AppConfig.siteBase}${r.avatarUrl}')
                              : null,
                          child: r.avatarUrl.isEmpty ? Text(r.name[0]) : null,
                        ),
                        const SizedBox(width: 12),
                        Expanded(child: Text(r.name, style: const TextStyle(fontWeight: FontWeight.w800))),
                        Text('${r.points} puan', style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.muted)),
                      ],
                    ),
                  );
                }),
              ],
            ),
    );
  }
}

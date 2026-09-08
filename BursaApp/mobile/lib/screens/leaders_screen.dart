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
  bool _weekly = true;

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

  Color _rankColor(int rank) {
    if (rank == 1) return AppColors.pink;
    if (rank == 2) return AppColors.cream;
    if (rank == 3) return AppColors.amber;
    return AppColors.bgDeep;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bgDeep,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        title: const Text('Lider haritası', style: TextStyle(fontWeight: FontWeight.w900)),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.lime))
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(99),
                  ),
                  child: Row(
                    children: [
                      _ToggleChip(label: 'Haftalık', on: _weekly, onTap: () => setState(() => _weekly = true)),
                      _ToggleChip(label: 'Ay', on: !_weekly, onTap: () => setState(() => _weekly = false)),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                ..._rows.map((r) {
                  final c = _rankColor(r.rank);
                  return Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: Row(
                      children: [
                        Container(
                          width: 56,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          decoration: BoxDecoration(
                            color: c,
                            borderRadius: BorderRadius.circular(18),
                          ),
                          child: Column(
                            children: [
                              const Icon(Icons.emoji_events, size: 18),
                              Text('#${r.rank}', style: const TextStyle(fontWeight: FontWeight.w900)),
                            ],
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Row(
                              children: [
                                CircleAvatar(
                                  backgroundImage: r.avatarUrl.isNotEmpty
                                      ? NetworkImage(r.avatarUrl.startsWith('http') ? r.avatarUrl : '${AppConfig.siteBase}${r.avatarUrl}')
                                      : null,
                                  child: r.avatarUrl.isEmpty ? Text(r.name[0]) : null,
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Text(r.name, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 16)),
                                ),
                                Text('${r.points}', style: const TextStyle(color: AppColors.lime, fontWeight: FontWeight.w900, fontSize: 18)),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              ],
            ),
    );
  }
}

class _ToggleChip extends StatelessWidget {
  const _ToggleChip({required this.label, required this.on, required this.onTap});
  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: on ? Colors.white : Colors.transparent,
            borderRadius: BorderRadius.circular(99),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontWeight: FontWeight.w800,
              color: on ? AppColors.ink : Colors.white.withValues(alpha: 0.8),
            ),
          ),
        ),
      ),
    );
  }
}

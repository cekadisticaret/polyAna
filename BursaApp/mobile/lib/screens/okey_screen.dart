import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/theme/app_theme.dart';

class OkeyScreen extends StatefulWidget {
  const OkeyScreen({super.key});

  @override
  State<OkeyScreen> createState() => _OkeyScreenState();
}

class _OkeyScreenState extends State<OkeyScreen> {
  List<OkeySeek> _rows = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final auth = context.read<AuthStore>();
      final rows = await auth.api.okeySeeking();
      setState(() => _rows = rows);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Okey — 4. arayan')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('İlan verme özelliği yakında')),
          );
        },
        label: const Text('İlan ver'),
        icon: const Icon(Icons.add),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _rows.length,
              itemBuilder: (context, i) {
                final r = _rows[i];
                return Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: AppColors.card,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(r.host, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 17)),
                          const Spacer(),
                          Chip(label: Text(r.ilce), backgroundColor: AppColors.bgSoft),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(r.timeLabel, style: const TextStyle(color: AppColors.muted)),
                      const SizedBox(height: 8),
                      Text(r.note),
                      const SizedBox(height: 10),
                      Text('Min. ${r.pointsMin} puan', style: const TextStyle(fontSize: 12, color: AppColors.muted)),
                      const SizedBox(height: 10),
                      Align(
                        alignment: Alignment.centerRight,
                        child: FilledButton(
                          onPressed: () {},
                          child: const Text('Katıl'),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
    );
  }
}

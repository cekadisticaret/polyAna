import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/theme/app_theme.dart';
import '../widgets/place_list_tile.dart';

class VisitScreen extends StatefulWidget {
  const VisitScreen({super.key, this.onProfileTap});
  final VoidCallback? onProfileTap;

  @override
  State<VisitScreen> createState() => _VisitScreenState();
}

class _VisitScreenState extends State<VisitScreen> {
  List<PlaceItem> _places = [];
  bool _loading = true;
  String? _suggest;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final auth = context.read<AuthStore>();
      final rows = await auth.api.places(category: 'visit', limit: 30);
      setState(() => _places = rows);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _suggestMe() async {
    setState(() {
      _loading = true;
      _suggest = null;
    });
    try {
      final auth = context.read<AuthStore>();
      final res = await auth.api.suggestPlace('Bursa gezilecek yer öner, kısa liste');
      setState(() => _suggest = res['reply']?.toString() ?? res['text']?.toString() ?? 'Öneri hazır');
    } catch (e) {
      setState(() => _suggest = 'Şu an öneri alınamadı. Listeden seçebilirsin.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Gezilecek yerler',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [AppColors.accentDeep, AppColors.accent.withValues(alpha: 0.85)],
                  ),
                  borderRadius: BorderRadius.circular(22),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Bugün ne keşfetsen?', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 18)),
                    const SizedBox(height: 8),
                    FilledButton(
                      onPressed: _loading ? null : _suggestMe,
                      style: FilledButton.styleFrom(
                        backgroundColor: Colors.white,
                        foregroundColor: AppColors.ink,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                      ),
                      child: const Text('Bana yer öner'),
                    ),
                  ],
                ),
              ),
              if (_suggest != null) ...[
                const SizedBox(height: 10),
                Text(_suggest!, style: const TextStyle(color: AppColors.muted, height: 1.4)),
              ],
            ],
          ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: _loading && _places.isEmpty
              ? const Center(child: CircularProgressIndicator())
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  itemCount: _places.length,
                  itemBuilder: (_, i) => PlaceListTile(place: _places[i]),
                ),
        ),
      ],
    );
  }
}

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/theme/app_theme.dart';
import '../widgets/category_pills.dart';
import '../widgets/destination_card.dart';

class FoodScreen extends StatefulWidget {
  const FoodScreen({super.key});

  @override
  State<FoodScreen> createState() => _FoodScreenState();
}

class _FoodScreenState extends State<FoodScreen> {
  static const _sections = [
    ('food', 'Restoran & kafe'),
    ('fun', 'Canlı müzik'),
    ('fun', 'Eğlence'),
  ];

  String _filterKey = 'food';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final auth = context.read<AuthStore>();
      final cat = _filterKey == 'fun2' ? 'fun' : _filterKey;
      final rows = await auth.api.places(category: cat, limit: 24);
      setState(() => _places = rows);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
      children: [
        const Text('Yeme & içme', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
        const SizedBox(height: 12),
        CategoryPills(
          items: const [
            ('food', 'Restoran & kafe'),
            ('live', 'Canlı müzik'),
            ('fun2', 'Eğlence'),
          ],
          selected: _filterKey,
          onSelected: (v) {
            setState(() => _filterKey = v);
            _load();
          },
        ),
        const SizedBox(height: 16),
        if (_loading)
          const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator()))
        else
          ..._places.map(
            (p) => Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: DestinationCard(place: p),
            ),
          ),
      ],
    );
  }
}

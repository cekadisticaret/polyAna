import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/theme/app_theme.dart';
import '../widgets/place_list_tile.dart';

class FoodScreen extends StatefulWidget {
  const FoodScreen({super.key, this.onProfileTap});
  final VoidCallback? onProfileTap;

  @override
  State<FoodScreen> createState() => _FoodScreenState();
}

class _FoodScreenState extends State<FoodScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  final _data = <String, List<PlaceItem>>{};
  final _loading = <String, bool>{};

  static const _sections = [
    ('food', 'Restoran & kafe', 'cafe'),
    ('food', 'Canlı müzik', 'live'),
    ('fun', 'Eğlence', null),
  ];

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    _tabs.addListener(() {
      if (!_tabs.indexIsChanging) _ensure(_tabs.index);
    });
    _ensure(0);
  }

  Future<void> _ensure(int index) async {
    final key = 's$index';
    if (_data.containsKey(key)) return;
    setState(() => _loading[key] = true);
    try {
      final auth = context.read<AuthStore>();
      final sec = _sections[index];
      final rows = await auth.api.places(
        category: sec.$1,
        sub: sec.$3,
        limit: 30,
      );
      setState(() => _data[key] = rows);
    } finally {
      if (mounted) setState(() => _loading[key] = false);
    }
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16),
          child: Text(
            'Yeme & içme',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900),
          ),
        ),
        TabBar(
          controller: _tabs,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          labelColor: AppColors.ink,
          unselectedLabelColor: AppColors.muted,
          indicatorColor: AppColors.accentDeep,
          tabs: _sections.map((s) => Tab(text: s.$2)).toList(),
        ),
        Expanded(
          child: TabBarView(
            controller: _tabs,
            children: List.generate(3, (i) {
              final key = 's$i';
              final rows = _data[key] ?? [];
              if (_loading[key] == true && rows.isEmpty) {
                return const Center(child: CircularProgressIndicator());
              }
              return ListView.builder(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                itemCount: rows.length,
                itemBuilder: (_, j) => PlaceListTile(place: rows[j]),
              );
            }),
          ),
        ),
      ],
    );
  }
}

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';
import '../widgets/destination_card.dart';

class VisitScreen extends StatefulWidget {
  const VisitScreen({super.key});

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
      final rows = await auth.api.places(category: 'visit', limit: 24);
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
      final res = await auth.api.suggestPlace('Bursa gezilecek 3 yer öner, kısa');
      setState(() => _suggest = res['reply']?.toString() ?? res['text']?.toString() ?? 'Harika rotalar hazır!');
    } catch (_) {
      setState(() => _suggest = 'Şimdilik listeden seç — yakında AI önerisi.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final featured = _places.isNotEmpty ? _places.first : null;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
      children: [
        const Text('Gezilecek yerler', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
        const SizedBox(height: 14),
        if (featured != null)
          _CircularHero(
            place: featured,
            onSuggest: _loading ? null : _suggestMe,
          ),
        if (_suggest != null) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.card,
              borderRadius: BorderRadius.circular(AppRadii.lg),
              boxShadow: AppShadows.card,
            ),
            child: Text(_suggest!, style: const TextStyle(height: 1.45)),
          ),
        ],
        const SizedBox(height: 18),
        const Text('Popüler', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 17)),
        const SizedBox(height: 10),
        if (_loading && _places.isEmpty)
          const Center(child: Padding(padding: EdgeInsets.all(32), child: CircularProgressIndicator()))
        else
          ..._places.skip(1).map((p) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: DestinationCard(place: p),
              )),
      ],
    );
  }
}

class _CircularHero extends StatelessWidget {
  const _CircularHero({required this.place, this.onSuggest});
  final PlaceItem place;
  final VoidCallback? onSuggest;

  @override
  Widget build(BuildContext context) {
    final img = place.imgUrl;
    return Column(
      children: [
        Container(
          width: 260,
          height: 260,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            boxShadow: AppShadows.soft,
            border: Border.all(color: Colors.white, width: 6),
          ),
          clipBehavior: Clip.antiAlias,
          child: img.isNotEmpty
              ? CachedNetworkImage(
                  imageUrl: img.startsWith('http') ? img : '${AppConfig.siteBase}$img',
                  fit: BoxFit.cover,
                )
              : ColoredBox(color: AppColors.bgDeep),
        ),
        const SizedBox(height: 16),
        Text(place.title, textAlign: TextAlign.center, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900)),
        Text(place.ilce, style: const TextStyle(color: AppColors.muted)),
        const SizedBox(height: 14),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: onSuggest,
            icon: const Icon(Icons.auto_awesome_rounded),
            label: const Text('Bana yer öner'),
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.nav,
              foregroundColor: AppColors.lime,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadii.lg)),
            ),
          ),
        ),
      ],
    );
  }
}

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';
import '../widgets/category_pills.dart';

class ExploreScreen extends StatefulWidget {
  const ExploreScreen({super.key});

  @override
  State<ExploreScreen> createState() => _ExploreScreenState();
}

class _ExploreScreenState extends State<ExploreScreen> {
  static const _filters = [
    ('food', 'Kafe'),
    ('visit', 'Gez'),
    ('fun', 'Eğlence'),
    ('concert', 'Konser'),
  ];

  String _filter = 'food';
  List<PlaceItem> _places = [];
  PlaceItem? _selected;
  LatLng _center = const LatLng(40.1885, 29.0610);
  bool _loading = true;
  final _mapController = MapController();

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await _locate();
    await _loadPlaces();
  }

  Future<void> _locate() async {
    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
      if (perm == LocationPermission.deniedForever || perm == LocationPermission.denied) return;
      final pos = await Geolocator.getCurrentPosition();
      setState(() => _center = LatLng(pos.latitude, pos.longitude));
      _mapController.move(_center, 14);
    } catch (_) {}
  }

  Future<void> _loadPlaces() async {
    setState(() => _loading = true);
    try {
      final auth = context.read<AuthStore>();
      final nearby = await auth.api.nearby(lat: _center.latitude, lng: _center.longitude, r: 2500);
      setState(() {
        _places = nearby.where((p) => p.category == _filter).toList();
        _selected = _places.isNotEmpty ? _places.first : null;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned.fill(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppRadii.lg),
            child: FlutterMap(
              mapController: _mapController,
              options: MapOptions(
                initialCenter: _center,
                initialZoom: 13,
                onTap: (_, __) => setState(() => _selected = null),
              ),
              children: [
                TileLayer(
                  urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  userAgentPackageName: 'com.bursaapp.mobile',
                ),
                MarkerLayer(
                  markers: [
                    Marker(
                      point: _center,
                      width: 36,
                      height: 36,
                      child: Container(
                        decoration: BoxDecoration(
                          color: AppColors.lime,
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 3),
                          boxShadow: AppShadows.fab,
                        ),
                        child: const Icon(Icons.person_pin_circle, color: AppColors.ink, size: 20),
                      ),
                    ),
                    ..._places.where((p) => p.lat != null && p.lng != null).map((p) {
                      final sel = _selected?.slug == p.slug;
                      return Marker(
                        point: LatLng(p.lat!, p.lng!),
                        width: sel ? 44 : 34,
                        height: sel ? 44 : 34,
                        child: GestureDetector(
                          onTap: () => setState(() => _selected = p),
                          child: Container(
                            decoration: BoxDecoration(
                              color: sel ? AppColors.coral : AppColors.nav,
                              shape: BoxShape.circle,
                              border: Border.all(color: Colors.white, width: 2),
                            ),
                            child: Icon(Icons.place, color: Colors.white, size: sel ? 22 : 18),
                          ),
                        ),
                      );
                    }),
                  ],
                ),
              ],
            ),
          ),
        ),
        Positioned(
          top: 8,
          left: 16,
          right: 16,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: AppColors.card.withValues(alpha: 0.94),
                  borderRadius: BorderRadius.circular(AppRadii.md),
                  boxShadow: AppShadows.card,
                ),
                child: const Row(
                  children: [
                    Icon(Icons.location_on_rounded, color: AppColors.coral, size: 18),
                    SizedBox(width: 6),
                    Text('Çevremde ne var?', style: TextStyle(fontWeight: FontWeight.w900)),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              CategoryPills(
                items: _filters,
                selected: _filter,
                onSelected: (v) {
                  setState(() => _filter = v);
                  _loadPlaces();
                },
              ),
            ],
          ),
        ),
        if (_loading)
          const Center(child: CircularProgressIndicator()),
        if (_selected != null)
          Positioned(
            left: 16,
            right: 16,
            bottom: 12,
            child: _PlaceSheet(
              place: _selected!,
              onRoute: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Rota oluşturuluyor…')),
                );
              },
            ),
          ),
      ],
    );
  }
}

class _PlaceSheet extends StatelessWidget {
  const _PlaceSheet({required this.place, required this.onRoute});
  final PlaceItem place;
  final VoidCallback onRoute;

  @override
  Widget build(BuildContext context) {
    final img = place.imgUrl;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppRadii.lg),
        boxShadow: AppShadows.soft,
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: SizedBox(
              width: 72,
              height: 72,
              child: img.isNotEmpty
                  ? CachedNetworkImage(
                      imageUrl: img.startsWith('http') ? img : '${AppConfig.siteBase}$img',
                      fit: BoxFit.cover,
                    )
                  : ColoredBox(color: AppColors.bgSoft, child: Icon(Icons.store, color: AppColors.muted.withValues(alpha: 0.4))),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(place.title, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
                Text(place.ilce, style: const TextStyle(color: AppColors.muted, fontSize: 12)),
              ],
            ),
          ),
          FilledButton(
            onPressed: onRoute,
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.nav,
              foregroundColor: AppColors.lime,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
            child: const Icon(Icons.route_rounded),
          ),
        ],
      ),
    );
  }
}

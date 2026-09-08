import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/theme/app_theme.dart';
import '../widgets/place_list_tile.dart';

class ExploreScreen extends StatefulWidget {
  const ExploreScreen({super.key, this.onProfileTap});
  final VoidCallback? onProfileTap;

  @override
  State<ExploreScreen> createState() => _ExploreScreenState();
}

class _ExploreScreenState extends State<ExploreScreen> {
  static const _filters = [
    ('food', 'Kafe & restoran'),
    ('visit', 'Gezilecek'),
    ('fun', 'Eğlence'),
    ('concert', 'Konser'),
  ];

  String _filter = 'food';
  List<PlaceItem> _places = [];
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
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
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
      final nearby = await auth.api.nearby(lat: _center.latitude, lng: _center.longitude, r: 2000);
      setState(() {
        _places = nearby.where((p) => _filter.isEmpty || p.category == _filter || (_filter == 'food' && p.category == 'food')).toList();
        if (_filter != 'food') {
          _places = nearby.where((p) => p.category == _filter).toList();
        }
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Harita verisi alınamadı: $e')));
      }
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
                'Çevremde ne var?',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: AppColors.ink),
              ),
              const SizedBox(height: 4),
              const Text('Haritada keşfet, rota oluştur', style: TextStyle(color: AppColors.muted)),
              const SizedBox(height: 12),
              SizedBox(
                height: 40,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: _filters.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (context, i) {
                    final f = _filters[i];
                    final on = f.$1 == _filter;
                    return FilterChip(
                      label: Text(f.$2),
                      selected: on,
                      onSelected: (_) {
                        setState(() => _filter = f.$1);
                        _loadPlaces();
                      },
                      backgroundColor: AppColors.card,
                      selectedColor: AppColors.accent,
                      labelStyle: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: on ? AppColors.ink : AppColors.muted,
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        Expanded(
          flex: 5,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(24),
              child: FlutterMap(
                mapController: _mapController,
                options: MapOptions(initialCenter: _center, initialZoom: 13),
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
                        child: const Icon(Icons.my_location, color: AppColors.sky, size: 32),
                      ),
                      ..._places.where((p) => p.lat != null && p.lng != null).map(
                            (p) => Marker(
                              point: LatLng(p.lat!, p.lng!),
                              width: 34,
                              height: 34,
                              child: const Icon(Icons.location_on, color: AppColors.coral, size: 30),
                            ),
                          ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Rota planlayıcı — seçili mekanlarla yakında')),
                );
              },
              icon: const Icon(Icons.route_rounded),
              label: const Text('Rota oluştur'),
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.ink,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
              ),
            ),
          ),
        ),
        Expanded(
          flex: 4,
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  itemCount: _places.length,
                  itemBuilder: (context, i) => PlaceListTile(place: _places[i]),
                ),
        ),
      ],
    );
  }
}

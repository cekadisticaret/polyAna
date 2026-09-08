import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../core/api/models.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';

class DestinationCard extends StatelessWidget {
  const DestinationCard({super.key, required this.place, this.onTap});
  final PlaceItem place;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final img = place.imgUrl;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 190,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppRadii.lg),
          boxShadow: AppShadows.card,
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (img.isNotEmpty)
              CachedNetworkImage(
                imageUrl: img.startsWith('http') ? img : '${AppConfig.siteBase}$img',
                fit: BoxFit.cover,
              )
            else
              Container(color: AppColors.bgSoft),
            Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.transparent, AppColors.ink.withValues(alpha: 0.8)],
                ),
              ),
            ),
            Positioned(
              top: 12,
              right: 12,
              child: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: AppColors.card.withValues(alpha: 0.9),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.favorite_border, size: 18),
              ),
            ),
            Positioned(
              left: 16,
              right: 16,
              bottom: 14,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(place.title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 18)),
                  Row(
                    children: [
                      const Icon(Icons.place, color: AppColors.lime, size: 14),
                      const SizedBox(width: 4),
                      Text(place.ilce, style: TextStyle(color: Colors.white.withValues(alpha: 0.9), fontSize: 12)),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class PlaceListTile extends StatelessWidget {
  const PlaceListTile({super.key, required this.place});
  final PlaceItem place;

  @override
  Widget build(BuildContext context) => DestinationCard(place: place);
}

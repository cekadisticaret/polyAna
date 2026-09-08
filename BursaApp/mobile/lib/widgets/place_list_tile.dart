import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../core/api/models.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';

class PlaceListTile extends StatelessWidget {
  const PlaceListTile({super.key, required this.place});
  final PlaceItem place;

  @override
  Widget build(BuildContext context) {
    final img = place.imgUrl;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: AppColors.ink.withValues(alpha: 0.05),
            blurRadius: 12,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: SizedBox(
              width: 64,
              height: 64,
              child: img.isNotEmpty
                  ? CachedNetworkImage(
                      imageUrl: img.startsWith('http') ? img : '${AppConfig.siteBase}$img',
                      fit: BoxFit.cover,
                    )
                  : ColoredBox(
                      color: AppColors.bgSoft,
                      child: Icon(Icons.place, color: AppColors.muted.withValues(alpha: 0.5)),
                    ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(place.title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                if (place.ilce.isNotEmpty)
                  Text(place.ilce, style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                if (place.blurb.isNotEmpty)
                  Text(
                    place.blurb,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12, height: 1.3),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

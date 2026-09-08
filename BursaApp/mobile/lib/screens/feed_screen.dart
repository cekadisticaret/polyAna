import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';
import '../widgets/login_sheet.dart';

class FeedScreen extends StatefulWidget {
  const FeedScreen({super.key, this.onProfileTap});
  final VoidCallback? onProfileTap;

  @override
  State<FeedScreen> createState() => _FeedScreenState();
}

class _FeedScreenState extends State<FeedScreen> {
  final _items = <Object>[];
  List<EventItem> _events = [];
  bool _loading = true;
  bool _hasMore = false;
  int _offset = 0;

  @override
  void initState() {
    super.initState();
    _load(refresh: true);
  }

  Future<void> _load({bool refresh = false}) async {
    if (refresh) {
      _offset = 0;
      _items.clear();
    }
    setState(() => _loading = true);
    try {
      final auth = context.read<AuthStore>();
      final res = await auth.api.feed(offset: _offset);
      _events = res.events;
      _hasMore = res.hasMore;
      var eventIdx = 0;
      for (var i = 0; i < res.feed.length; i++) {
        _items.add(res.feed[i]);
        if ((i + 1) % 3 == 0 && eventIdx < _events.length) {
          _items.add(_events[eventIdx++]);
        }
      }
      _offset += res.feed.length;
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Akış yüklenemedi: $e')));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _like(FeedItem item) async {
    requireAuth(context, () async {
      try {
        final auth = context.read<AuthStore>();
        final r = await auth.api.toggleLike(item.id);
        setState(() {
          item.liked = r.liked;
          item.likes = r.likes;
        });
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () => _load(refresh: true),
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        itemCount: _items.length + (_loading ? 1 : 0) + (_hasMore && !_loading ? 1 : 0),
        itemBuilder: (context, i) {
          if (_loading && i == 0 && _items.isEmpty) {
            return const Padding(
              padding: EdgeInsets.all(48),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          final base = _loading && _items.isEmpty ? i - 1 : i;
          if (base >= _items.length) {
            return TextButton(
              onPressed: () => _load(),
              child: const Text('Daha fazla yükle'),
            );
          }
          final item = _items[base];
          if (item is EventItem) {
            return _EventCard(event: item);
          }
          return _FeedCard(item: item as FeedItem, onLike: () => _like(item as FeedItem));
        },
      ),
    );
  }
}

class _FeedCard extends StatelessWidget {
  const _FeedCard({required this.item, required this.onLike});
  final FeedItem item;
  final VoidCallback onLike;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: AppColors.ink.withValues(alpha: 0.06),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 20,
                backgroundColor: AppColors.accentDeep,
                child: Text(
                  item.user.name.isNotEmpty ? item.user.name[0] : 'Ü',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.user.name, style: const TextStyle(fontWeight: FontWeight.w800)),
                    Text('${item.user.handle} · ${item.ago}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                  ],
                ),
              ),
            ],
          ),
          if (item.body.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(item.body, style: const TextStyle(height: 1.45)),
          ],
          if (item.images.isNotEmpty) ...[
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(18),
              child: AspectRatio(
                aspectRatio: 16 / 10,
                child: CachedNetworkImage(
                  imageUrl: item.images.first.startsWith('http')
                      ? item.images.first
                      : '${AppConfig.siteBase}${item.images.first}',
                  fit: BoxFit.cover,
                ),
              ),
            ),
          ],
          if (item.placeTitle != null) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppColors.bgSoft,
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                children: [
                  const Icon(Icons.place_outlined, size: 16, color: AppColors.muted),
                  const SizedBox(width: 6),
                  Expanded(child: Text(item.placeTitle!, style: const TextStyle(fontWeight: FontWeight.w700))),
                ],
              ),
            ),
          ],
          const SizedBox(height: 12),
          Row(
            children: [
              _ActionChip(
                icon: item.liked ? Icons.favorite : Icons.favorite_border,
                label: '${item.likes}',
                onTap: onLike,
              ),
              const SizedBox(width: 8),
              _ActionChip(
                icon: Icons.chat_bubble_outline,
                label: '${item.comments}',
                onTap: () => requireAuth(context, () {}),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ActionChip extends StatelessWidget {
  const _ActionChip({required this.icon, required this.label, required this.onTap});
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(99),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: AppColors.bgSoft,
          borderRadius: BorderRadius.circular(99),
        ),
        child: Row(
          children: [
            Icon(icon, size: 18, color: AppColors.ink),
            const SizedBox(width: 4),
            Text(label, style: const TextStyle(fontWeight: FontWeight.w700)),
          ],
        ),
      ),
    );
  }
}

class _EventCard extends StatelessWidget {
  const _EventCard({required this.event});
  final EventItem event;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.coral.withValues(alpha: 0.15), AppColors.sky.withValues(alpha: 0.12)],
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppColors.coral.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: AppColors.card,
              borderRadius: BorderRadius.circular(16),
            ),
            clipBehavior: Clip.antiAlias,
            child: event.imgUrl.isNotEmpty
                ? CachedNetworkImage(
                    imageUrl: event.imgUrl.startsWith('http') ? event.imgUrl : '${AppConfig.siteBase}${event.imgUrl}',
                    fit: BoxFit.cover,
                  )
                : const Icon(Icons.event, color: AppColors.coral),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Yaklaşan etkinlik', style: TextStyle(color: AppColors.coral.withValues(alpha: 0.9), fontWeight: FontWeight.w800, fontSize: 11)),
                Text(event.title, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16)),
                Text('${event.whenLabel} · ${event.startsAtLabel}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api/models.dart';
import '../core/auth/auth_store.dart';
import '../core/config.dart';
import '../core/theme/app_theme.dart';
import '../widgets/category_pills.dart';
import '../widgets/login_sheet.dart';

class FeedScreen extends StatefulWidget {
  const FeedScreen({super.key});

  @override
  State<FeedScreen> createState() => _FeedScreenState();
}

class _FeedScreenState extends State<FeedScreen> {
  final _items = <Object>[];
  List<EventItem> _events = [];
  bool _loading = true;
  bool _hasMore = false;
  int _offset = 0;
  String _chip = 'all';

  static const _chips = [
    ('all', 'Tümü'),
    ('event', 'Etkinlik'),
    ('food', 'Lezzet'),
    ('visit', 'Gezi'),
  ];

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
        final post = res.feed[i];
        if (_chip != 'all' && post.kind != 'post') continue;
        _items.add(post);
        if ((i + 1) % 2 == 0 && eventIdx < _events.length) {
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
    final hero = _events.isNotEmpty ? _events.first : null;

    return RefreshIndicator(
      onRefresh: () => _load(refresh: true),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
        children: [
          _SearchBar(),
          const SizedBox(height: 14),
          CategoryPills(
            items: _chips,
            selected: _chip,
            onSelected: (v) {
              setState(() => _chip = v);
              _load(refresh: true);
            },
          ),
          const SizedBox(height: 16),
          if (hero != null) ...[
            _HeroEventCard(event: hero),
            const SizedBox(height: 18),
            const _SectionTitle(title: 'Topluluk akışı'),
            const SizedBox(height: 10),
          ],
          if (_loading && _items.isEmpty)
            const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator()))
          else
            ..._items.map((item) {
              if (item is EventItem) return _EventStrip(event: item);
              return _FeedCard(item: item as FeedItem, onLike: () => _like(item as FeedItem));
            }),
          if (_hasMore && !_loading)
            TextButton(onPressed: () => _load(), child: const Text('Daha fazla')),
        ],
      ),
    );
  }
}

class _SearchBar extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppRadii.lg),
        boxShadow: AppShadows.card,
      ),
      child: Row(
        children: [
          const Icon(Icons.search_rounded, color: AppColors.muted),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'Mekan, etkinlik, mahalle…',
              style: TextStyle(color: AppColors.muted, fontWeight: FontWeight.w600),
            ),
          ),
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: AppColors.nav,
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(Icons.tune_rounded, color: AppColors.lime, size: 20),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title});
  final String title;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900)),
        const Spacer(),
        Text('Tümü', style: TextStyle(color: AppColors.accentDeep, fontWeight: FontWeight.w800, fontSize: 13)),
      ],
    );
  }
}

class _HeroEventCard extends StatelessWidget {
  const _HeroEventCard({required this.event});
  final EventItem event;

  @override
  Widget build(BuildContext context) {
    final img = event.imgUrl;
    return Container(
      height: 220,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppRadii.xl),
        boxShadow: AppShadows.soft,
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
            Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(colors: [AppColors.bgDeep, AppColors.accentDeep]),
              ),
            ),
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Colors.transparent, AppColors.ink.withValues(alpha: 0.75)],
              ),
            ),
          ),
          Positioned(
            left: 18,
            right: 18,
            bottom: 18,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: AppColors.lime,
                    borderRadius: BorderRadius.circular(99),
                  ),
                  child: Text(
                    event.whenLabel.isNotEmpty ? event.whenLabel : 'Yakında',
                    style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 11, color: AppColors.ink),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  event.title,
                  style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w900, height: 1.1),
                ),
                Text(
                  '${event.startsAtLabel}${event.ilce.isNotEmpty ? ' · ${event.ilce}' : ''}',
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 13),
                ),
              ],
            ),
          ),
        ],
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
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppRadii.lg),
        boxShadow: AppShadows.card,
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 14, 14, 0),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 18,
                  backgroundColor: AppColors.accentDeep,
                  child: Text(item.user.name.isNotEmpty ? item.user.name[0] : 'Ü', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item.user.name, style: const TextStyle(fontWeight: FontWeight.w800)),
                      Text('${item.ago} · ${item.user.handle}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(color: AppColors.bgSoft, borderRadius: BorderRadius.circular(99)),
                  child: const Row(
                    children: [
                      Icon(Icons.star_rounded, size: 14, color: AppColors.amber),
                      Text(' 4.8', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (item.images.isNotEmpty)
            Padding(
              padding: const EdgeInsets.all(12),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppRadii.md),
                child: AspectRatio(
                  aspectRatio: 1.1,
                  child: CachedNetworkImage(
                    imageUrl: item.images.first.startsWith('http') ? item.images.first : '${AppConfig.siteBase}${item.images.first}',
                    fit: BoxFit.cover,
                  ),
                ),
              ),
            ),
          if (item.body.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Text(item.body, style: const TextStyle(height: 1.45, fontSize: 15)),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 14),
            child: Row(
              children: [
                _PillAction(icon: item.liked ? Icons.favorite : Icons.favorite_border, label: '${item.likes}', onTap: onLike, accent: AppColors.coral),
                const SizedBox(width: 8),
                _PillAction(icon: Icons.chat_bubble_outline, label: '${item.comments}', onTap: () => requireAuth(context, () {})),
                const Spacer(),
                if (item.placeTitle != null)
                  Text(item.placeTitle!, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.accentDeep)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PillAction extends StatelessWidget {
  const _PillAction({required this.icon, required this.label, required this.onTap, this.accent});
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? accent;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(color: AppColors.bgSoft, borderRadius: BorderRadius.circular(99)),
        child: Row(
          children: [
            Icon(icon, size: 18, color: accent ?? AppColors.ink),
            const SizedBox(width: 4),
            Text(label, style: const TextStyle(fontWeight: FontWeight.w800)),
          ],
        ),
      ),
    );
  }
}

class _EventStrip extends StatelessWidget {
  const _EventStrip({required this.event});
  final EventItem event;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.pink.withValues(alpha: 0.22), AppColors.sky.withValues(alpha: 0.18)],
        ),
        borderRadius: BorderRadius.circular(AppRadii.lg),
        border: Border.all(color: AppColors.pink.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          const Icon(Icons.event_available_rounded, color: AppColors.coral, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(event.title, style: const TextStyle(fontWeight: FontWeight.w900)),
                Text('${event.whenLabel} · ${event.startsAtLabel}', style: const TextStyle(color: AppColors.muted, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

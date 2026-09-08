class AuthUser {
  AuthUser({
    required this.id,
    required this.name,
    required this.displayName,
    required this.avatarUrl,
    required this.points,
    this.email = '',
  });

  final int id;
  final String name;
  final String displayName;
  final String avatarUrl;
  final int points;
  final String email;

  factory AuthUser.fromJson(Map<String, dynamic> j) => AuthUser(
        id: (j['id'] as num?)?.toInt() ?? 0,
        name: j['name']?.toString() ?? 'Üye',
        displayName: j['display_name']?.toString() ?? j['name']?.toString() ?? 'Üye',
        avatarUrl: j['avatar_url']?.toString() ?? '',
        points: (j['loyalty_points'] as num?)?.toInt() ?? 0,
        email: j['email']?.toString() ?? '',
      );
}

class FeedUser {
  FeedUser({required this.name, required this.avatarUrl, required this.handle});
  final String name;
  final String avatarUrl;
  final String handle;

  factory FeedUser.fromJson(Map<String, dynamic>? j) => FeedUser(
        name: j?['name']?.toString() ?? 'Üye',
        avatarUrl: j?['avatar_url']?.toString() ?? '',
        handle: j?['handle']?.toString() ?? '@uye',
      );
}

class FeedItem {
  FeedItem({
    required this.kind,
    required this.id,
    required this.ago,
    required this.user,
    required this.body,
    required this.images,
    required this.likes,
    required this.liked,
    required this.comments,
    this.placeTitle,
    this.placeSlug,
  });

  final String kind;
  final int id;
  final String ago;
  final FeedUser user;
  final String body;
  final List<String> images;
  int likes;
  bool liked;
  final int comments;
  final String? placeTitle;
  final String? placeSlug;

  factory FeedItem.fromJson(Map<String, dynamic> j) {
    final place = j['place'] as Map<String, dynamic>?;
    return FeedItem(
      kind: j['kind']?.toString() ?? 'post',
      id: (j['id'] as num?)?.toInt() ?? 0,
      ago: j['ago']?.toString() ?? '',
      user: FeedUser.fromJson(j['user'] as Map<String, dynamic>?),
      body: j['body']?.toString() ?? '',
      images: (j['images'] as List? ?? []).map((e) => e.toString()).where((e) => e.isNotEmpty).toList(),
      likes: (j['likes'] as num?)?.toInt() ?? 0,
      liked: j['liked'] == true,
      comments: (j['comments'] as num?)?.toInt() ?? 0,
      placeTitle: place?['title']?.toString(),
      placeSlug: place?['slug']?.toString(),
    );
  }
}

class EventItem {
  EventItem({
    required this.title,
    required this.slug,
    required this.whenLabel,
    required this.startsAtLabel,
    required this.imgUrl,
    required this.ilce,
    required this.going,
  });

  final String title;
  final String slug;
  final String whenLabel;
  final String startsAtLabel;
  final String imgUrl;
  final String ilce;
  final int going;

  factory EventItem.fromJson(Map<String, dynamic> j) => EventItem(
        title: j['title']?.toString() ?? 'Etkinlik',
        slug: j['slug']?.toString() ?? '',
        whenLabel: j['when_label']?.toString() ?? '',
        startsAtLabel: j['starts_at_label']?.toString() ?? '',
        imgUrl: j['img_url']?.toString() ?? '',
        ilce: j['ilce']?.toString() ?? '',
        going: (j['going'] as num?)?.toInt() ?? 0,
      );
}

class FeedResponse {
  FeedResponse({required this.feed, required this.events, required this.hasMore});
  final List<FeedItem> feed;
  final List<EventItem> events;
  final bool hasMore;

  factory FeedResponse.fromJson(Map<String, dynamic> j) => FeedResponse(
        feed: (j['feed'] as List? ?? [])
            .map((e) => FeedItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        events: (j['events'] as List? ?? [])
            .map((e) => EventItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        hasMore: j['has_more'] == true,
      );
}

class PlaceItem {
  PlaceItem({
    required this.title,
    required this.slug,
    required this.category,
    required this.ilce,
    required this.blurb,
    required this.imgUrl,
    required this.lat,
    required this.lng,
    required this.subcategory,
  });

  final String title;
  final String slug;
  final String category;
  final String ilce;
  final String blurb;
  final String imgUrl;
  final double? lat;
  final double? lng;
  final String subcategory;

  factory PlaceItem.fromJson(Map<String, dynamic> j) => PlaceItem(
        title: j['title']?.toString() ?? '',
        slug: j['slug']?.toString() ?? '',
        category: j['category']?.toString() ?? '',
        ilce: j['ilce']?.toString() ?? '',
        blurb: j['blurb']?.toString() ?? '',
        imgUrl: j['img_url']?.toString() ?? '',
        lat: (j['lat'] as num?)?.toDouble(),
        lng: (j['lng'] as num?)?.toDouble(),
        subcategory: j['subcategory']?.toString() ?? j['subcategory_label']?.toString() ?? '',
      );
}

class MenuGroup {
  MenuGroup({required this.title, required this.icon, required this.items});
  final String title;
  final String icon;
  final List<MenuLink> items;

  factory MenuGroup.fromJson(Map<String, dynamic> j) => MenuGroup(
        title: j['title']?.toString() ?? '',
        icon: j['icon']?.toString() ?? '',
        items: (j['items'] as List? ?? [])
            .map((e) => MenuLink.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class MenuLink {
  MenuLink({required this.label, required this.path, this.category});
  final String label;
  final String path;
  final String? category;

  factory MenuLink.fromJson(Map<String, dynamic> j) => MenuLink(
        label: j['label']?.toString() ?? '',
        path: j['path']?.toString() ?? '',
        category: j['category']?.toString(),
      );
}

class LeaderRow {
  LeaderRow({required this.rank, required this.name, required this.avatarUrl, required this.points});
  final int rank;
  final String name;
  final String avatarUrl;
  final int points;

  factory LeaderRow.fromJson(Map<String, dynamic> j) {
    final u = j['user'] as Map<String, dynamic>? ?? {};
    return LeaderRow(
      rank: (j['rank'] as num?)?.toInt() ?? 0,
      name: u['name']?.toString() ?? 'Üye',
      avatarUrl: u['avatar_url']?.toString() ?? '',
      points: (u['points'] as num?)?.toInt() ?? 0,
    );
  }
}

class OkeySeek {
  OkeySeek({
    required this.id,
    required this.host,
    required this.ilce,
    required this.timeLabel,
    required this.note,
    required this.pointsMin,
  });

  final int id;
  final String host;
  final String ilce;
  final String timeLabel;
  final String note;
  final int pointsMin;

  factory OkeySeek.fromJson(Map<String, dynamic> j) => OkeySeek(
        id: (j['id'] as num?)?.toInt() ?? 0,
        host: j['host']?.toString() ?? '',
        ilce: j['ilce']?.toString() ?? '',
        timeLabel: j['time_label']?.toString() ?? '',
        note: j['note']?.toString() ?? '',
        pointsMin: (j['points_min'] as num?)?.toInt() ?? 0,
      );
}

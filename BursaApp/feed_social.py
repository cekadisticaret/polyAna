"""Profil feed yardımcıları — post / ziyaret / albüm / yorum birleşik akış."""
from __future__ import annotations

import json
import os
from datetime import datetime

FEED_PAGE_SIZE = 12
FEED_FETCH_CAP = 120
PROFILE_FEED_TABS = frozenset({"recents", "friends", "popular", "mine"})

from catalog import place_public
from models import (
    EventGoing,
    Place,
    PlacePhoto,
    PostLike,
    Review,
    User,
    UserPost,
    UserVisit,
)

EVENT_CATS = ("event", "concert", "theater", "cinema", "family")
# Feed “Yer seç” — gezi/kamp; hastane/market/diş vb. yok
FEED_PICKER_CATS = ("visit", "camp")
_DIR = os.path.dirname(os.path.abspath(__file__))
_VIRTUAL_USERS_JSON = os.path.join(_DIR, "data", "virtual_users.json")
SANAL_EMAIL_SUFFIX = ".sanal@bursaapp.com"  # legacy


def _virtual_user_emails() -> list[str]:
    try:
        with open(_VIRTUAL_USERS_JSON, encoding="utf-8") as f:
            personas = json.load(f)
    except Exception:
        return []
    emails = [p["email"].lower() for p in personas if p.get("email")]
    legacy = [f"{p['slug']}{SANAL_EMAIL_SUFFIX}" for p in personas if p.get("slug")]
    return list(dict.fromkeys(emails + legacy))


def _query_virtual_users(db, *, exclude_id: int | None = None) -> list[User]:
    emails = _virtual_user_emails()
    if not emails:
        return []
    q = db.query(User).filter(User.email.in_(emails))
    if exclude_id:
        q = q.filter(User.id != exclude_id)
    return q.order_by(User.id.asc()).all()


def post_images(post: UserPost) -> list[str]:
    try:
        data = json.loads(post.images_json or "[]")
    except Exception:
        return []
    return [x for x in data if isinstance(x, str) and x][:9]


def set_post_images(post: UserPost, urls: list[str]) -> None:
    post.images_json = json.dumps([u for u in urls if u][:9], ensure_ascii=False)


def _ago(dt: datetime | None) -> str:
    if not dt:
        return ""
    sec = int((datetime.utcnow() - dt).total_seconds())
    if sec < 60:
        return "az önce"
    if sec < 3600:
        return f"{sec // 60} dk önce"
    if sec < 86400:
        return f"{sec // 3600} sa önce"
    if sec < 604800:
        return f"{sec // 86400} gün önce"
    return dt.strftime("%d.%m.%Y")


def _user_card(u: User | None) -> dict:
    if not u:
        return {"id": 0, "name": "Üye", "handle": "@uye", "avatar_url": "", "display_name": "Üye"}
    return {
        "id": u.id,
        "name": u.name or "Üye",
        "handle": u.handle(),
        "avatar_url": u.avatar_url or "",
        "display_name": u.display_name(),
    }


def _place_card(p: Place | None) -> dict | None:
    if not p:
        return None
    d = place_public(p)
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "category": p.category,
        "ilce": p.ilce,
        "path": d.get("path") or f"/yer/{p.slug}",
        "img_url": p.img_url or "",
    }


def sanal_user_ids(db) -> list[int]:
    return [u.id for u in _query_virtual_users(db)]


def suggest_follow_users(db, viewer_id: int, *, limit: int = 3) -> list[dict]:
    """Feed sağ sütun — sanal topluluk üyeleri."""
    rows = _query_virtual_users(db, exclude_id=viewer_id)
    scored: list[tuple[int, User]] = []
    for u in rows:
        posts_n = db.query(UserPost).filter(UserPost.user_id == u.id).count()
        scored.append((posts_n, u))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    out: list[dict] = []
    for posts_n, u in scored[:limit]:
        out.append(
            {
                "id": u.id,
                "name": u.name,
                "handle": u.handle(),
                "avatar_url": u.avatar_url or "",
                "posts": posts_n,
            }
        )
    return out


def build_feed(
    db,
    *,
    viewer: User | None = None,
    owner_id: int | None = None,
    tab: str = "recents",
    limit: int = FEED_PAGE_SIZE,
    offset: int = 0,
    friends_only: bool = False,
) -> tuple[list[dict], bool]:
    """Birleşik feed: post + ziyaret + yorum + foto. (sayfa, has_more) döner."""
    items: list[dict] = []
    liked_ids: set[int] = set()
    if viewer:
        liked_ids = {
            x.post_id
            for x in db.query(PostLike).filter(PostLike.user_id == viewer.id).limit(500).all()
        }

    friend_ids: list[int] | None = sanal_user_ids(db) if friends_only else None
    if friends_only and not friend_ids:
        return [], False

    offset = max(0, offset)
    fetch = min(max((offset + limit) * 2, limit * 4), FEED_FETCH_CAP)

    pq = db.query(UserPost).order_by(UserPost.id.desc())
    if owner_id:
        pq = pq.filter(UserPost.user_id == owner_id)
    elif tab != "mine":
        pq = pq.filter(UserPost.privacy == "public", UserPost.status == "approved")
    if friend_ids is not None:
        pq = pq.filter(UserPost.user_id.in_(friend_ids))
    for post in pq.limit(fetch).all():
        u = db.get(User, post.user_id)
        place = db.get(Place, post.place_id) if post.place_id else None
        items.append(
            {
                "kind": "post",
                "id": post.id,
                "sort": post.created_at or datetime.utcnow(),
                "ago": _ago(post.created_at),
                "user": _user_card(u),
                "body": post.body,
                "images": post_images(post),
                "place": _place_card(place),
                "likes": post.likes_count,
                "liked": post.id in liked_ids,
                "comments": post.comments_count,
                "status": post.status,
                "views": int((post.likes_count or 0) * 137 + post.id * 17 + 180),
            }
        )

    vq = db.query(UserVisit).order_by(UserVisit.id.desc())
    if owner_id:
        vq = vq.filter(UserVisit.user_id == owner_id)
    else:
        vq = vq.filter(UserVisit.status == "approved")
    if friend_ids is not None:
        vq = vq.filter(UserVisit.user_id.in_(friend_ids))
    for v in vq.limit(fetch).all():
        u = db.get(User, v.user_id)
        place = db.get(Place, v.place_id)
        if not place or place.status != "approved":
            continue
        items.append(
            {
                "kind": "visit",
                "id": v.id,
                "sort": v.created_at or datetime.utcnow(),
                "ago": _ago(v.created_at),
                "user": _user_card(u),
                "body": v.note or f"{place.title} yerini ziyaret etti",
                "images": [place.img_url] if place.img_url else [],
                "place": _place_card(place),
                "likes": 0,
                "liked": False,
                "comments": 0,
                "status": v.status,
                "views": 0,
            }
        )

    rq = db.query(Review).order_by(Review.id.desc())
    if owner_id:
        rq = rq.filter(Review.user_id == owner_id)
    else:
        rq = rq.filter(Review.status == "approved")
    if friend_ids is not None:
        rq = rq.filter(Review.user_id.in_(friend_ids))
    for r in rq.limit(fetch).all():
        u = db.get(User, r.user_id)
        place = db.get(Place, r.place_id)
        if not place:
            continue
        items.append(
            {
                "kind": "review",
                "id": r.id,
                "sort": r.updated_at or r.created_at or datetime.utcnow(),
                "ago": _ago(r.updated_at or r.created_at),
                "user": _user_card(u),
                "body": r.body or f"★ {r.overall():.1f} değerlendirme",
                "images": [r.img_url] if r.img_url else [],
                "place": _place_card(place),
                "likes": 0,
                "liked": False,
                "comments": 0,
                "score": round(r.overall(), 1),
                "status": r.status,
                "views": 0,
            }
        )

    phq = db.query(PlacePhoto).filter(PlacePhoto.status == "approved").order_by(PlacePhoto.id.desc())
    if owner_id:
        phq = phq.filter(PlacePhoto.user_id == owner_id)
    if friend_ids is not None:
        phq = phq.filter(PlacePhoto.user_id.in_(friend_ids))
    for ph in phq.limit(fetch).all():
        u = db.get(User, ph.user_id)
        place = db.get(Place, ph.place_id)
        items.append(
            {
                "kind": "photo",
                "id": ph.id,
                "sort": ph.created_at or datetime.utcnow(),
                "ago": _ago(ph.created_at),
                "user": _user_card(u),
                "body": ph.caption or "Albüme foto ekledi",
                "images": [ph.img_url] if ph.img_url else [],
                "place": _place_card(place),
                "likes": 0,
                "liked": False,
                "comments": 0,
                "views": 0,
            }
        )

    if tab == "popular":
        items.sort(key=lambda x: (x.get("likes") or 0, x["sort"]), reverse=True)
    else:
        items.sort(key=lambda x: x["sort"], reverse=True)
    page = items[offset : offset + limit]
    has_more = len(items) > offset + limit
    return page, has_more


def profile_feed(
    db,
    viewer: User,
    tab: str,
    *,
    limit: int = FEED_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[dict], bool]:
    """Profil feed sekmesine göre sayfalanmış akış."""
    tab = tab if tab in PROFILE_FEED_TABS else "recents"
    if tab == "friends":
        return build_feed(
            db,
            viewer=viewer,
            owner_id=None,
            tab="recents",
            friends_only=True,
            limit=limit,
            offset=offset,
        )
    if tab == "recents":
        return build_feed(db, viewer=viewer, owner_id=None, tab="recents", limit=limit, offset=offset)
    if tab == "popular":
        return build_feed(db, viewer=viewer, owner_id=None, tab="popular", limit=limit, offset=offset)
    if tab == "mine":
        return build_feed(db, viewer=viewer, owner_id=viewer.id, tab="mine", limit=limit, offset=offset)
    return [], False


def album_photos(db, user_id: int, limit: int = 60) -> list[dict]:
    out = []
    for ph in (
        db.query(PlacePhoto)
        .filter(PlacePhoto.user_id == user_id, PlacePhoto.status.in_(("approved", "pending")))
        .order_by(PlacePhoto.id.desc())
        .limit(limit)
        .all()
    ):
        place = db.get(Place, ph.place_id)
        out.append(
            {
                "img_url": ph.img_url,
                "caption": ph.caption,
                "status": ph.status,
                "place": _place_card(place),
                "ago": _ago(ph.created_at),
            }
        )
    for post in db.query(UserPost).filter(UserPost.user_id == user_id, UserPost.status == "approved").order_by(UserPost.id.desc()).limit(40).all():
        for img in post_images(post):
            place = db.get(Place, post.place_id) if post.place_id else None
            out.append(
                {
                    "img_url": img,
                    "caption": (post.body or "")[:80],
                    "status": "approved",
                    "place": _place_card(place),
                    "ago": _ago(post.created_at),
                }
            )
    return out[:limit]


def going_count(db, place_id: int) -> int:
    return db.query(EventGoing).filter(EventGoing.place_id == place_id).count()


def user_is_going(db, user_id: int, place_id: int) -> bool:
    return (
        db.query(EventGoing)
        .filter(EventGoing.user_id == user_id, EventGoing.place_id == place_id)
        .first()
        is not None
    )


def suggest_places(db, limit: int = 6) -> list[dict]:
    """Öne çıkan gezilecek yerler + kamp (feed yer etiketi)."""
    rows = (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.category.in_(FEED_PICKER_CATS),
            Place.featured.is_(True),
        )
        .order_by(Place.id.desc())
        .limit(limit)
        .all()
    )
    if len(rows) < limit:
        more = (
            db.query(Place)
            .filter(Place.status == "approved", Place.category.in_(FEED_PICKER_CATS))
            .order_by(Place.views.desc())
            .limit(limit * 2)
            .all()
        )
        seen = {r.id for r in rows}
        for m in more:
            if m.id not in seen:
                rows.append(m)
            if len(rows) >= limit:
                break
    return [_place_card(p) for p in rows if p]


def suggest_top_restaurants(db, limit: int = 6) -> list[dict]:
    """Feed sağ sütun — en yüksek puanlı restoranlar."""
    rows = (
        db.query(Place)
        .filter(Place.status == "approved", Place.category == "food")
        .order_by(
            Place.rating_admin.desc().nulls_last(),
            Place.rating_avg.desc().nulls_last(),
            Place.rating_count.desc(),
            Place.featured.desc(),
            Place.views.desc(),
        )
        .limit(max(limit * 4, 24))
        .all()
    )
    out: list[dict] = []
    for p in rows:
        card = _place_card(p)
        if not card:
            continue
        score = p.rating_avg if p.rating_avg is not None else p.rating_admin
        if score is not None:
            card["rating"] = round(float(score), 1)
        out.append(card)
        if len(out) >= limit:
            break
    return out


def feed_picker_places(db, user_id: int, *, limit: int = 20) -> list[dict]:
    """Gönderi formu: önce gittiğin gezilecek yerler, sonra öneriler (tekrarsız)."""
    out: list[dict] = []
    seen: set[str] = set()
    for v in (
        db.query(UserVisit)
        .filter(UserVisit.user_id == user_id)
        .order_by(UserVisit.id.desc())
        .limit(40)
        .all()
    ):
        p = db.get(Place, v.place_id)
        if not p or p.status != "approved" or p.category not in FEED_PICKER_CATS:
            continue
        if p.slug in seen:
            continue
        card = _place_card(p)
        if card:
            out.append(card)
            seen.add(p.slug)
        if len(out) >= limit:
            return out
    for card in suggest_places(db, max(8, limit - len(out))):
        if not card or card.get("slug") in seen:
            continue
        out.append(card)
        seen.add(card["slug"])
        if len(out) >= limit:
            break
    return out


def upcoming_events(db, limit: int = 8) -> list[dict]:
    now = datetime.utcnow()
    rows = (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.category.in_(EVENT_CATS),
            Place.starts_at.isnot(None),
            Place.starts_at >= now,
        )
        .order_by(Place.starts_at.asc())
        .limit(limit)
        .all()
    )
    out = []
    for p in rows:
        d = _place_card(p)
        d["starts_at"] = p.starts_at.strftime("%d.%m %H:%M") if p.starts_at else ""
        d["going"] = going_count(db, p.id)
        out.append(d)
    return out

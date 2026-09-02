"""Profil feed yardımcıları — post / ziyaret / albüm / yorum birleşik akış."""
from __future__ import annotations

import json
from datetime import datetime

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


def build_feed(
    db,
    *,
    viewer: User | None = None,
    owner_id: int | None = None,
    tab: str = "recents",
    limit: int = 40,
) -> list[dict]:
    """Birleşik feed: post + ziyaret + yorum + foto."""
    items: list[dict] = []
    liked_ids: set[int] = set()
    if viewer:
        liked_ids = {
            x.post_id
            for x in db.query(PostLike).filter(PostLike.user_id == viewer.id).limit(500).all()
        }

    pq = db.query(UserPost).order_by(UserPost.id.desc())
    if owner_id:
        pq = pq.filter(UserPost.user_id == owner_id)
    elif tab != "mine":
        pq = pq.filter(UserPost.privacy == "public")
    for post in pq.limit(limit).all():
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
            }
        )

    vq = db.query(UserVisit).order_by(UserVisit.id.desc())
    if owner_id:
        vq = vq.filter(UserVisit.user_id == owner_id)
    for v in vq.limit(limit).all():
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
            }
        )

    rq = db.query(Review).filter(Review.status == "approved").order_by(Review.id.desc())
    if owner_id:
        rq = rq.filter(Review.user_id == owner_id)
    for r in rq.limit(limit).all():
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
            }
        )

    phq = db.query(PlacePhoto).filter(PlacePhoto.status == "approved").order_by(PlacePhoto.id.desc())
    if owner_id:
        phq = phq.filter(PlacePhoto.user_id == owner_id)
    for ph in phq.limit(limit).all():
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
            }
        )

    if tab == "popular":
        items.sort(key=lambda x: (x.get("likes") or 0, x["sort"]), reverse=True)
    else:
        items.sort(key=lambda x: x["sort"], reverse=True)
    return items[:limit]


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
    for post in db.query(UserPost).filter(UserPost.user_id == user_id).order_by(UserPost.id.desc()).limit(40).all():
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
    rows = (
        db.query(Place)
        .filter(Place.status == "approved", Place.featured.is_(True))
        .order_by(Place.id.desc())
        .limit(limit)
        .all()
    )
    if len(rows) < limit:
        more = (
            db.query(Place)
            .filter(Place.status == "approved")
            .order_by(Place.views.desc())
            .limit(limit)
            .all()
        )
        seen = {r.id for r in rows}
        for m in more:
            if m.id not in seen:
                rows.append(m)
            if len(rows) >= limit:
                break
    return [_place_card(p) for p in rows if p]


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

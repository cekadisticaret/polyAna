"""Aktivite arkadaşı ilanları — okey 4., tenis partneri vb."""
from __future__ import annotations

from datetime import datetime, timedelta

from content_filter import filter_profanity, profanity_ok
from feed_social import _ago
from models import ActivitySeek, ActivitySeekJoin, User
from user_points import award_activity_join_approved, user_points

JOIN_PENDING = "pending"
JOIN_JOINED = "joined"
JOIN_LEFT = "left"
JOIN_REJECTED = "rejected"

ACTIVITY_TYPES: dict[str, dict[str, str]] = {
    "okey": {"label": "Okey", "emoji": "🀄", "default_title": "4. oyuncu arıyorum"},
    "tennis": {"label": "Tenis", "emoji": "🎾", "default_title": "Tenis arkadaşı arıyorum"},
    "padel": {"label": "Padel", "emoji": "🏸", "default_title": "Padel partneri arıyorum"},
    "football": {"label": "Halı saha / Futbol", "emoji": "⚽", "default_title": "Oyuncu arıyorum"},
    "basketball": {"label": "Basketbol", "emoji": "🏀", "default_title": "Basketbol arkadaşı arıyorum"},
    "running": {"label": "Koşu", "emoji": "🏃", "default_title": "Koşu arkadaşı arıyorum"},
    "hiking": {"label": "Yürüyüş", "emoji": "🥾", "default_title": "Yürüyüş arkadaşı arıyorum"},
    "visit": {"label": "Birlikte gezi", "emoji": "🗺", "default_title": "Birlikte gidelim mi?"},
    "board": {"label": "Masa oyunu", "emoji": "🎲", "default_title": "Masa oyunu grubu arıyorum"},
    "other": {"label": "Diğer", "emoji": "✨", "default_title": "Arkadaş arıyorum"},
}

SKILL_LEVELS = {
    "any": "Fark etmez",
    "beginner": "Başlangıç",
    "intermediate": "Orta",
    "advanced": "İleri",
}

PARTNER_PLACE_CATEGORIES = frozenset(
    {"visit", "camp", "fun", "nightlife", "family", "event", "concert", "theater", "cinema"}
)

_TR_MONTH = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)
_TR_WDAY = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


def partner_eligible(category: str | None) -> bool:
    return (category or "") in PARTNER_PLACE_CATEGORIES


def _format_when_label(when_at: datetime) -> str:
    return f"{when_at.day} {_TR_MONTH[when_at.month - 1]} {_TR_WDAY[when_at.weekday()]}"


def _default_place_seek_title(place_title: str) -> str:
    t = (place_title or "Buraya").strip()
    return f"{t}'a gideceğim — benimle gelmek isteyen var mı?"[:120]


def activity_meta(key: str) -> dict[str, str]:
    return ACTIVITY_TYPES.get(key) or ACTIVITY_TYPES["other"]


def _join_count(seek: ActivitySeek) -> int:
    return sum(1 for j in seek.joins if j.status == JOIN_JOINED)


def _pending_requests(seek: ActivitySeek) -> list[ActivitySeekJoin]:
    return [j for j in seek.joins if j.status == JOIN_PENDING]


def _spots_left(seek: ActivitySeek) -> int:
    return max(0, int(seek.slots_needed or 1) - _join_count(seek))


def _refresh_status(seek: ActivitySeek) -> None:
    now = datetime.utcnow()
    if seek.status != "open":
        return
    if seek.expires_at and seek.expires_at <= now:
        seek.status = "expired"
        return
    if _spots_left(seek) <= 0:
        seek.status = "filled"


def list_open_seeks(db, *, activity_type: str | None = None, ilce: str | None = None, limit: int = 40):
    from sqlalchemy.orm import joinedload

    now = datetime.utcnow()
    q = (
        db.query(ActivitySeek)
        .options(joinedload(ActivitySeek.user), joinedload(ActivitySeek.joins).joinedload(ActivitySeekJoin.user))
        .filter(ActivitySeek.status == "open")
        .filter((ActivitySeek.expires_at.is_(None)) | (ActivitySeek.expires_at > now))
    )
    if activity_type and activity_type in ACTIVITY_TYPES:
        q = q.filter(ActivitySeek.activity_type == activity_type)
    if ilce:
        q = q.filter(ActivitySeek.ilce == ilce)
    rows = q.order_by(ActivitySeek.created_at.desc()).limit(max(1, min(limit, 80))).all()
    for row in rows:
        _refresh_status(row)
    db.commit()
    return [s for s in rows if s.status == "open"]


def seek_public(db, seek: ActivitySeek, viewer: User | None) -> dict:
    meta = activity_meta(seek.activity_type)
    host = seek.user
    joined_ids = {j.user_id for j in seek.joins if j.status == JOIN_JOINED}
    spots_left = _spots_left(seek)
    viewer_joined = bool(viewer and viewer.id in joined_ids)
    viewer_pending = bool(
        viewer
        and any(j.user_id == viewer.id and j.status == JOIN_PENDING for j in seek.joins)
    )
    viewer_host = bool(viewer and viewer.id == seek.user_id)
    joiners: list[dict] = []
    pending_requests: list[dict] = []
    if viewer_joined or viewer_host:
        for j in seek.joins:
            if j.status != JOIN_JOINED or not j.user:
                continue
            joiners.append(
                {
                    "id": j.user.id,
                    "name": j.user.display_name(),
                    "handle": j.user.handle(),
                    "avatar_url": j.user.avatar_url or "",
                    "points": user_points(j.user),
                }
            )
    if viewer_host:
        for j in _pending_requests(seek):
            if not j.user:
                continue
            pending_requests.append(
                {
                    "user_id": j.user.id,
                    "name": j.user.display_name(),
                    "handle": j.user.handle(),
                    "avatar_url": j.user.avatar_url or "",
                    "points": user_points(j.user),
                    "ago": _ago(j.created_at),
                }
            )
    out = {
        "id": seek.id,
        "activity_type": seek.activity_type,
        "activity_label": meta["label"],
        "emoji": meta["emoji"],
        "title": seek.title or meta["default_title"],
        "host": host.display_name() if host else "Üye",
        "host_id": seek.user_id,
        "host_handle": host.handle() if host else "",
        "host_points": user_points(host) if host else 0,
        "ilce": seek.ilce or "",
        "venue": seek.venue or "",
        "time_label": seek.when_label or "Esnek",
        "when_at": seek.when_at.isoformat() if seek.when_at else None,
        "note": seek.note or "",
        "skill_level": seek.skill_level or "any",
        "skill_label": SKILL_LEVELS.get(seek.skill_level or "any", "Fark etmez"),
        "points_min": int(seek.points_min or 0),
        "slots_needed": int(seek.slots_needed or 1),
        "slots_filled": _join_count(seek),
        "spots_left": spots_left,
        "joiners_count": len(joined_ids),
        "pending_count": len(pending_requests),
        "joined": viewer_joined,
        "pending": viewer_pending,
        "is_mine": viewer_host,
        "status": seek.status,
        "ago": _ago(seek.created_at),
        "contact_hint": "",
        "joiners": joiners,
        "pending_requests": pending_requests,
    }
    if viewer_joined or viewer_host:
        out["contact_hint"] = seek.contact_hint or ""
    if seek.place_id:
        from models import Place
        from seo_urls import place_seo_path

        pl = db.get(Place, seek.place_id)
        if pl and pl.status == "approved":
            out["place_id"] = pl.id
            out["place_title"] = pl.title
            out["place_slug"] = pl.slug
            out["place_path"] = place_seo_path(pl)
    return out


def create_seek(db, user: User, payload: dict) -> tuple[ActivitySeek | None, str | None]:
    activity_type = (payload.get("activity_type") or payload.get("type") or "other").strip().lower()
    if activity_type not in ACTIVITY_TYPES:
        activity_type = "other"
    meta = activity_meta(activity_type)

    title = filter_profanity((payload.get("title") or meta["default_title"]).strip())[:120]
    note = filter_profanity((payload.get("note") or "").strip())[:800]
    venue = filter_profanity((payload.get("venue") or "").strip())[:160]
    contact_hint = filter_profanity((payload.get("contact_hint") or "").strip())[:120]
    when_label = filter_profanity((payload.get("when_label") or payload.get("time_label") or "Esnek").strip())[:80]
    ilce = (payload.get("ilce") or "").strip()[:48]

    if not profanity_ok(title) or not profanity_ok(note):
        return None, "Metin uygun değil"

    try:
        slots_needed = int(payload.get("slots_needed") or payload.get("slots") or 1)
    except (TypeError, ValueError):
        slots_needed = 1
    slots_needed = max(1, min(slots_needed, 10))

    try:
        points_min = int(payload.get("points_min") or 0)
    except (TypeError, ValueError):
        points_min = 0
    points_min = max(0, min(points_min, 5000))

    skill = (payload.get("skill_level") or "any").strip().lower()
    if skill not in SKILL_LEVELS:
        skill = "any"

    when_at = None
    raw_when = (payload.get("when_at") or "").strip()
    if raw_when:
        try:
            when_at = datetime.fromisoformat(raw_when.replace("Z", "+00:00").replace("+00:00", ""))
        except ValueError:
            when_at = None

    open_count = (
        db.query(ActivitySeek)
        .filter(ActivitySeek.user_id == user.id, ActivitySeek.status == "open")
        .count()
    )
    if open_count >= 5:
        return None, "En fazla 5 açık ilan olabilir"

    seek = ActivitySeek(
        user_id=user.id,
        activity_type=activity_type,
        title=title,
        slots_needed=slots_needed,
        ilce=ilce,
        venue=venue,
        when_label=when_label,
        when_at=when_at,
        note=note,
        skill_level=skill,
        points_min=points_min,
        contact_hint=contact_hint,
        status="open",
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    try:
        place_id = int(payload.get("place_id") or 0)
    except (TypeError, ValueError):
        place_id = 0
    if place_id > 0:
        seek.place_id = place_id
        if when_at and when_at > datetime.utcnow():
            seek.expires_at = when_at + timedelta(days=1)
    db.add(seek)
    db.commit()
    db.refresh(seek)
    return seek, None


def get_user_open_place_seek(db, user_id: int, place_id: int) -> ActivitySeek | None:
    return (
        db.query(ActivitySeek)
        .filter(
            ActivitySeek.user_id == user_id,
            ActivitySeek.place_id == place_id,
            ActivitySeek.status == "open",
        )
        .order_by(ActivitySeek.id.desc())
        .first()
    )


def create_place_seek(
    db,
    user: User,
    place,
    *,
    when_date: str,
    slots_needed: int = 1,
    note: str = "",
) -> tuple[ActivitySeek | None, str | None]:
    """Yer detayından «partner bul» ilanı."""
    from seo_urls import place_seo_path

    if not partner_eligible(place.category):
        return None, "Bu kayıt türü için partner ilanı açılamaz"

    existing = get_user_open_place_seek(db, user.id, place.id)
    if existing:
        return None, "Bu yer için zaten açık ilanın var"

    raw = (when_date or "").strip()
    if not raw:
        return None, "Gidiş tarihi seç"
    try:
        parts = raw.split("-")
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        when_at = datetime(y, m, d, 10, 0, 0)
    except (ValueError, IndexError):
        return None, "Geçersiz tarih"

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if when_at < today:
        return None, "Geçmiş tarih seçilemez"

    path = place_seo_path(place)
    title = _default_place_seek_title(place.title)
    when_label = _format_when_label(when_at)
    body = filter_profanity((note or "").strip())
    if not body:
        body = f"{place.title} — detay: {path}"
    else:
        body = f"{body} · {path}"[:800]

    payload = {
        "activity_type": "visit",
        "title": title,
        "slots_needed": slots_needed,
        "ilce": place.ilce or "",
        "venue": place.title,
        "when_label": when_label,
        "when_at": when_at.isoformat(),
        "note": body,
        "place_id": place.id,
        "skill_level": "any",
        "points_min": 0,
    }
    return create_seek(db, user, payload)


def join_seek(db, user: User, seek_id: int) -> tuple[ActivitySeek | None, str | None]:
    seek = db.query(ActivitySeek).filter(ActivitySeek.id == seek_id).first()
    if seek is None:
        return None, "İlan bulunamadı"
    _refresh_status(seek)
    if seek.status != "open":
        return None, "İlan kapalı"

    if seek.user_id == user.id:
        return None, "Kendi ilanına katılamazsın"

    if user_points(user) < int(seek.points_min or 0):
        return None, f"En az {seek.points_min} puan gerekli"

    existing = (
        db.query(ActivitySeekJoin)
        .filter(ActivitySeekJoin.seek_id == seek.id, ActivitySeekJoin.user_id == user.id)
        .first()
    )
    if existing and existing.status == JOIN_JOINED:
        return None, "Zaten katıldın"
    if existing and existing.status == JOIN_PENDING:
        return None, "Onay bekliyorsun — ilan sahibi yanıtlayacak"

    if _spots_left(seek) <= 0:
        seek.status = "filled"
        db.commit()
        return None, "Kontenjan doldu"

    if existing:
        existing.status = JOIN_PENDING
        existing.created_at = datetime.utcnow()
        existing.responded_at = None
    else:
        db.add(ActivitySeekJoin(seek_id=seek.id, user_id=user.id, status=JOIN_PENDING))

    db.commit()
    db.refresh(seek)
    return seek, None


def approve_join(
    db, host: User, seek_id: int, join_user_id: int
) -> tuple[ActivitySeek | None, str | None]:
    seek = db.query(ActivitySeek).filter(ActivitySeek.id == seek_id).first()
    if seek is None:
        return None, "İlan bulunamadı"
    if seek.user_id != host.id and host.role != "admin":
        return None, "Yetki yok"
    _refresh_status(seek)
    if seek.status != "open":
        return None, "İlan kapalı"
    if _spots_left(seek) <= 0:
        return None, "Kontenjan doldu"

    row = (
        db.query(ActivitySeekJoin)
        .filter(
            ActivitySeekJoin.seek_id == seek.id,
            ActivitySeekJoin.user_id == join_user_id,
            ActivitySeekJoin.status == JOIN_PENDING,
        )
        .first()
    )
    if row is None:
        return None, "Bekleyen istek yok"

    row.status = JOIN_JOINED
    row.responded_at = datetime.utcnow()
    db.flush()
    _refresh_status(seek)
    award_activity_join_approved(db, join_user_id=join_user_id, seek_id=seek.id, host_id=seek.user_id)
    db.commit()
    db.refresh(seek)
    return seek, None


def reject_join(
    db, host: User, seek_id: int, join_user_id: int
) -> tuple[ActivitySeek | None, str | None]:
    seek = db.query(ActivitySeek).filter(ActivitySeek.id == seek_id).first()
    if seek is None:
        return None, "İlan bulunamadı"
    if seek.user_id != host.id and host.role != "admin":
        return None, "Yetki yok"

    row = (
        db.query(ActivitySeekJoin)
        .filter(
            ActivitySeekJoin.seek_id == seek.id,
            ActivitySeekJoin.user_id == join_user_id,
            ActivitySeekJoin.status == JOIN_PENDING,
        )
        .first()
    )
    if row is None:
        return None, "Bekleyen istek yok"

    row.status = JOIN_REJECTED
    row.responded_at = datetime.utcnow()
    db.commit()
    db.refresh(seek)
    return seek, None


def leave_seek(db, user: User, seek_id: int) -> tuple[ActivitySeek | None, str | None]:
    seek = db.query(ActivitySeek).filter(ActivitySeek.id == seek_id).first()
    if seek is None:
        return None, "İlan bulunamadı"

    row = (
        db.query(ActivitySeekJoin)
        .filter(
            ActivitySeekJoin.seek_id == seek.id,
            ActivitySeekJoin.user_id == user.id,
            ActivitySeekJoin.status.in_((JOIN_JOINED, JOIN_PENDING)),
        )
        .first()
    )
    if row is None:
        return None, "Katılım yok"

    was_joined = row.status == JOIN_JOINED
    row.status = JOIN_LEFT
    row.responded_at = datetime.utcnow()
    if was_joined and seek.status == "filled":
        seek.status = "open"
    db.commit()
    db.refresh(seek)
    return seek, None


def cancel_seek(db, user: User, seek_id: int) -> str | None:
    seek = db.query(ActivitySeek).filter(ActivitySeek.id == seek_id).first()
    if seek is None:
        return "İlan bulunamadı"
    if seek.user_id != user.id and user.role != "admin":
        return "Yetki yok"
    seek.status = "cancelled"
    db.commit()
    return None


def seed_demo_seeks(db) -> int:
    """Soğuk başlangıç — örnek ilanlar (yalnız tablo boşken)."""
    if db.query(ActivitySeek).count() > 0:
        return 0
    users = (
        db.query(User)
        .filter(User.is_active.is_(True), User.role == "user")
        .order_by(User.id.asc())
        .limit(6)
        .all()
    )
    if len(users) < 2:
        return 0
    samples = [
        ("okey", "Nilüfer", "Bu akşam 21:00", "3 kişiyiz, 1 kişi arıyoruz. Acele etmeyin :)", 1, 0),
        ("tennis", "Osmangazi", "Yarın 18:00", "Çiftler tenisi — partner arıyorum, orta seviye.", 1, 50),
        ("football", "Yıldırım", "Cumartesi 20:00", "Halı saha için 2 oyuncu lazım.", 2, 0),
        ("board", "Nilüfer", "Pazar 15:00", "Catan / Tabu — 2 kişi daha.", 2, 0),
    ]
    n = 0
    for i, (atype, ilce, when_label, note, slots, pts) in enumerate(samples):
        host = users[i % len(users)]
        meta = activity_meta(atype)
        db.add(
            ActivitySeek(
                user_id=host.id,
                activity_type=atype,
                title=meta["default_title"],
                slots_needed=slots,
                ilce=ilce,
                when_label=when_label,
                note=note,
                points_min=pts,
                status="open",
                expires_at=datetime.utcnow() + timedelta(days=5),
            )
        )
        n += 1
    db.commit()
    return n

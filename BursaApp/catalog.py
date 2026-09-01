"""Kategori / ilçe sabitleri ve Place sorguları."""
from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import or_

CATEGORIES = (
    {"key": "food", "path": "/yeme-icme", "label": "Yeme-içme", "hint": "restoran, cafe, İskender, tatlı, pub"},
    {"key": "visit", "path": "/gezilecek", "label": "Gezilecek", "hint": "cami, han, köy, doğa, Uludağ"},
    {"key": "hotel", "path": "/oteller", "label": "Oteller", "hint": "termal, şehir, Uludağ kayak"},
    {"key": "camp", "path": "/kamp", "label": "Kamp", "hint": "milli park, göl, karavan"},
    {"key": "concert", "path": "/konserler", "label": "Konserler", "hint": "salon, açıkhava, stadyum"},
    {"key": "theater", "path": "/tiyatro", "label": "Tiyatro", "hint": "sahneler ve oyunlar"},
    {"key": "cinema", "path": "/sinema", "label": "Sinema", "hint": "salonlar ve vizyon"},
    {"key": "fun", "path": "/eglence", "label": "Eğlence", "hint": "canlı müzik, bar, bowling, escape"},
    {"key": "event", "path": "/etkinlikler", "label": "Etkinlikler", "hint": "tarihli takvim"},
    {"key": "org", "path": "/organizasyonlar", "label": "Organizasyonlar", "hint": "festival, dernek, ajans"},
    {"key": "hospital", "path": "/hastaneler", "label": "Hastaneler", "hint": "devlet, özel, üniversite"},
    {"key": "doctor", "path": "/doktorlar", "label": "Doktorlar", "hint": "branş + bağlı olduğu hastane"},
    {"key": "vet", "path": "/veterinerler", "label": "Veterinerler", "hint": "klinik, hayvan hastanesi"},
)
CAT_BY_KEY = {c["key"]: c for c in CATEGORIES}
CAT_BY_PATH = {c["path"]: c for c in CATEGORIES}
CAT_KEYS = tuple(c["key"] for c in CATEGORIES)

DOCTOR_SPECS = (
    "Kadın doğum", "Çocuk", "Kalp", "Onkoloji", "Göz", "Diş",
    "Ortopedi", "KBB", "Cildiye", "Genel cerrahi", "Üroloji",
    "Beyin cerrahisi", "Nöroloji", "Dahiliye", "Göğüs",
    "Gastroenteroloji", "Psikiyatri", "Hematoloji", "Endokrin",
    "FTR", "Plastik", "Enfeksiyon", "Nakil", "Genetik",
)
CONCERT_KINDS = ("Yaklaşan", "Salon", "Açıkhava", "Stadyum", "Live")
THEATER_KINDS = ("Yaklaşan", "Salon")
CINEMA_KINDS = ("Vizyonda", "Salon")
EVENT_KINDS = ("Festival", "Fuar", "Sahne", "Kent")
GROUP_ILCE = frozenset(("food", "visit", "hotel", "camp", "vet", "hospital"))
GROUP_BAND = frozenset(("doctor", "concert", "theater", "cinema", "event"))
KIND_BY_CAT = {
    "concert": CONCERT_KINDS,
    "theater": THEATER_KINDS,
    "cinema": CINEMA_KINDS,
    "event": EVENT_KINDS,
}

ILCELER = (
    "Osmangazi",
    "Nilüfer",
    "Yıldırım",
    "Mudanya",
    "Gemlik",
    "İnegöl",
    "Mustafakemalpaşa",
    "İznik",
    "Diğer",
)

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")


def slugify(text: str) -> str:
    s = (text or "").translate(_TR).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "yer"


def unique_slug(db, title: str, exclude_id: int | None = None) -> str:
    from models import Place

    base = slugify(title)
    slug, n = base, 2
    while True:
        q = db.query(Place).filter(Place.slug == slug)
        if exclude_id:
            q = q.filter(Place.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def tags_load(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def tags_dump(val) -> str:
    return json.dumps(tags_load(val), ensure_ascii=False)


def place_public(p) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "category": p.category,
        "category_label": (CAT_BY_KEY.get(p.category) or {}).get("label") or p.category,
        "ilce": p.ilce,
        "address": p.address,
        "lat": p.lat,
        "lng": p.lng,
        "phone": p.phone,
        "web": p.web,
        "hours_text": p.hours_text,
        "price_band": p.price_band,
        "blurb": p.blurb,
        "body": p.body,
        "img_url": p.img_url,
        "img": p.img_url,
        "tags": tags_load(p.tags),
        "rating_admin": p.rating_admin,
        "rating": p.rating_admin,
        "featured": bool(p.featured),
        "starts_at": p.starts_at.isoformat() if p.starts_at else None,
        "when": p.starts_at.strftime("%d.%m %H:%M") if p.starts_at else None,
        "ends_at": p.ends_at.isoformat() if p.ends_at else None,
        "venue_name": p.venue_name,
        "hospital_slug": p.venue_name if p.category == "doctor" else "",
        "status": p.status,
        "maps": maps_url(p),
    }


def place_mine(p) -> dict:
    d = place_public(p)
    d["reject_reason"] = p.reject_reason
    d["created_at"] = p.created_at.isoformat() if p.created_at else None
    return d


def maps_url(p) -> str:
    if p.lat is not None and p.lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={p.lat},{p.lng}"
    q = " ".join(x for x in (p.title, p.address, p.ilce, "Bursa") if x)
    from urllib.parse import quote_plus
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(q)}"


def parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def query_places(
    db,
    *,
    category: str | None = None,
    ilce: str | None = None,
    q: str | None = None,
    from_=None,
    to=None,
    status: str = "approved",
    featured: bool | None = None,
    submitted_by_id: int | None = None,
    order: str | None = None,
    price_band: str | None = None,
    venue_name: str | None = None,
    limit: int = 24,
    offset: int = 0,
):
    from models import Place

    qry = db.query(Place)
    if status:
        qry = qry.filter(Place.status == status)
    if category and category in CAT_KEYS:
        qry = qry.filter(Place.category == category)
    if ilce:
        qry = qry.filter(Place.ilce == ilce)
    if price_band:
        qry = qry.filter(Place.price_band == price_band)
    if venue_name:
        qry = qry.filter(Place.venue_name == venue_name)
    if submitted_by_id:
        qry = qry.filter(Place.submitted_by_id == submitted_by_id)
    if featured is True:
        qry = qry.filter(Place.featured.is_(True))
    if from_:
        dt = parse_dt(from_)
        if dt:
            qry = qry.filter(Place.starts_at.isnot(None), Place.starts_at >= dt)
    if to:
        dt = parse_dt(to)
        if dt:
            qry = qry.filter(or_(Place.ends_at.is_(None), Place.ends_at <= dt), Place.starts_at.isnot(None))
    if q:
        like = f"%{q.strip()}%"
        qry = qry.filter(
            or_(
                Place.title.ilike(like),
                Place.blurb.ilike(like),
                Place.body.ilike(like),
                Place.ilce.ilike(like),
                Place.address.ilike(like),
                Place.venue_name.ilike(like),
                Place.tags.ilike(like),
            )
        )
    if order == "rating":
        qry = qry.order_by(Place.rating_admin.desc().nulls_last(), Place.title.asc())
    elif order == "date":
        qry = qry.order_by(Place.starts_at.asc().nulls_last(), Place.featured.desc(), Place.id.desc())
    else:
        qry = qry.order_by(Place.featured.desc(), Place.starts_at.asc().nulls_last(), Place.id.desc())
    total = qry.count()
    rows = qry.offset(max(0, offset)).limit(max(1, min(int(limit or 24), 200))).all()
    return rows, total

"""Bugün / Bu akşam / Yakınımda / Hafta sonu keşif sorguları."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from catalog import place_public, tags_load
from models import Place

_TZ = ZoneInfo("Europe/Istanbul")

# Osmangazi Heykel civarı — konum izni yoksa fallback
FALLBACK_LAT = 40.1885
FALLBACK_LNG = 29.0610

TODAY_GROUPS = (
    ("concert", "Konserler"),
    ("theater", "Tiyatro"),
    ("cinema", "Sinema"),
    ("event", "Etkinlikler"),
    ("family", "Aile"),
    ("sport", "Spor"),
)

_SHOW_CATS = ("concert", "theater", "cinema", "event", "family", "sport")


def _now() -> datetime:
    return datetime.now(_TZ).replace(tzinfo=None)


def _day_bounds(day: datetime | None = None):
    d = day or _now()
    start = datetime(d.year, d.month, d.day)
    end = start + timedelta(days=1)
    return start, end


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _rating_key(p: Place) -> float:
    if p.rating_avg is not None:
        return float(p.rating_avg)
    if p.rating_admin is not None:
        return float(p.rating_admin)
    return 0.0


def today_bursa(db, day: datetime | None = None) -> dict:
    start, end = _day_bounds(day)
    d = day or _now()
    rows = (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.starts_at.isnot(None),
            Place.starts_at >= start,
            Place.starts_at < end,
            Place.category.in_(_SHOW_CATS),
        )
        .order_by(Place.starts_at.asc())
        .all()
    )
    by_cat: dict[str, list] = {k: [] for k, _ in TODAY_GROUPS}
    for p in rows:
        by_cat.setdefault(p.category, []).append(place_public(p))
    groups = []
    for key, label in TODAY_GROUPS:
        items = by_cat.get(key) or []
        if items:
            groups.append({"key": key, "label": label, "places": items, "count": len(items)})
    gunler = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
    aylar = (
        "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    )
    return {
        "date_label": f"{d.day} {aylar[d.month - 1]} {gunler[d.weekday()]}",
        "date_iso": start.strftime("%Y-%m-%d"),
        "groups": groups,
        "total": sum(g["count"] for g in groups),
    }


def tonight(db, *, couple: bool = False) -> dict:
    start, end = _day_bounds()
    evening = start.replace(hour=17, minute=0)
    shows = (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.starts_at.isnot(None),
            Place.starts_at >= evening,
            Place.starts_at < end,
            Place.category.in_(("concert", "theater", "cinema", "event")),
        )
        .order_by(Place.starts_at.asc())
        .limit(40)
        .all()
    )
    food = (
        db.query(Place)
        .filter(Place.status == "approved", Place.category == "food")
        .all()
    )
    food_sorted = sorted(food, key=_rating_key, reverse=True)

    def _cafe_night(p: Place) -> bool:
        tags = {t.lower() for t in tags_load(p.tags)}
        sub = (p.subcategory or "").lower()
        if sub == "cafe":
            return True
        return bool(tags & {"cafe", "kahve", "7-24", "nargile", "manzarali", "romantik"})

    cafes = [p for p in food_sorted if _cafe_night(p)][:8]
    dinners = [p for p in food_sorted if (p.subcategory or "") != "cafe"][:8]

    if couple:
        couple_tags = {"romantik", "manzarali", "cafe", "tatli", "kitap-cafe"}
        dinners = [
            p for p in food_sorted
            if couple_tags & {t.lower() for t in tags_load(p.tags)}
            or (p.subcategory or "") in ("cafe", "tatli", "restoran")
        ][:8] or dinners
        shows = [
            p for p in shows
            if p.category in ("theater", "cinema", "concert")
        ] or shows

    by = {
        "cinema": [place_public(p) for p in shows if p.category == "cinema"],
        "concert": [place_public(p) for p in shows if p.category == "concert"],
        "theater": [place_public(p) for p in shows if p.category == "theater"],
        "event": [place_public(p) for p in shows if p.category == "event"],
        "dinner": [place_public(p) for p in dinners],
        "cafe": [place_public(p) for p in cafes],
    }
    sections = [
        {"key": "cinema", "label": "Sinema", "places": by["cinema"]},
        {"key": "concert", "label": "Konser", "places": by["concert"]},
        {"key": "theater", "label": "Tiyatro", "places": by["theater"]},
        {"key": "dinner", "label": "Akşam yemeği", "places": by["dinner"]},
        {"key": "cafe", "label": "Kahve", "places": by["cafe"]},
    ]
    if by["event"]:
        sections.insert(3, {"key": "event", "label": "Etkinlik", "places": by["event"]})
    return {
        "couple": couple,
        "title": "Çiftler için bu akşam Bursa'da" if couple else "Bu akşam ne yapabilirim?",
        "sections": [s for s in sections if s["places"]],
    }


def nearby(db, lat: float, lng: float, radius_m: float = 500, category: str | None = None, *, unlimited: bool = False) -> dict:
    qry = db.query(Place).filter(
        Place.status == "approved",
        Place.lat.isnot(None),
        Place.lng.isnot(None),
    )
    if category:
        qry = qry.filter(Place.category == category)
    rows = qry.all()
    hits = []
    for p in rows:
        dist = haversine_m(lat, lng, float(p.lat), float(p.lng))
        if unlimited or dist <= radius_m:
            d = place_public(p)
            d["distance_m"] = int(round(dist))
            hits.append(d)
    hits.sort(key=lambda x: (x.get("distance_m") or 0, -(x.get("rating") or 0)))
    counts: dict[str, int] = {}
    for h in hits:
        counts[h["category"]] = counts.get(h["category"], 0) + 1
    tip = None
    prefer = ("market", "food") if not category else (category,)
    for h in hits:
        if h.get("category") in prefer and (h.get("rating") or 0) >= 4.2:
            tip = h
            break
    if tip is None and hits:
        tip = hits[0]
    return {
        "lat": lat,
        "lng": lng,
        "radius_m": int(radius_m) if not unlimited else 0,
        "total": len(hits),
        "counts": counts,
        "places": hits,
        "tip": tip,
        "category": category or "",
        "unlimited": unlimited,
    }


def _pick(db, *, category=None, subcategory=None, tags_any=None, limit=4):
    qry = db.query(Place).filter(Place.status == "approved")
    if category:
        qry = qry.filter(Place.category == category)
    if subcategory:
        qry = qry.filter(Place.subcategory == subcategory)
    rows = qry.all()
    if tags_any:
        want = {t.lower() for t in tags_any}
        rows = [p for p in rows if want & {x.lower() for x in tags_load(p.tags)}]
    rows = sorted(rows, key=_rating_key, reverse=True)
    return [place_public(p) for p in rows[:limit]]


def _next_weekend():
    now = _now()
    # weekday: Mon=0 … Sat=5 Sun=6
    days_to_sat = (5 - now.weekday()) % 7
    if now.weekday() == 6:  # Sunday → this Sunday + next Saturday? show this weekend still
        sat = datetime(now.year, now.month, now.day) - timedelta(days=1)
    elif now.weekday() == 5:
        sat = datetime(now.year, now.month, now.day)
    else:
        sat = datetime(now.year, now.month, now.day) + timedelta(days=days_to_sat)
    sun = sat + timedelta(days=1)
    return sat, sun


def weekend(db) -> dict:
    sat, sun = _next_weekend()
    sat_start, sat_end = _day_bounds(sat)
    sun_start, sun_end = _day_bounds(sun)

    def _shows(a, b):
        return (
            db.query(Place)
            .filter(
                Place.status == "approved",
                Place.starts_at.isnot(None),
                Place.starts_at >= a,
                Place.starts_at < b,
            )
            .order_by(Place.starts_at.asc())
            .limit(12)
            .all()
        )

    sat_shows = [place_public(p) for p in _shows(sat_start, sat_end)]
    sun_shows = [place_public(p) for p in _shows(sun_start, sun_end)]

    saturday = [
        {"key": "kahvalti", "label": "Kahvaltı", "places": _pick(db, category="food", subcategory="kahvalti", limit=4)
         or _pick(db, category="food", subcategory="cafe", limit=4)},
        {"key": "visit", "label": "Gezilecek yer", "places": _pick(db, category="visit", limit=4)},
        {"key": "event", "label": "Etkinlik", "places": sat_shows[:4]},
        {"key": "concert", "label": "Konser", "places": [p for p in sat_shows if p["category"] == "concert"][:4]},
        {"key": "dinner", "label": "Akşam yemeği", "places": _pick(db, category="food", limit=4)},
    ]
    sunday = [
        {"key": "doga", "label": "Doğa", "places": _pick(db, category="visit", tags_any=["doga", "doğa", "uludag", "park"], limit=4)
         or _pick(db, category="camp", limit=4) or _pick(db, category="visit", limit=4)},
        {"key": "tarihi", "label": "Tarihi mekan", "places": _pick(db, category="visit", tags_any=["tarihi", "unesco", "cami"], limit=4)
         or _pick(db, category="visit", limit=4)},
        {"key": "aile", "label": "Aile aktivitesi", "places": _pick(db, category="family", limit=4)
         or _pick(db, category="fun", limit=4)},
        {"key": "cafe", "label": "Cafe", "places": _pick(db, category="food", subcategory="cafe", limit=4)
         or _pick(db, category="food", limit=4)},
        {"key": "event", "label": "Etkinlik", "places": sun_shows[:4]},
    ]
    aylar = (
        "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    )
    return {
        "saturday_label": f"Cumartesi · {sat.day} {aylar[sat.month - 1]}",
        "sunday_label": f"Pazar · {sun.day} {aylar[sun.month - 1]}",
        "saturday": [s for s in saturday if s["places"]],
        "sunday": [s for s in sunday if s["places"]],
        "sat_iso": sat.strftime("%Y-%m-%d"),
        "sun_iso": sun.strftime("%Y-%m-%d"),
    }


def weekend_plan(db, people: int = 2) -> dict:
    """Kural tabanlı 2 kişilik Cumartesi + Pazar rota."""
    w = weekend(db)

    def first(sections, key):
        for s in sections:
            if s["key"] == key and s["places"]:
                return s["places"][0]
        for s in sections:
            if s["places"]:
                return s["places"][0]
        return None

    sat_slots = [
        {"when": "Sabah", "place": first(w["saturday"], "kahvalti")},
        {"when": "Öğlen", "place": first(w["saturday"], "visit")},
        {"when": "Akşam", "place": first(w["saturday"], "dinner") or first(w["saturday"], "concert")},
    ]
    sun_slots = [
        {"when": "Sabah", "place": first(w["sunday"], "cafe")},
        {"when": "Öğlen", "place": first(w["sunday"], "doga") or first(w["sunday"], "tarihi")},
        {"when": "İkindi", "place": first(w["sunday"], "aile") or first(w["sunday"], "tarihi")},
    ]
    return {
        "people": people,
        "title": f"{people} kişilik hafta sonu planı",
        "saturday_label": w["saturday_label"],
        "sunday_label": w["sunday_label"],
        "saturday": [s for s in sat_slots if s["place"]],
        "sunday": [s for s in sun_slots if s["place"]],
    }

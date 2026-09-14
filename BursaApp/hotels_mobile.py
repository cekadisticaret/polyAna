"""Mobil oteller listesi — web /oteller ile aynı filtre/sıralama."""
from __future__ import annotations

import json
import os
import re

from catalog import ILCELER, place_public, query_places, subcategories_for

_DIR = os.path.dirname(os.path.abspath(__file__))
_PRICE_META_PATH = os.path.join(_DIR, "data", "hotels_price_meta.json")


def hotel_price_meta() -> dict:
    if not os.path.isfile(_PRICE_META_PATH):
        return {}
    try:
        with open(_PRICE_META_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def hotel_price_tl(place: dict) -> int | None:
    """Örnek gecelik fiyat — extra.price_min metninden TL tamsayı."""
    raw = ""
    extra = place.get("extra") or {}
    if isinstance(extra, dict):
        raw = (extra.get("price_min") or extra.get("price_max") or "").strip()
    if not raw:
        est = int(place.get("est_meal_tl") or 0)
        return est if est > 0 else None
    digits = re.sub(r"[^\d]", "", raw.split(",")[0])
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def hotel_badge_label(place: dict) -> str:
    band = (place.get("price_band") or "sehir").lower()
    if band == "termal":
        return "TERMAL"
    if band == "uludag":
        return "ULUDAĞ"
    sub = (place.get("subcategory_label") or "").strip()
    return sub.upper() if sub else "OTEL"


def hotel_price_label(place: dict) -> str:
    extra = place.get("extra") or {}
    if isinstance(extra, dict):
        raw = (extra.get("price_min") or extra.get("price_max") or "").strip()
        if raw:
            return raw
    return "Fiyat sor"


def build_hotels_payload(
    db,
    *,
    q: str = "",
    ilce: str = "",
    sub: str = "",
    band: str = "",
    sort: str = "rating",
    price_filter: str = "",
    limit: int = 300,
) -> dict:
    q = (q or "").strip()
    ilce = (ilce or "").strip()
    sub = (sub or "").strip()
    band = (band or "").strip().lower()
    sort = (sort or "rating").strip().lower()
    if sort not in ("rating", "price_asc", "price_desc"):
        sort = "rating"
    price_filter = (price_filter or "").strip().lower()

    rows, _ = query_places(
        db,
        category="hotel",
        ilce=ilce or None,
        q=q or None,
        subcategory=sub or None,
        order="rating",
        limit=limit,
    )
    places = [place_public(p) for p in rows]
    for p in places:
        p["price_tl"] = hotel_price_tl(p)
        p["badge_label"] = hotel_badge_label(p)
        p["price_label"] = hotel_price_label(p)

    if band and not ilce:
        places = [p for p in places if (p.get("price_band") or "").lower() == band]
    if price_filter == "lt10":
        places = [p for p in places if (p.get("price_tl") or 10**9) < 10000]
    elif price_filter == "10-18":
        places = [p for p in places if p.get("price_tl") is not None and 10000 <= p["price_tl"] < 18000]
    elif price_filter == "18plus":
        places = [p for p in places if (p.get("price_tl") or 0) >= 18000]

    if sort == "price_asc":
        places.sort(
            key=lambda p: (
                p.get("price_tl") is None,
                p.get("price_tl") or 10**9,
                (p.get("title") or ""),
            )
        )
    elif sort == "price_desc":
        places.sort(
            key=lambda p: (
                p.get("price_tl") is None,
                -(p.get("price_tl") or 0),
                (p.get("title") or ""),
            )
        )
    else:
        places.sort(
            key=lambda p: (
                -(float(p["rating"]) if p.get("rating") is not None else -1.0),
                (p.get("title") or ""),
            )
        )

    if sort.startswith("price"):
        featured = places[:8]
    else:
        featured = [p for p in places if p.get("featured")][:8]
        if len(featured) < 4:
            featured = places[:8]

    featured_slugs = [p.get("slug") for p in featured if p.get("slug")]
    hero_img = ""
    for p in featured or places:
        img = (p.get("img_url") or "").strip()
        if img:
            hero_img = img
            break

    return {
        "places": places,
        "featured": featured,
        "featured_slugs": featured_slugs,
        "hero_img": hero_img,
        "districts": list(ILCELER),
        "subs": [{"key": k, "label": lab} for k, lab in subcategories_for("hotel")],
        "price_meta": hotel_price_meta(),
        "total": len(places),
        "filters": {
            "q": q,
            "ilce": ilce,
            "sub": sub,
            "band": band,
            "sort": sort,
            "price": price_filter,
        },
    }

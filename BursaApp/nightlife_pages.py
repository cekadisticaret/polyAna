"""Gece hayatı listesi — öne çıkan mekanlar, marka önceliği, gruplama."""
from __future__ import annotations

import os

_DIR = os.path.dirname(os.path.abspath(__file__))

# seed_nightlife_media.py hero-nightclub.jpg indirir
NIGHTLIFE_HERO = "/static/cache/nightlife/hero-nightclub.jpg"

STALE_IMG_MARKERS = (
    "kale-sokak",
    "cafe-cover",
    "/static/visit/",
    "/static/fun/",
    "uludag.jpg",
    "suuctu.jpg",
)

SUBCAT_IMG = {
    "gece-kulubu": "gece-kulubu",
    "bar": "bar",
    "pub": "pub",
    "meyhane": "meyhane",
    "canli-muzik": "canli-muzik",
    "gazino": "gazino",
    "karaoke": "karaoke",
    "lounge": "lounge",
}

FEATURED_SLUGS = frozenset(
    {
        "club-inferno-bursa",
        "sess-16-club",
        "tren-bursa",
        "bongo-night-club",
        "nox-live",
        "opus-live-bursa",
        "arap-sukru-bursa",
        "danza-gece-kulubu",
    }
)

BRAND_NEEDLES: tuple[tuple[str, int], ...] = (
    ("inferno", 1),
    ("bongo", 2),
    ("nox", 3),
    ("opus live", 4),
    ("opus", 4),
    ("arap şükrü", 5),
    ("arap sukru", 5),
    ("hayal kahvesi", 6),
    ("sess 16", 7),
    ("tren bursa", 8),
    ("danza", 9),
    ("suare", 10),
    ("kat 3", 11),
    ("sahne bursa", 12),
)


def nightlife_brand_rank(place: dict) -> int:
    text = f"{place.get('title') or ''} {place.get('slug') or ''}".lower()
    best = 99
    for needle, rank in BRAND_NEEDLES:
        if needle in text:
            best = min(best, rank)
    if (place.get("slug") or "") in FEATURED_SLUGS:
        best = min(best, 20)
    return best


def sort_nightlife_places(places: list[dict]) -> list[dict]:
    def key(p: dict):
        sub = (p.get("subcategory") or "").lower()
        if sub == "gece-kulubu":
            sub_pri = 0
        elif sub in ("bar", "canli-muzik", "lounge", "pub"):
            sub_pri = 1
        elif sub == "meyhane":
            sub_pri = 2
        else:
            sub_pri = 3
        return (
            sub_pri,
            nightlife_brand_rank(p),
            0 if p.get("featured") else 1,
            -(float(p["rating"]) if p.get("rating") is not None else -1.0),
            (p.get("title") or "").lower(),
        )

    return sorted(places, key=key)


def pick_featured(places: list[dict], limit: int = 6) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for p in places:
        slug = p.get("slug") or ""
        if slug in seen:
            continue
        if p.get("featured") or nightlife_brand_rank(p) <= 10:
            out.append(p)
            seen.add(slug)
        if len(out) >= limit:
            break
    if len(out) < limit:
        for p in places:
            slug = p.get("slug") or ""
            if slug in seen:
                continue
            out.append(p)
            seen.add(slug)
            if len(out) >= limit:
                break
    return out


def nightlife_image_key(p) -> str:
    sub = (getattr(p, "subcategory", None) or p.get("subcategory") or "").lower()
    if sub in SUBCAT_IMG:
        return SUBCAT_IMG[sub]
    title = (getattr(p, "title", None) or p.get("title") or "").lower()
    if "pub" in title:
        return "pub"
    if "meyhane" in title or "fasil" in title or "rakı" in title or "raki" in title:
        return "meyhane"
    if "gazino" in title:
        return "gazino"
    if "kulüp" in title or "kulup" in title or "club" in title:
        return "gece-kulubu"
    if "live" in title or "sahne" in title or "konser" in title:
        return "canli-muzik"
    if "karaoke" in title:
        return "karaoke"
    if "lounge" in title:
        return "lounge"
    return "bar"


def needs_nightlife_image(img_url: str | None) -> bool:
    if not img_url:
        return True
    low = img_url.lower()
    if any(m in low for m in STALE_IMG_MARKERS):
        return True
    rel = img_url.lstrip("/")
    if rel.startswith("static/cache/nightlife/"):
        return not os.path.isfile(os.path.join(_DIR, rel))
    return not os.path.isfile(os.path.join(_DIR, rel))


def group_nightlife_places(places: list[dict], sub_chips: list[tuple[str, str]]) -> list[dict]:
    order = [lab for _, lab in sub_chips]
    by: dict[str, list] = {}
    for p in places:
        lab = p.get("subcategory_label") or "Diğer"
        by.setdefault(lab, []).append(p)
    groups = []
    for lab in order:
        if lab in by:
            groups.append({"label": lab, "places": by.pop(lab)})
    for lab, plist in sorted(by.items()):
        groups.append({"label": lab, "places": plist})
    return groups

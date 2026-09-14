"""Spor listesi — marka önceliği, görsel eşleme, sıralama."""
from __future__ import annotations

import os

_DIR = os.path.dirname(os.path.abspath(__file__))

# Bilinen zincir / marka — düşük rank = üstte
SPORT_BRAND_NEEDLES: tuple[tuple[str, int], ...] = (
    ("macfit", 1),
    ("mac fit", 1),
    ("sportown", 2),
    ("world gym", 3),
    ("world fitness", 3),
    ("fitness first", 4),
    ("gold's gym", 5),
    ("golds gym", 5),
    ("euphoria fitness", 6),
    ("bfc club", 7),
    ("maestro sports", 8),
    ("ennfit", 9),
    ("tfa fitness", 10),
    ("flexi gym", 11),
    ("nilfit", 12),
    ("sportpark", 13),
    ("sporpark", 13),
    ("sunviva", 14),
    ("macfitclub", 1),
)

SUBCAT_IMG = {
    "fitness": "gym",
    "pilates": "yoga",
    "yoga": "yoga",
    "yuzme": "pool",
    "tenis": "tennis",
    "hali-saha": "football",
    "dovus": "boxing",
}

FEATURED_SLUGS = frozenset(
    {
        "macfit-nilufer",
        "osm-spor-macfit",
        "osm-spor-sportown",
    }
)

SPORT_HERO = "/static/cache/sport/hero-fitness.jpg"


def sport_brand_rank(place: dict) -> int:
    text = f"{place.get('title') or ''} {place.get('slug') or ''}".lower()
    best = 99
    for needle, rank in SPORT_BRAND_NEEDLES:
        if needle in text:
            best = min(best, rank)
    return best


def sport_image_key(p) -> str:
    sub = (getattr(p, "subcategory", None) or p.get("subcategory") or "").lower()
    if sub in SUBCAT_IMG:
        return SUBCAT_IMG[sub]
    title = (getattr(p, "title", None) or p.get("title") or "").lower()
    if any(x in title for x in ("yüzme", "yuzme", "havuz", "pool", "yüzme")):
        return "pool"
    if "tenis" in title or "kort" in title:
        return "tennis"
    if any(x in title for x in ("halı", "hali", "futbol", "saha", "stadyum")):
        return "football"
    if any(x in title for x in ("kickboks", "mma", "boks", "dövüş", "dovus")):
        return "boxing"
    if "yoga" in title or "pilates" in title:
        return "yoga"
    if "fitness" in title or "gym" in title or "spor merkezi" in title:
        return "gym"
    return "gym"


def needs_sport_image(img_url: str | None) -> bool:
    if not img_url:
        return True
    if "uludag.jpg" in img_url or "suuctu.jpg" in img_url:
        return True
    rel = img_url.lstrip("/")
    return not os.path.isfile(os.path.join(_DIR, rel))


def sort_sport_places(places: list[dict]) -> list[dict]:
    def key(p: dict):
        sub = (p.get("subcategory") or "").lower()
        if sub == "fitness":
            sub_pri = 0
        elif sub in ("yoga", "pilates", "yuzme", "tenis", "hali-saha", "dovus"):
            sub_pri = 1
        else:
            sub_pri = 2
        return (
            sub_pri,
            sport_brand_rank(p),
            0 if p.get("featured") else 1,
            -(float(p["rating"]) if p.get("rating") is not None else -1.0),
            (p.get("title") or "").lower(),
        )

    return sorted(places, key=key)


def group_sport_places(places: list[dict], sub_chips: list[tuple[str, str]]) -> list[dict]:
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

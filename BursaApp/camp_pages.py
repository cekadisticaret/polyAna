"""Kamp listesi — öne çıkan alanlar, vibe sıralaması."""
from __future__ import annotations

CAMP_HERO = "/static/cache/thumbs/golyazi-kamp-35b982f1cc5ae775-640.jpg"

FEATURED_SLUGS = frozenset(
    {
        "golyazi-uluabat-gun-batimi",
        "kapanca-korsan-limani",
        "cobankaya-kamp-alani",
        "seytan-sofrasi-kamp",
        "dagyenice-goleti",
        "sadagi-kanyonu",
        "karacabey-longoz-ormanlari",
        "ortunc-koyu",
    }
)

VIBE_CHIPS: tuple[tuple[str, str, str], ...] = (
    ("", "Tümü", "⛺"),
    ("instagram", "Favori", "⭐"),
    ("uludag", "Uludağ", "🏔"),
    ("deniz", "Deniz", "🌊"),
    ("gol", "Göl", "💧"),
    ("yayla", "Yayla", "🌿"),
    ("kanyon", "Kanyon", "🪨"),
    ("ucretsiz", "Ücretsiz", "🆓"),
    ("balikesir", "Balıkesir", "🛤"),
)


def pick_featured(places: list[dict], limit: int = 6) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for p in places:
        slug = p.get("slug") or ""
        if slug in seen:
            continue
        if p.get("featured") or slug in FEATURED_SLUGS:
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


def price_label(place: dict) -> str:
    band = (place.get("price_band") or "").lower()
    if "ücretsiz" in band or "ucretsiz" in band:
        return "Ücretsiz"
    if "tesis" in band or "milli" in band:
        return place.get("price_band") or "Tesisli"
    return place.get("price_band") or place.get("hours_text") or "Kamp alanı"


def location_label(place: dict) -> str:
    ex = place.get("extra") or {}
    city = (ex.get("city") or "").strip()
    ilce = (place.get("ilce") or "").strip()
    if city and ilce:
        return f"{city}, {ilce}"
    return ilce or city or "Bursa"

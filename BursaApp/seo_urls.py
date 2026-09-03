"""Yer SEO yolu + rezerve /bursa-* anahtarları."""
from __future__ import annotations

# SEO landing / meşhur yemek path'leri — yer slug'ı bunlarla çakışmasın
RESERVED_BURSA_PATHS = {
    "bursa-da-ne-yenir",
    "bursa-restoranlari",
    "bursa-cafeler",
    "bursa-kahvalti",
    "bursa-kahvalti-mekanlari",
    "bursa-konserleri",
    "bursa-tiyatro",
    "bursa-gezilecek-yerler",
    "bursa-iskender",
    "bursa-inegol-kofte",
    "bursa-kemalpasa",
    "bursa-pideli-kofte",
    "bursa-kestane-sekeri",
    "bursa-sut-helvasi",
}

# Bu kategoriler /bursa-{slug} SEO URL kullanır
SEO_PATH_CATEGORIES = {
    "visit",
    "food",
    "hotel",
    "camp",
    "hospital",
    "doctor",
    "dentist",
    "vet",
    "school",
    "shop",
    "market",
    "sport",
    "family",
    "fun",
    "org",
}


def place_seo_path(p) -> str:
    """Kart / detay linki — örn. /bursa-ulu-cami."""
    slug = (getattr(p, "slug", None) or "").strip().strip("/")
    cat = (getattr(p, "category", None) or "").strip()
    if not slug:
        return "/"
    if cat in SEO_PATH_CATEGORIES:
        key = slug if slug.startswith("bursa-") else f"bursa-{slug}"
        if key not in RESERVED_BURSA_PATHS:
            return f"/{key}"
    return f"/yer/{slug}"


def path_to_place_slug(path_slug: str) -> str:
    """bursa-ulu-cami → ulu-cami."""
    s = (path_slug or "").strip().strip("/")
    if s.startswith("bursa-"):
        return s[6:]
    return s

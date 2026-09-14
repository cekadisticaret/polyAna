#!/usr/bin/env python3
"""Spor mekanları — fitness görselleri + bilinen markaları öne çıkar.

  python3 seed_sport_media.py
"""
from __future__ import annotations

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from enrich_media_content import IMG
from media_cache import ensure_cached
from models import Place, SessionLocal, init_db
from sport_pages import FEATURED_SLUGS, needs_sport_image, sport_image_key

# Ek fitness görselleri (döngü çeşitliliği — yalnız doğrulanmış URL)
EXTRA_IMG = {
    "gym2": "https://commons.wikimedia.org/wiki/Special:FilePath/Exercise_equipment.jpg?width=1200",
    "hero": "https://commons.wikimedia.org/wiki/Special:FilePath/Gym.jpg?width=1600",
    "pool2": "https://commons.wikimedia.org/wiki/Special:FilePath/Swimming_pool.jpg?width=1200",
}

ALL_IMG = {**IMG, **EXTRA_IMG}


def _cache(key: str, filename: str) -> str | None:
    url = ALL_IMG.get(key)
    if not url:
        return None
    out = ensure_cached(url, category="sport", filename=filename)
    if out:
        return out
    if key not in ("gym", "gym2"):
        return _cache("gym", filename)
    return None


def main() -> None:
    init_db()
    db = SessionLocal()
    hero = _cache("hero", "hero-fitness.jpg")
    n_img = n_feat = 0
    gym_variants = ["gym", "gym2"]
    pool_keys = ["pool", "pool2"]
    try:
        rows = db.query(Place).filter(Place.category == "sport", Place.status == "approved").all()
        for i, p in enumerate(rows):
            if p.slug in FEATURED_SLUGS or sport_brand_rank_place(p) <= 14:
                if not p.featured:
                    p.featured = True
                    n_feat += 1
            stale = needs_sport_image(p.img_url)
            if stale or "uludag.jpg" in (p.img_url or "") or "suuctu.jpg" in (p.img_url or ""):
                base_key = sport_image_key(p)
                if base_key == "gym":
                    key = gym_variants[i % len(gym_variants)]
                elif base_key == "pool":
                    key = pool_keys[i % len(pool_keys)]
                else:
                    key = base_key
                url = _cache(key, f"{p.slug}.jpg")
                if url:
                    p.img_url = url
                    n_img += 1
        db.commit()
        print(f"seed_sport_media: imgs={n_img} featured+={n_feat} hero={hero or 'skip'}")
    finally:
        db.close()


def sport_brand_rank_place(p: Place) -> int:
    from sport_pages import sport_brand_rank

    return sport_brand_rank({"title": p.title, "slug": p.slug})


if __name__ == "__main__":
    main()

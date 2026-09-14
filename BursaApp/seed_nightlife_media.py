#!/usr/bin/env python3
"""Gece hayatı görselleri — stok ev/sokak yerine bar/kulüp/meyhane + bilinen mekânlar.

  python3 seed_nightlife_media.py
  python3 seed_nightlife_media.py --slug club-inferno-bursa
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from enrich_food_venues import commons_search, score_hit
from enrich_media_content import IMG
from media_cache import ensure_cached
from models import Place, SessionLocal, init_db, merge_place_extra, place_extra
from nightlife_pages import FEATURED_SLUGS, needs_nightlife_image, nightlife_image_key

UA = {"User-Agent": "Mozilla/5.0 (compatible; BursaApp/1.0; +https://bursaapp.com)"}
DATA = os.path.join(_DIR, "data", "nightlife_venues.json")

# Mekân / marka — doğrulanmış URL (Commons veya resmi site)
CURATED_PHOTOS: dict[str, str] = {
    "hayal-kahvesi-ozluce": "https://upload.wikimedia.org/wikipedia/commons/a/a4/Berke_%C3%96zg%C3%BCm%C3%BC%C5%9F_in_Bursa_Hayal_Kahvesi.JPG",
    "club-inferno-bursa": "https://commons.wikimedia.org/wiki/Special:FilePath/San_Francisco_Club_X_big_room_2023.jpg?width=1200",
    "sess-16-club": "https://commons.wikimedia.org/wiki/Special:FilePath/XS_Nightclub_Las_Vegas_Interior_Lamps.jpg?width=1200",
    "tren-bursa": "https://commons.wikimedia.org/wiki/Special:FilePath/Womb_Nightclub_Tokyo.jpg?width=1200",
    "danza-gece-kulubu": "https://commons.wikimedia.org/wiki/Special:FilePath/Uniun_Nightclub_Toronto.jpg?width=1200",
    "bongo-bar": "https://commons.wikimedia.org/wiki/Special:FilePath/The_APX_performing_at_Center_Stage_Atlanta.jpg?width=1200",
    "bongo-night-club": "https://commons.wikimedia.org/wiki/Special:FilePath/The_APX_performing_at_Center_Stage_Atlanta.jpg?width=1200",
    "nox-club": "https://commons.wikimedia.org/wiki/Special:FilePath/Girls_dancing_in_a_nightclub_2004.jpg?width=1200",
    "nox-live": "https://commons.wikimedia.org/wiki/Special:FilePath/Girls_dancing_in_a_nightclub_2004.jpg?width=1200",
    "opus-live": "https://commons.wikimedia.org/wiki/Special:FilePath/The_APX_performing_at_Center_Stage_Atlanta.jpg?width=1200",
    "opus-live-bursa": "https://commons.wikimedia.org/wiki/Special:FilePath/The_APX_performing_at_Center_Stage_Atlanta.jpg?width=1200",
    "meyhane-i-salas": "https://commons.wikimedia.org/wiki/Special:FilePath/%C3%87ukur_Meyhane_1.jpg?width=1200",
    "arap-sukru-sokagi": "https://commons.wikimedia.org/wiki/Special:FilePath/Meyhane.jpg?width=1200",
    "arap-sukru-bursa": "https://commons.wikimedia.org/wiki/Special:FilePath/Meyhane.jpg?width=1200",
    "suare-gece": "https://commons.wikimedia.org/wiki/Special:FilePath/Dancing_in_a_nightclub_2004.jpg?width=1200",
    "club-dess-mudanya": "https://commons.wikimedia.org/wiki/Special:FilePath/Dancing_in_a_nightclub_2004.jpg?width=1200",
    "kat-3-bursa": "https://commons.wikimedia.org/wiki/Special:FilePath/Interior_of_Last_Tuesday_Society_cocktail_bar.jpg?width=1200",
}

EXTRA_IMG = {
    "hero": "https://commons.wikimedia.org/wiki/Special:FilePath/San_Francisco_Club_X_big_room_2023.jpg?width=1600",
    "gece-kulubu": "https://commons.wikimedia.org/wiki/Special:FilePath/Dancing_in_a_nightclub_2004.jpg?width=1200",
    "gece-kulubu2": "https://commons.wikimedia.org/wiki/Special:FilePath/XS_Nightclub_Las_Vegas_Interior_Lamps.jpg?width=1200",
    "gece-kulubu3": "https://commons.wikimedia.org/wiki/Special:FilePath/Womb_Nightclub_Tokyo.jpg?width=1200",
    "gece-kulubu4": "https://commons.wikimedia.org/wiki/Special:FilePath/Uniun_Nightclub_Toronto.jpg?width=1200",
    "bar": "https://commons.wikimedia.org/wiki/Special:FilePath/Interior_of_Czeczotka_Cocktail_Bar%2C_Krak%C3%B3w%2C_2019.jpg?width=1200",
    "bar2": "https://commons.wikimedia.org/wiki/Special:FilePath/Bartender_at_Sylvarum_cocktail_bar%2C_Alicante.jpg?width=1200",
    "bar3": "https://commons.wikimedia.org/wiki/Special:FilePath/Interior_of_Last_Tuesday_Society_cocktail_bar.jpg?width=1200",
    "pub": "https://commons.wikimedia.org/wiki/Special:FilePath/Pub_interior_-_geograph.org.uk_-_555584.jpg?width=1200",
    "pub2": "https://commons.wikimedia.org/wiki/Special:FilePath/Sir_Alexander_Fleming_pub_interior%2C_Paddington.jpg?width=1200",
    "meyhane": "https://commons.wikimedia.org/wiki/Special:FilePath/Meyhane.jpg?width=1200",
    "meyhane2": "https://commons.wikimedia.org/wiki/Special:FilePath/%C3%87ukur_Meyhane_1.jpg?width=1200",
    "meyhane3": "https://commons.wikimedia.org/wiki/Special:FilePath/%C3%87ukur_Meyhane_4.jpg?width=1200",
    "canli-muzik": "https://commons.wikimedia.org/wiki/Special:FilePath/The_APX_performing_at_Center_Stage_Atlanta.jpg?width=1200",
    "canli-muzik2": "https://commons.wikimedia.org/wiki/Special:FilePath/Girls_dancing_in_a_nightclub_2004.jpg?width=1200",
    "canli-muzik3": "https://commons.wikimedia.org/wiki/Special:FilePath/XS_Nightclub_Las_Vegas_Interior_Lamps.jpg?width=1200",
    "gazino": "https://commons.wikimedia.org/wiki/Special:FilePath/Girls_dancing_in_a_nightclub_2004.jpg?width=1200",
    "karaoke": "https://commons.wikimedia.org/wiki/Special:FilePath/Interior_of_Last_Tuesday_Society_cocktail_bar.jpg?width=1200",
    "lounge": "https://commons.wikimedia.org/wiki/Special:FilePath/Interior_of_Czeczotka_Cocktail_Bar%2C_Krak%C3%B3w%2C_2019.jpg?width=1200",
    "raki": IMG["raki"],
}

POOL_KEYS: dict[str, list[str]] = {
    "gece-kulubu": ["gece-kulubu", "gece-kulubu2", "gece-kulubu3", "gece-kulubu4"],
    "bar": ["bar", "bar2", "bar3"],
    "pub": ["pub", "pub2"],
    "meyhane": ["meyhane", "meyhane2", "meyhane3", "raki"],
    "canli-muzik": ["canli-muzik", "canli-muzik2", "canli-muzik3"],
    "gazino": ["gazino", "gece-kulubu2"],
    "karaoke": ["karaoke", "lounge"],
    "lounge": ["lounge", "bar2"],
}


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def og_image(url: str) -> str | None:
    if not url or not url.startswith("http"):
        return None
    try:
        html = _get(url, timeout=18).decode("utf-8", "ignore")[:80000]
    except Exception:
        return None
    for pat in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
    ):
        m = re.search(pat, html, re.I)
        if m:
            u = m.group(1).strip()
            if u and not u.endswith(".svg"):
                return u
    return None


def _cache(url: str, filename: str) -> str | None:
    if not url:
        return None
    out = ensure_cached(url, category="nightlife", filename=filename)
    if out:
        return out
    # Bozuk URL — aynı kategoride çalışan yedek
    fallback = EXTRA_IMG.get("bar")
    if fallback and fallback != url:
        return ensure_cached(fallback, category="nightlife", filename=filename)
    return None


def pool_key_for_slug(slug: str, base: str) -> str:
    keys = POOL_KEYS.get(base, POOL_KEYS["bar"])
    idx = int(hashlib.md5(slug.encode()).hexdigest(), 16) % len(keys)
    return keys[idx]


def commons_photo(title: str, sub: str) -> str | None:
    queries = [f"{title} Bursa", f"{title} gece", title]
    best_url = None
    best_score = 0.42
    for q in queries:
        if not q:
            continue
        time.sleep(0.4)
        try:
            hits = commons_search(q, limit=6)
        except Exception:
            continue
        for h in hits:
            fl = h["title"].lower()
            if any(x in fl for x in ("plant", "flower", "map", "logo", "coat")):
                continue
            sc = score_hit(title, h["title"], sub)
            if sub == "gece-kulubu" and any(x in fl for x in ("club", "night", "disc", "dj")):
                sc += 0.12
            if sub == "meyhane" and "meyhane" in fl:
                sc += 0.25
            if sub == "canli-muzik" and any(x in fl for x in ("stage", "concert", "live", "music")):
                sc += 0.12
            if "bursa" in fl and "pastoris" not in fl:
                sc += 0.2
            if sc > best_score:
                best_score = sc
                best_url = h["url"]
        if best_score >= 0.72:
            break
    return best_url


def pick_source(p: Place, raw: dict | None) -> tuple[str | None, str]:
    slug = p.slug or ""
    if slug in CURATED_PHOTOS:
        return CURATED_PHOTOS[slug], "curated"

    ex = place_extra(p)
    for src in ((raw or {}).get("photo_url"), ex.get("photo_url")):
        if src and src.startswith("http"):
            return src, "extra"

    if p.web:
        og = og_image(p.web)
        if og:
            return og, "og:image"

    sub = nightlife_image_key(p)
    c = commons_photo(p.title or "", sub)
    if c:
        return c, "commons"

    key = pool_key_for_slug(slug, sub)
    url = EXTRA_IMG.get(key) or EXTRA_IMG.get(sub) or EXTRA_IMG["bar"]
    return url, f"pool:{key}"


def apply_photo(p: Place, raw: dict | None, force: bool) -> tuple[bool, str]:
    if not force and not needs_nightlife_image(p.img_url):
        return False, "keep"
    src, note = pick_source(p, raw)
    if not src:
        return False, "skip"
    fname = f"{p.slug}.jpg"
    cached = _cache(src, fname)
    if not cached:
        return False, f"fail:{note}"
    p.img_url = cached
    merge_place_extra(p, {"photo_url": src, "photo_source": note})
    return True, note


def load_raw_by_slug() -> dict[str, dict]:
    if not os.path.isfile(DATA):
        return {}
    payload = json.load(open(DATA, encoding="utf-8"))
    rows = payload.get("venues") or payload
    if isinstance(rows, dict):
        rows = list(rows.values())
    return {r["slug"]: r for r in rows if r.get("slug")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="Tek mekân")
    ap.add_argument("--force", action="store_true", help="Mevcut nightlife cache dışı görselleri de yenile")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    raw_map = load_raw_by_slug()
    hero = _cache(EXTRA_IMG["hero"], "hero-nightclub.jpg")
    n_img = n_feat = 0
    try:
        q = db.query(Place).filter(Place.category == "nightlife", Place.status == "approved")
        if args.slug:
            q = q.filter(Place.slug == args.slug)
        rows = q.all()
        for p in rows:
            if p.slug in FEATURED_SLUGS and not p.featured:
                p.featured = True
                n_feat += 1
            ok, note = apply_photo(p, raw_map.get(p.slug), force=args.force or bool(args.slug))
            if ok:
                n_img += 1
                print(f"  {p.slug}: {note}")
        db.commit()
        print(f"seed_nightlife_media: imgs={n_img} featured+={n_feat} hero={hero or 'skip'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

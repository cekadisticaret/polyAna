#!/usr/bin/env python3
"""Bursa burger rehberi — kapsamlı seed + işletme görseli.

  python3 seed_burger_bursa.py
  python3 seed_burger_bursa.py --photos-only
  python3 seed_burger_bursa.py --slug otto-burger-altinsehir
"""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import slugify, tags_dump
from enrich_food_venues import commons_search, score_hit, is_stock
from media_cache import ensure_cached
from models import Place, SessionLocal, init_db, merge_place_extra, place_extra

UA = {"User-Agent": "Mozilla/5.0 (compatible; BursaApp/1.0; +https://bursaapp.com)"}
DATA = os.path.join(_DIR, "data", "burgers_bursa.json")

BRAND_PHOTOS = {
    "mcdonalds": "https://commons.wikimedia.org/wiki/Special:FilePath/Big_Mac_hamburger_%28US%29.jpg?width=1200",
    "burger king": "https://commons.wikimedia.org/wiki/Special:FilePath/Whooper.jpg?width=1200",
    "kfc": "https://commons.wikimedia.org/wiki/Special:FilePath/KFC_Original_Recipe_Pressing.jpg?width=1200",
    "carl's jr": "https://commons.wikimedia.org/wiki/Special:FilePath/Carl%27s_Jr_6_Dollar_Burger.jpg?width=1200",
}

FALLBACK_POOL = [
    "https://commons.wikimedia.org/wiki/Special:FilePath/Cheeseburger.jpg?width=1200",
    "https://commons.wikimedia.org/wiki/Special:FilePath/Hamburger_%282%29.jpg?width=1200",
    "https://commons.wikimedia.org/wiki/Special:FilePath/McDonald%27s_Quarter_Pounder_with_Cheese%2C_United_States.jpg?width=1200",
    "https://commons.wikimedia.org/wiki/Special:FilePath/Homemade_burger.jpg?width=1200",
    "https://commons.wikimedia.org/wiki/Special:FilePath/Whooper.jpg?width=1200",
    "https://commons.wikimedia.org/wiki/Special:FilePath/Big_Mac_hamburger_%28US%29.jpg?width=1200",
    "https://commons.wikimedia.org/wiki/Special:FilePath/Foodphotography.jpg?width=1200",
]

# İşletme / marka görselleri (site veya Commons — stok değil)
CURATED_PHOTOS: dict[str, str] = {
    "too-burger-ozluce": "https://tooburger.com/trash/menu-burger.png",
    "too-burger-gecit": "https://tooburger.com/trash/slider-1.png",
    "too-burger-ardic-park": "https://tooburger.com/trash/slider-2.png",
    "burgy-burgers-more": "https://commons.wikimedia.org/wiki/Special:FilePath/Cheeseburger.jpg?width=1200",
    "osm-fast_food-islak-hamburger": "https://commons.wikimedia.org/wiki/Special:FilePath/Turkish%20fast%20food.jpg?width=1200",
}


def _get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def og_image(url: str) -> str | None:
    if not url or not url.startswith("http"):
        return None
    try:
        html = _get(url, timeout=20).decode("utf-8", "ignore")[:80000]
    except Exception:
        return None
    for pat in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


def site_images(base_url: str) -> list[str]:
    if not base_url.startswith("http"):
        return []
    try:
        html = _get(base_url, timeout=20).decode("utf-8", "ignore")
    except Exception:
        return []
    root = urllib.parse.urljoin(base_url, "/")
    out: list[str] = []
    for src in re.findall(r'(?:src|href)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)', html, re.I):
        if any(x in src.lower() for x in ("logo", "icon", "favicon", "sprite")):
            continue
        out.append(urllib.parse.urljoin(root, src))
    return out[:12]


def menu_text(raw: dict) -> str:
    menu = raw.get("menu") or []
    if not menu:
        return ""
    note = "Not: fiyatlar yaklaşık (2026); güncel menü için mekânı ara."
    return "\n".join(menu + [note])


def upsert(db, raw: dict) -> Place:
    slug = raw["slug"]
    tags = list(raw.get("tags") or ["burger"])
    if "burger" not in tags:
        tags.insert(0, "burger")
    body = (raw.get("body") or raw.get("blurb") or "")[:8000]
    est = raw.get("est_meal_tl")
    fields = dict(
        title=raw["title"][:200],
        category="food",
        subcategory="burger",
        ilce=raw.get("ilce") or "Osmangazi",
        address=(raw.get("address") or "")[:280],
        lat=raw.get("lat"),
        lng=raw.get("lng"),
        phone=(raw.get("phone") or "")[:40],
        web=(raw.get("web") or "")[:280],
        hours_text=(raw.get("hours_text") or "")[:160],
        price_band="burger",
        blurb=(raw.get("blurb") or "")[:400],
        body=body,
        tags=tags_dump(tags),
        rating_admin=raw.get("rating_admin"),
        featured=bool(raw.get("featured")),
        status="approved",
        est_meal_tl=int(est) if est else None,
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        p = Place(slug=slug, img_url="", **fields)
        db.add(p)
        db.flush()
    else:
        for k, v in fields.items():
            if k in ("lat", "lng") and v is None:
                continue
            if k == "rating_admin" and v is None:
                continue
            setattr(p, k, v)
    mt = menu_text(raw)
    if mt:
        p.menu_text = mt
    merge_place_extra(
        p,
        {
            "brand": raw.get("brand") or "",
            "photo_url": raw.get("photo_url") or CURATED_PHOTOS.get(slug) or "",
            "search_photo": raw.get("search_photo") or "",
            "source": "burger_research_2026",
        },
    )
    return p


def pick_photo(p: Place, raw: dict | None, force: bool) -> tuple[str | None, str]:
    if not force and p.img_url and not is_stock(p.img_url):
        return p.img_url, "keep"

    slug = p.slug
    ex = place_extra(p)

    candidates: list[tuple[str, str]] = []
    for src in (
        (raw or {}).get("photo_url"),
        ex.get("photo_url"),
        CURATED_PHOTOS.get(slug),
    ):
        if src:
            candidates.append((src, "direct"))

    brand = ((raw or {}).get("brand") or ex.get("brand") or "").lower()
    for key, url in BRAND_PHOTOS.items():
        if key in brand or key.replace(" ", "") in slug.replace("-", ""):
            candidates.append((url, f"brand:{key}"))

    if p.web:
        og = og_image(p.web)
        if og:
            candidates.append((og, "og:image"))
        for u in site_images(p.web):
            candidates.append((u, "site"))

    search_q = (raw or {}).get("search_photo") or ex.get("search_photo") or ""
    queries = [search_q, f"{p.title} Bursa burger", p.title, f"{p.title} burger"]
    best_url = None
    best_score = 0.38
    best_note = ""
    for q in queries:
        if not q:
            continue
        time.sleep(0.35)
        try:
            hits = commons_search(q)
        except Exception:
            continue
        for h in hits:
            sc = score_hit(p.title, h["title"], "burger")
            if "burger" in h["title"].lower() or "hamburger" in h["title"].lower():
                sc += 0.15
            if sc > best_score:
                best_score = sc
                best_url = h["url"]
                best_note = f"commons:{q}"
        if best_score >= 0.65:
            break
    if best_url:
        candidates.append((best_url, best_note or "commons"))

    idx = int(hashlib.md5(slug.encode()).hexdigest(), 16) % len(FALLBACK_POOL)
    candidates.append((FALLBACK_POOL[idx], f"pool:{idx}"))

    for url, note in candidates:
        if not url:
            continue
        if url.endswith(".svg"):
            continue
        local = ensure_cached(url, category="food-burger", filename=f"{slug}.jpg", min_bytes=6000)
        if local:
            return local, note

    if p.img_url and not is_stock(p.img_url):
        return p.img_url, "keep-old"
    return None, ""


def run(*, photos_only: bool, force_photo: bool, slug: str | None) -> None:
    init_db()
    rows = json.loads(open(DATA, encoding="utf-8").read())
    if slug:
        rows = [r for r in rows if r["slug"] == slug]
    db = SessionLocal()
    n_up = n_photo = 0
    try:
        by_slug = {r["slug"]: r for r in rows}
        if not photos_only:
            for raw in rows:
                upsert(db, raw)
                n_up += 1
            db.commit()
            print("upsert", n_up)

        q = db.query(Place).filter(Place.category == "food", Place.status == "approved")
        if slug:
            q = q.filter(Place.slug == slug)
        else:
            slugs = {r["slug"] for r in rows}
            q = q.filter(Place.slug.in_(slugs))
        for p in q.all():
            raw = by_slug.get(p.slug)
            path, src = pick_photo(p, raw, force=force_photo)
            if path and path != p.img_url:
                p.img_url = path
                merge_place_extra(p, {"photo_source": src, "photo_enriched_at": time.strftime("%Y-%m-%d")})
                print("PHOTO", p.slug, "<-", src)
                n_photo += 1
            elif not path:
                print("MISS", p.slug)
        db.commit()
        total = db.query(Place).filter(
            Place.category == "food", Place.status == "approved", Place.subcategory == "burger"
        ).count()
        print("burger approved", total, "photos", n_photo)
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos-only", action="store_true")
    ap.add_argument("--force-photo", action="store_true")
    ap.add_argument("--slug", default="")
    args = ap.parse_args()
    run(
        photos_only=bool(args.photos_only),
        force_photo=bool(args.force_photo),
        slug=(args.slug or "").strip() or None,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""OSM delta — otel, alışveriş, spor, sinema, eğlence, aile (park).

  python3 BursaApp/seed_osm_city.py

bursaapp_nightly.py gece turunda çağrılır.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import ILCELER, slugify, tags_dump
from models import Place, SessionLocal, init_db
from seed_food_expand import BBOX, guess_ilce, overpass

UA = "BursaApp/1.0 (https://bursaapp.com)"

CATEGORY_IMG = {
    "hotel": "/static/visit/eski-kaplica.jpg",
    "shop": "/static/visit/koza-han.jpg",
    "sport": "/static/visit/uludag.jpg",
    "cinema": "/static/visit/panorama-1326.jpg",
    "fun": "/static/visit/kale-sokak.jpg",
    "family": "/static/visit/soganli-botanik.jpg",
}

# (cache_key, overpass_ql, category, subcategory, tags)
OSM_BATCHES: list[tuple[str, str, str, str, list[str]]] = [
    (
        "osm_hotel",
        f'[out:json][timeout:90];(node["tourism"="hotel"]["name"]({BBOX});way["tourism"="hotel"]["name"]({BBOX}););out center tags;',
        "hotel",
        "otel",
        ["otel", "osm"],
    ),
    (
        "osm_hostel",
        f'[out:json][timeout:90];(node["tourism"="hostel"]["name"]({BBOX});way["tourism"="hostel"]["name"]({BBOX}););out center tags;',
        "hotel",
        "pansiyon",
        ["pansiyon", "osm"],
    ),
    (
        "osm_mall",
        f'[out:json][timeout:90];(node["shop"="mall"]["name"]({BBOX});way["shop"="mall"]["name"]({BBOX}););out center tags;',
        "shop",
        "avm",
        ["avm", "alisveris", "osm"],
    ),
    (
        "osm_dept",
        f'[out:json][timeout:90];(node["shop"="department_store"]["name"]({BBOX});way["shop"="department_store"]["name"]({BBOX}););out center tags;',
        "shop",
        "magaza",
        ["magaza", "alisveris", "osm"],
    ),
    (
        "osm_cinema",
        f'[out:json][timeout:90];(node["amenity"="cinema"]["name"]({BBOX});way["amenity"="cinema"]["name"]({BBOX}););out center tags;',
        "cinema",
        "sinema",
        ["sinema", "osm"],
    ),
    (
        "osm_fitness",
        f'[out:json][timeout:90];(node["leisure"="fitness_centre"]["name"]({BBOX});way["leisure"="fitness_centre"]["name"]({BBOX}););out center tags;',
        "sport",
        "fitness",
        ["fitness", "spor", "osm"],
    ),
    (
        "osm_sports",
        f'[out:json][timeout:90];(node["leisure"="sports_centre"]["name"]({BBOX});way["leisure"="sports_centre"]["name"]({BBOX}););out center tags;',
        "sport",
        "spor",
        ["spor", "osm"],
    ),
    (
        "osm_swim",
        f'[out:json][timeout:90];(node["leisure"="swimming_pool"]["name"]({BBOX});way["leisure"="swimming_pool"]["name"]({BBOX}););out center tags;',
        "sport",
        "yuzme",
        ["yuzme", "havuz", "osm"],
    ),
    (
        "osm_bowling",
        f'[out:json][timeout:90];(node["leisure"="bowling_alley"]["name"]({BBOX});way["leisure"="bowling_alley"]["name"]({BBOX}););out center tags;',
        "fun",
        "bowling",
        ["bowling", "eglence", "osm"],
    ),
    (
        "osm_playground",
        f'[out:json][timeout:90];(node["leisure"="playground"]["name"]({BBOX});way["leisure"="playground"]["name"]({BBOX}););out center tags;',
        "family",
        "oyun-parki",
        ["aile", "cocuk", "osm"],
    ),
    (
        "osm_park_family",
        f'[out:json][timeout:90];(node["leisure"="park"]["name"]["access"!="private"]({BBOX});way["leisure"="park"]["name"]["access"!="private"]({BBOX}););out center tags;',
        "family",
        "park",
        ["park", "aile", "osm"],
    ),
]

SKIP_NAME_RE = re.compile(
    r"\b(test|deneme|xxx|private|özel\s*okul\s*test)\b",
    re.I,
)


def make_slug(title: str, *, prefix: str = "osm") -> str:
    base = slugify(title)[:72] or "mekan"
    return f"{prefix}-{base}"[:80]


def _osm_fetch(cache: str, ql: str, *, max_age_h: float | None) -> list:
    path = f"/tmp/{cache}.json"
    use_cache = os.path.isfile(path) and os.path.getsize(path) > 80
    if use_cache and max_age_h is not None:
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h > max_age_h:
            use_cache = False
    if use_cache:
        return json.load(open(path))
    els = overpass(ql)
    json.dump(els, open(path, "w"))
    time.sleep(1.2)
    return els


def _parse_elements(els: list) -> list[dict]:
    out: list[dict] = []
    for e in els:
        t = e.get("tags") or {}
        name = (t.get("name") or t.get("name:tr") or "").strip()
        if not name or len(name) < 2 or SKIP_NAME_RE.search(name):
            continue
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lng = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        street = t.get("addr:street") or ""
        house = t.get("addr:housenumber") or ""
        city = t.get("addr:city") or ""
        addr = ", ".join(x for x in (street, house, city) if x).strip()
        out.append(
            {
                "title": name[:200],
                "lat": float(lat),
                "lng": float(lng),
                "address": addr[:280],
                "phone": ((t.get("phone") or t.get("contact:phone") or "")[:40]),
                "web": ((t.get("website") or t.get("contact:website") or "")[:280]),
                "hours": ((t.get("opening_hours") or "")[:160]),
                "ilce": guess_ilce(float(lat), float(lng)),
            }
        )
    return out


def _upsert(
    db,
    *,
    slug: str,
    category: str,
    sub: str,
    title: str,
    ilce: str,
    address: str,
    lat: float | None,
    lng: float | None,
    blurb: str,
    img: str,
    tags: list[str],
    phone: str = "",
    web: str = "",
    hours: str = "",
) -> str:
    ilce_use = ilce if ilce in ILCELER else guess_ilce(lat, lng)
    fields = dict(
        title=title[:200],
        category=category,
        subcategory=sub,
        ilce=ilce_use,
        address=address or "",
        lat=lat,
        lng=lng,
        phone=phone or "",
        web=web or "",
        hours_text=hours[:160] if hours else "",
        price_band=sub,
        blurb=blurb[:400],
        body=blurb[:400],
        img_url=img or "",
        tags=tags_dump(tags),
        rating_admin=4.2,
        featured=False,
        status="approved",
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        nm = slugify(title)
        if nm and db.query(Place).filter(Place.category == category, Place.title.ilike(title)).first():
            return "skip"
        final = slug
        n = 2
        while db.query(Place).filter(Place.slug == final).first() is not None:
            final = f"{slug}-{n}"[:80]
            n += 1
        db.add(Place(slug=final, **fields))
        db.flush()
        return "new"
    if p.category != category:
        return "skip"
    for k, v in fields.items():
        if k == "img_url" and (p.img_url or "").strip() and not v:
            continue
        if k in ("blurb", "body") and (p.blurb or "") and len(p.blurb or "") > len(v or ""):
            continue
        setattr(p, k, v)
    return "upd"


def import_osm_delta(db, *, max_age_h: float | None = 16.0) -> dict:
    stats: dict[str, int] = {"new": 0, "upd": 0, "skip": 0}
    existing_titles = {slugify(p.title) for p in db.query(Place).all() if p.title}
    for cache, ql, category, sub, tags in OSM_BATCHES:
        try:
            els = _osm_fetch(cache, ql, max_age_h=max_age_h)
        except Exception as e:
            print("osm fail", cache, e, file=sys.stderr)
            continue
        pts = _parse_elements(els)
        print(f"{cache}: els={len(els)} named={len(pts)}")
        img = CATEGORY_IMG.get(category, "")
        for i, raw in enumerate(pts):
            nm = slugify(raw["title"])
            if not nm or nm in existing_titles:
                stats["skip"] += 1
                continue
            existing_titles.add(nm)
            slug = make_slug(raw["title"], prefix=f"osm-{category[:4]}")
            blurb = f"Bursa {sub} · {raw['ilce']}."
            st = _upsert(
                db,
                slug=slug,
                category=category,
                sub=sub,
                title=raw["title"],
                ilce=raw["ilce"],
                address=raw.get("address") or "",
                lat=raw.get("lat"),
                lng=raw.get("lng"),
                blurb=blurb,
                img=img,
                tags=tags,
                phone=raw.get("phone") or "",
                web=raw.get("web") or "",
                hours=raw.get("hours") or "",
            )
            stats[st] = stats.get(st, 0) + 1
        db.commit()
        print("after", cache, {k: stats[k] for k in ("new", "upd", "skip")})
    return stats


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        stats = import_osm_delta(db, max_age_h=None)
        print("DONE", stats)
    finally:
        db.close()


if __name__ == "__main__":
    main()

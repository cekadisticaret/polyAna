#!/usr/bin/env python3
"""Bursapanorama restoran listesinde olup bizde olmayanları ekler.

  python3 seed_panorama_food.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import ILCELER, infer_food_subcategory, slugify, tags_dump
from models import Place, SessionLocal, init_db

SRC_URL = "https://www.bursapanorama.com/bursa/restoranlar"
CACHE = os.path.join(_DIR, "data", "panorama_restoranlar.json")
UA = "BursaApp/1.0 (https://bursaapp.com; city guide)"

SUB_IMG = {
    "kahvalti": "/static/food/kahvalti-1.jpg",
    "kebap": "/static/food/kebapci-iskenderoglu.jpg",
    "iskender": "/static/food/iskender-4.jpg",
    "cafe": "/static/food/kahvalti-1.jpg",
    "meyhane": "/static/food/meyhane-cekirge.jpg",
    "doner": "/static/food/doner-1.jpg",
    "inegol-kofte": "/static/food/kofte-1.jpg",
    "balik": "/static/food/balik-1.jpg",
    "burger": "/static/food/doner-2.jpg",
    "bar": "/static/food/fine-1.jpg",
    "pide": "/static/food/cantikci-yildirim.jpg",
    "cantik": "/static/food/cantikci-yildirim.jpg",
    "restoran": "/static/food/fine-1.jpg",
}
SKIP_TITLE = ("hotel", "otel", "thermal", "spa hotel")


def guess_ilce(addr: str) -> str:
    a = (addr or "")
    blob = slugify(a)
    # "Nilüfer/Bursa" ilçe; "3. Nilüfer Cd." cadde — önce /ilçe kalıbı
    m = re.search(r"/\s*(Nilüfer|Osmangazi|Yıldırım|Mudanya|Gemlik|İnegöl|Kestel|Karacabey|Orhangazi|Gürsu)\b", a, re.I)
    if m:
        for ad in ILCELER:
            if ad.lower() == m.group(1).lower():
                return ad
    m = re.search(r"\b(Osmangazi|Yıldırım|Mudanya|Gemlik|İnegöl|Kestel|Karacabey)\s*/\s*Bursa", a, re.I)
    if m:
        for ad in ILCELER:
            if ad.lower() == m.group(1).lower():
                return ad
    if "niluferkoy" in blob or "nilufer-koy" in blob:
        return "Osmangazi"
    if re.search(r"nilufer\s*/\s*bursa|nilufer,|nilufer$", blob):
        return "Nilüfer"
    for ad in ILCELER:
        if ad.lower() in a.lower() or slugify(ad) in blob:
            if ad == "Nilüfer" and re.search(r"nilufer\s+(cd|cad|caddesi|sk|sokak)", blob):
                continue
            return ad
    if "osmangazi" in blob:
        return "Osmangazi"
    return "Osmangazi"


def guess_sub(title: str, tags: list[str] | None = None) -> str:
    blob = " ".join([title] + list(tags or []))
    if re.search(r"mangal|ocakbaşı|ocakbasi", title, re.I):
        blob = blob + " kebap"
    if re.search(r"köfte|kofte|pideli", title, re.I):
        blob = blob + " köfte"
    if re.search(r"kahvalt", title, re.I):
        blob = blob + " kahvalti"
    return infer_food_subcategory(blob, [title])


def fetch_listings(*, refresh: bool = False) -> list[dict]:
    if not refresh and os.path.isfile(CACHE) and os.path.getsize(CACHE) > 200:
        return json.loads(open(CACHE, encoding="utf-8").read())
    req = urllib.request.Request(SRC_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        html = r.read().decode("utf-8", "replace")
    chunks = re.findall(r'<div class="listing-item">(.*?)</article>', html, re.S)
    rows = []
    seen = set()
    for ch in chunks:
        m = re.search(r'<h3 class="title-sin_map">\s*<a href="([^"]+)">([^<]+)</a>', ch, re.S)
        if not m:
            continue
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        addr_m = re.search(r'fa-map-marker-alt"></i>\s*([^<]+)', ch)
        price_m = re.search(r"(\d[\d.]*)\s*₺", ch)
        est = 0
        if price_m:
            try:
                est = int(price_m.group(1).replace(".", ""))
            except ValueError:
                est = 0
        rows.append(
            {
                "title": title,
                "address": re.sub(r"\s+", " ", (addr_m.group(1) if addr_m else "")).strip(),
                "est_meal_tl": est if 50 <= est <= 5000 else 0,
            }
        )
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(rows, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return rows


def already_have(title: str, names: set[str]) -> bool:
    sl = slugify(title)
    if sl in names:
        return True
    # şube eki olmadan birebir (Tepe Cafe & Restaurant ↔ Tepe Cafe)
    core = re.sub(r"-(cafe|restaurant|restoran|lounge|bistro)$", "", sl).strip("-")
    if core and core in names:
        return True
    return False


def upsert(db, raw: dict) -> str:
    from models import merge_place_extra

    title = raw["title"]
    slug = slugify(title)[:80]
    sub = guess_sub(title)
    ilce = guess_ilce(raw.get("address") or "")
    img = SUB_IMG.get(sub) or SUB_IMG["restoran"]
    blurb = f"{ilce} · {title}. {raw.get('address') or ''}".strip()[:400]
    price = "$" if sub in ("fast-food", "doner", "pastane", "tatli") else "$$"
    fields = dict(
        title=title[:200],
        category="food",
        subcategory=sub,
        ilce=ilce if ilce in ILCELER else "Osmangazi",
        address=(raw.get("address") or "")[:280],
        phone="",
        web="",
        hours_text="",
        price_band=price,
        blurb=blurb,
        body=blurb,
        img_url=img,
        tags=tags_dump([sub, "restoran", "panorama"]),
        rating_admin=None,
        featured=False,
        status="approved",
        est_meal_tl=int(raw.get("est_meal_tl") or 0),
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        final = slug
        n = 2
        while db.query(Place).filter(Place.slug == final).first() is not None:
            final = f"{slug}-{n}"[:80]
            n += 1
        db.add(Place(slug=final, **fields))
        db.flush()
        np = db.query(Place).filter(Place.slug == final).first()
        if np:
            merge_place_extra(np, {"source": "panorama", "rating_verified": False})
        return "new"
    if p.category == "food":
        if not (p.address or "").strip() and fields["address"]:
            p.address = fields["address"]
        merge_place_extra(p, {"source": "panorama"})
        return "skip"
    return "skip"


def main(*, refresh: bool = False) -> dict:
    init_db()
    rows = fetch_listings(refresh=refresh)
    db = SessionLocal()
    stats = {"new": 0, "skip": 0, "have": 0, "hotel": 0}
    try:
        names = {
            slugify(p.title)
            for p in db.query(Place).filter(Place.category == "food", Place.status == "approved")
        }
        for raw in rows:
            t = raw["title"]
            if any(k in t.lower() for k in SKIP_TITLE):
                stats["hotel"] += 1
                continue
            if already_have(t, names):
                stats["have"] += 1
                continue
            st = upsert(db, raw)
            stats[st] = stats.get(st, 0) + 1
            names.add(slugify(t))
        db.commit()
        n = db.query(Place).filter(Place.category == "food", Place.status == "approved").count()
        print("panorama listings", len(rows), "stats", stats, "food approved", n)
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="bursapanorama HTML'i yeniden çek")
    args = ap.parse_args()
    main(refresh=args.refresh)

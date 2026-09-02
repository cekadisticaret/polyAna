#!/usr/bin/env python3
"""Kamp yerlerini camps.json'dan zenginleştir + Wikimedia foto."""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db, merge_place_extra

UA = {"User-Agent": "BursaApp/1.0 (https://bursaapp.com; city guide)"}
CAMP_DIR = os.path.join(_DIR, "static", "camp")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def commons_search(q: str) -> str | None:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": q,
            "gsrnamespace": 6,
            "gsrlimit": 10,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": 1400,
            "format": "json",
        }
    )
    data = json.loads(_get(url))
    ban = ("bursaray", "siemens", "metro", ".pdf", ".svg", "logo", "map")
    best = None
    best_size = 0
    for p in (data.get("query") or {}).get("pages", {}).values():
        title = (p.get("title") or "").lower()
        if any(b in title for b in ban):
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        if not str(ii.get("mime") or "").startswith("image/"):
            continue
        sz = int(ii.get("size") or 0)
        u = ii.get("thumburl") or ii.get("url")
        if u and sz >= best_size:
            best, best_size = u, sz
    return best


def save_img(slug: str, url: str) -> str:
    dest = os.path.join(CAMP_DIR, f"{slug}.jpg")
    raw = _get(url)
    if len(raw) < 8000:
        return ""
    os.makedirs(CAMP_DIR, exist_ok=True)
    open(dest, "wb").write(raw)
    return f"/static/camp/{slug}.jpg"


def photo_for(raw: dict, force: bool = False) -> str:
    slug = raw["slug"]
    dest = os.path.join(CAMP_DIR, f"{slug}.jpg")
    if not force and os.path.isfile(dest) and os.path.getsize(dest) > 40000:
        return f"/static/camp/{slug}.jpg"
    url = None
    for q in (raw.get("search"), raw.get("title"), f"{raw.get('title')} Bursa"):
        if not q:
            continue
        time.sleep(0.4)
        try:
            url = commons_search(q)
        except Exception as e:
            print("search", slug, e)
            continue
        if url:
            break
    if url:
        try:
            path = save_img(slug, url)
            if path:
                print("dl", slug)
                return path
        except Exception as e:
            print("dl fail", slug, e)
    copy = raw.get("copy")
    if copy:
        src = os.path.join(_DIR, "static", "visit", f"{copy}.jpg")
        if os.path.isfile(src):
            os.makedirs(CAMP_DIR, exist_ok=True)
            shutil.copy(src, dest)
            print("copy", slug, "<-", copy)
            return f"/static/camp/{slug}.jpg"
    if os.path.isfile(dest) and os.path.getsize(dest) > 8000:
        return f"/static/camp/{slug}.jpg"
    print("NO PHOTO", slug)
    return ""


def upsert(db, raw: dict, img: str) -> None:
    body = (raw.get("body") or raw.get("blurb") or "")[:8000]
    fields = dict(
        title=raw["title"][:200],
        category="camp",
        subcategory=(raw.get("subcategory") or "")[:48],
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=(raw.get("blurb") or "")[:400],
        body=body,
        img_url=img or "",
        tags=tags_dump(raw.get("tags") or []),
        featured=bool(raw.get("featured")),
        status="approved",
        lat=raw.get("lat"),
        lng=raw.get("lng"),
        rating_admin=raw.get("rating_admin"),
    )
    p = db.query(Place).filter(Place.slug == raw["slug"]).first()
    if p is None:
        p = Place(slug=raw["slug"], **fields)
        db.add(p)
        db.flush()
    else:
        for k, v in fields.items():
            if k in ("lat", "lng") and v is None:
                continue
            if k == "rating_admin" and v is None:
                continue
            setattr(p, k, v)
    city = raw.get("city") or ""
    merge_place_extra(
        p,
        {
            "facilities": raw.get("facilities") or [],
            "tips": raw.get("tips") or "",
            "vibe": raw.get("vibe") or "",
            "source": "camp_research_2026",
            "city": city,
        },
    )


def main() -> None:
    force = "--force-photos" in sys.argv
    init_db()
    rows = json.loads(open(os.path.join(_DIR, "data", "camps.json"), encoding="utf-8").read())
    db = SessionLocal()
    try:
        keep = {r["slug"] for r in rows}
        for raw in rows:
            img = photo_for(raw, force=force or raw["slug"] in (
                "kapanca-korsan-limani",
                "eskel-kamp",
                "kocayayla-kamp",
                "ericek-goleti-kamp",
                "barakli-goleti-kamp",
                "softabogan-kamp",
                "dagyenice-kamp",
                "kayapa-kamp",
            ))
            upsert(db, raw, img)
        # eski seed dışı camp'ları silme — sadece uyarı
        orphans = [
            p.slug
            for p in db.query(Place).filter(Place.category == "camp", Place.status == "approved")
            if p.slug not in keep
        ]
        if orphans:
            print("orphan camps (kept):", orphans)
        db.commit()
        print("camp n", len(rows))
    finally:
        db.close()


if __name__ == "__main__":
    main()

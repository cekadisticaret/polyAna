#!/usr/bin/env python3
"""Oteller + kamp: Commons/Wikipedia foto, yoksa aynı yerin visit karesi."""
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
from models import Place, SessionLocal, init_db

UA = {"User-Agent": "BursaApp/1.0 (https://bursaapp.com; city guide)"}
IMG = {
    "hotel": os.path.join(_DIR, "static", "hotel"),
    "camp": os.path.join(_DIR, "static", "camp"),
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=28) as r:
        return r.read()


def wiki_thumb(title: str) -> str | None:
    q = urllib.parse.urlencode({
        "action": "query", "titles": title, "prop": "pageimages",
        "pithumbsize": 1100, "format": "json", "redirects": 1,
    })
    data = json.loads(_get("https://en.wikipedia.org/w/api.php?" + q))
    for p in data.get("query", {}).get("pages", {}).values():
        t = (p.get("thumbnail") or {}).get("source")
        if t:
            return t
    tr = urllib.parse.urlencode({
        "action": "query", "titles": title, "prop": "pageimages",
        "pithumbsize": 1100, "format": "json", "redirects": 1,
    })
    data = json.loads(_get("https://tr.wikipedia.org/w/api.php?" + tr))
    for p in data.get("query", {}).get("pages", {}).values():
        t = (p.get("thumbnail") or {}).get("source")
        if t:
            return t
    return None


def commons_search(q: str) -> str | None:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrsearch": q,
        "gsrnamespace": 6, "gsrlimit": 8, "prop": "imageinfo",
        "iiprop": "url|mime", "iiurlwidth": 1100, "format": "json",
    })
    data = json.loads(_get(url))
    ban = ("bursaray", "siemens", "metro station", ".pdf")
    for p in (data.get("query") or {}).get("pages", {}).values():
        title = (p.get("title") or "").lower()
        if any(b in title for b in ban):
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        if not str(ii.get("mime") or "").startswith("image/"):
            continue
        return ii.get("thumburl") or ii.get("url")
    return None


def save_img(kind: str, slug: str, url: str) -> str:
    dest = os.path.join(IMG[kind], f"{slug}.jpg")
    raw = _get(url)
    if len(raw) < 4000:
        return ""
    os.makedirs(IMG[kind], exist_ok=True)
    open(dest, "wb").write(raw)
    return f"/static/{kind}/{slug}.jpg"


def photo_for(kind: str, raw: dict) -> str:
    slug = raw["slug"]
    dest = os.path.join(IMG[kind], f"{slug}.jpg")
    if os.path.isfile(dest) and os.path.getsize(dest) > 8000:
        return f"/static/{kind}/{slug}.jpg"
    url = None
    if raw.get("wiki"):
        try:
            url = wiki_thumb(raw["wiki"])
        except Exception as e:
            print("wiki", slug, e)
    if not url and raw.get("search"):
        time.sleep(0.6)
        try:
            url = commons_search(raw["search"])
        except Exception as e:
            print("search", slug, e)
    if url:
        try:
            path = save_img(kind, slug, url)
            if path:
                print("dl", slug)
                return path
        except Exception as e:
            print("dl fail", slug, e)
    copy = raw.get("copy")
    if copy:
        src = os.path.join(_DIR, "static", "visit", f"{copy}.jpg")
        if os.path.isfile(src):
            os.makedirs(IMG[kind], exist_ok=True)
            shutil.copy(src, dest)
            print("copy", slug, "<-", copy)
            return f"/static/{kind}/{slug}.jpg"
    print("NO PHOTO", slug)
    return ""


def upsert(db, kind: str, raw: dict, img: str) -> None:
    fields = dict(
        title=raw["title"],
        category=kind,
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=raw.get("blurb") or "",
        img_url=img,
        tags=tags_dump(raw.get("tags") or []),
        featured=bool(raw.get("featured")),
        status="approved",
    )
    p = db.query(Place).filter(Place.slug == raw["slug"]).first()
    if p is None:
        db.add(Place(slug=raw["slug"], **fields))
    else:
        for k, v in fields.items():
            setattr(p, k, v)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        for kind, fname in (("hotel", "hotels.json"), ("camp", "camps.json")):
            rows = json.loads(open(os.path.join(_DIR, "data", fname), encoding="utf-8").read())
            for raw in rows:
                time.sleep(0.35)
                img = photo_for(kind, raw)
                upsert(db, kind, raw, img)
            print(kind, "n", len(rows))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Gezilecek yerler: Wikimedia gerçek foto + Bursaray listeden çıkar."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db

SRC = os.path.join(_DIR, "data", "places_visit.json")
IMG_DIR = os.path.join(_DIR, "static", "visit")
UA = {"User-Agent": "BursaApp/1.0 (https://bursaapp.com; city guide)"}
HIDE = ("bursaray",)
WIKI_FALLBACK = {
    "ulu-cami": "Grand Mosque of Bursa",
    "koza-han": "Koza Han",
    "yesil-turbe": "Green Tomb",
    "yesil-cami": "Green Mosque (Bursa)",
    "cumalikizik": "Cumalıkızık",
    "golyazi": "Gölyazı",
    "muradiye": "Muradiye Complex",
    "irgandi": "Irgandı Bridge",
    "emir-sultan": "Emir Sultan Mosque",
    "uludag": "Uludağ",
    "iznik-surlar": "İznik",
    "tirilye": "Tirilye",
}


def _get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def commons_file_url(filename: str) -> str | None:
    q = urllib.parse.urlencode({
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": 1100,
        "format": "json",
    })
    data = json.loads(_get("https://commons.wikimedia.org/w/api.php?" + q))
    pages = data.get("query", {}).get("pages", {})
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        return ii.get("thumburl") or ii.get("url")
    return None


def wiki_thumb(title: str) -> str | None:
    q = urllib.parse.urlencode({
        "action": "query",
        "titles": title,
        "prop": "pageimages",
        "pithumbsize": 1100,
        "format": "json",
        "redirects": 1,
    })
    data = json.loads(_get("https://en.wikipedia.org/w/api.php?" + q))
    for p in data.get("query", {}).get("pages", {}).values():
        t = (p.get("thumbnail") or {}).get("source")
        if t:
            return t
    return None


def commons_search(q: str) -> str | None:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": q,
        "gsrnamespace": 6,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "iiurlwidth": 1100,
        "format": "json",
    })
    data = json.loads(_get(url))
    ban = ("bursaray", "bursa ray", "metro", "siemens", "station sign")
    for p in (data.get("query") or {}).get("pages", {}).values():
        title = (p.get("title") or "").lower()
        if any(b in title for b in ban):
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        if not str(ii.get("mime") or "").startswith("image/"):
            continue
        return ii.get("thumburl") or ii.get("url")
    return None


def download(slug: str, filename: str | None) -> str:
    os.makedirs(IMG_DIR, exist_ok=True)
    dest = os.path.join(IMG_DIR, f"{slug}.jpg")
    if os.path.isfile(dest) and os.path.getsize(dest) > 8000:
        return f"/static/visit/{slug}.jpg"
    url = None
    if filename:
        try:
            url = commons_file_url(filename)
        except Exception as e:
            print("file fail", slug, e)
    if not url and slug in WIKI_FALLBACK:
        time.sleep(0.8)
        try:
            url = wiki_thumb(WIKI_FALLBACK[slug])
        except Exception as e:
            print("wiki fail", slug, e)
    if not url:
        time.sleep(0.8)
        try:
            url = commons_search(filename or slug.replace("-", " ") + " Bursa")
        except Exception as e:
            print("search fail", slug, e)
    if not url:
        print("NO PHOTO", slug)
        return ""
    try:
        raw = _get(url)
        if len(raw) < 4000:
            print("tiny", slug, len(raw))
            return ""
        open(dest, "wb").write(raw)
        print("ok", slug, len(raw))
        return f"/static/visit/{slug}.jpg"
    except Exception as e:
        print("dl fail", slug, e)
        return ""


def main() -> None:
    init_db()
    rows = json.loads(open(SRC, encoding="utf-8").read())
    db = SessionLocal()
    n_new = n_upd = 0
    try:
        for raw in rows:
            time.sleep(0.35)
            img = download(raw["slug"], raw.get("file"))
            fields = dict(
                title=raw["title"],
                category="visit",
                ilce=raw.get("ilce") or "",
                address=raw.get("address") or "",
                hours_text=raw.get("hours_text") or "",
                price_band=raw.get("price_band") or "",
                blurb=raw.get("blurb") or "",
                body=raw.get("blurb") or "",
                img_url=img or "",
                tags=tags_dump(raw.get("tags") or []),
                featured=bool(raw.get("featured")),
                status="approved",
                rating_admin=None,
            )
            p = db.query(Place).filter(Place.slug == raw["slug"]).first()
            if p is None:
                db.add(Place(slug=raw["slug"], **fields))
                n_new += 1
            else:
                for k, v in fields.items():
                    setattr(p, k, v)
                n_upd += 1
        for slug in HIDE:
            p = db.query(Place).filter(Place.slug == slug).first()
            if p:
                p.status = "rejected"
                p.reject_reason = "ulaşım, gezilecek yer değil"
                p.category = "visit"
        db.commit()
        print(f"visit new={n_new} upd={n_upd}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Düğün salonu JSON → Place (category=wedding).

  python3 seed_wedding.py
"""
from __future__ import annotations

import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db, merge_place_extra

DATA = os.path.join(_DIR, "data", "wedding_venues.json")
DEFAULT_COVER = "/static/visit/koza-han.jpg"


def _upsert(db, raw: dict) -> str:
    slug = raw["slug"]
    tags = ["dugun", "salon", raw.get("subcategory") or "kapali-salon", raw.get("price_band") or "orta"]
    rating = raw.get("rating")
    try:
        rating = float(rating) if rating not in (None, "") else None
    except (TypeError, ValueError):
        rating = None
    body = raw.get("body") or raw.get("blurb") or ""
    if raw.get("facilities"):
        body = (body + "\n\n" + " · ".join(raw["facilities"][:8])).strip()[:4000]
    fields = dict(
        title=raw["title"],
        category="wedding",
        subcategory=raw.get("subcategory") or "kapali-salon",
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        lat=raw.get("lat"),
        lng=raw.get("lng"),
        phone=raw.get("phone") or "",
        web=raw.get("web") or raw.get("source_url") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=body,
        img_url=raw.get("img_url") or DEFAULT_COVER,
        tags=tags_dump(tags),
        rating_admin=rating,
        featured=bool(raw.get("featured")),
        status="approved",
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        p = Place(slug=slug, **fields)
        db.add(p)
        db.flush()
        st = "new"
    else:
        st = "upd"
        for k, v in fields.items():
            if k == "rating_admin" and v is None:
                continue
            setattr(p, k, v)
    merge_place_extra(
        p,
        {
            "gallery": list(raw.get("gallery") or raw.get("image_urls") or [])[:8],
            "facilities": list(raw.get("facilities") or [])[:12],
            "fees": list(raw.get("fees") or [])[:6],
            "fee_note": raw.get("fee_note") or "",
            "price_min": raw.get("price_min") or "",
            "price_max": raw.get("price_max") or "",
            "source_url": raw.get("source_url") or raw.get("web") or "",
            "reservation_note": "Teklif ve tarih için salonu doğrudan arayın — BursaApp aracılık etmez.",
            "about": raw.get("about") or "",
        },
    )
    return st


def main() -> None:
    if not os.path.isfile(DATA):
        print(f"eksik: {DATA} — önce wedding_venues_fetch.py", file=sys.stderr)
        sys.exit(1)
    payload = json.load(open(DATA, encoding="utf-8"))
    rows = payload.get("venues") or payload
    if isinstance(rows, dict):
        rows = list(rows.values())
    init_db()
    db = SessionLocal()
    n = u = 0
    try:
        for raw in rows:
            if not raw.get("slug") or not raw.get("title"):
                continue
            st = _upsert(db, raw)
            if st == "new":
                n += 1
            else:
                u += 1
        db.commit()
        print(f"seed_wedding: new={n} upd={u} total={len(rows)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

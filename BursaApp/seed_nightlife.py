#!/usr/bin/env python3
"""Gece hayatı JSON + mevcut bar/meyhane kayıtlarını category=nightlife.

  python3 seed_nightlife.py
"""
from __future__ import annotations

import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db, merge_place_extra

DATA = os.path.join(_DIR, "data", "nightlife_venues.json")
DEFAULT_COVER = ""

MIGRATE_SUBCATS = frozenset({"bar", "meyhane"})
MIGRATE_FUN_SLUGS = frozenset({"bongo-bar", "nox-club", "opus-live", "meyhane-i-salas"})
FUN_SUBCAT = {
    "bongo-bar": "canli-muzik",
    "nox-club": "gece-kulubu",
    "opus-live": "canli-muzik",
    "meyhane-i-salas": "meyhane",
}
EXTRA_MIGRATE_SLUGS = frozenset(
    {
        "osm-restaurant-trilye-balik",
        "osm-restaurant-giritli-balik-restaurant",
        "osm-restaurant-kalami-balik-restaurant",
        "anadolu-evi-fasil-restaurant",
        "osm-restaurant-arap-sukru-sokagi",
        "osm-restaurant-arap-sukru-vira-2",
    }
)


def _food_is_nightlife(p: Place) -> bool:
    sub = (p.subcategory or "").strip()
    if sub in MIGRATE_SUBCATS:
        return True
    slug = p.slug or ""
    if slug in EXTRA_MIGRATE_SLUGS:
        return True
    if sub == "restoran" and any(
        x in slug for x in ("meyhane", "pub", "bar-", "-bar", "fasil", "arap-sukru")
    ):
        return True
    return False


def _guess_subcat(p: Place) -> str:
    sub = (p.subcategory or "").strip()
    if sub in MIGRATE_SUBCATS:
        return sub
    slug = (p.slug or "").lower()
    title = (p.title or "").lower()
    if "pub" in slug or "pub" in title:
        return "pub"
    if "meyhane" in slug or "meyhane" in title or "fasil" in slug:
        return "meyhane"
    if "gazino" in slug or "gazino" in title:
        return "gazino"
    if "kulüp" in title or "kulup" in slug or "club" in slug:
        return "gece-kulubu"
    if "canli" in slug or "sahne" in title or "live" in slug:
        return "canli-muzik"
    return "bar"


def migrate_existing(db) -> tuple[int, int]:
    moved = fixed = 0
    rows = (
        db.query(Place)
        .filter(Place.category.in_(("food", "fun")), Place.status == "approved")
        .all()
    )
    for p in rows:
        go = False
        if p.category == "fun" and (p.slug or "") in MIGRATE_FUN_SLUGS:
            go = True
            sub = FUN_SUBCAT.get(p.slug or "", _guess_subcat(p))
        elif p.category == "food" and _food_is_nightlife(p):
            go = True
            sub = _guess_subcat(p)
        if not go:
            continue
        p.category = "nightlife"
        if not (p.subcategory or "").strip() or p.subcategory not in MIGRATE_SUBCATS:
            p.subcategory = sub
        tags = json.loads(p.tags or "[]") if p.tags else []
        if "gece-hayati" not in tags:
            tags.append("gece-hayati")
        p.tags = tags_dump(tags)
        moved += 1
        if p.subcategory:
            fixed += 1
    return moved, fixed


def _upsert(db, raw: dict) -> str:
    slug = raw["slug"]
    tags = list(raw.get("tags") or [])
    for t in ("gece-hayati", raw.get("subcategory") or "bar"):
        if t and t not in tags:
            tags.append(t)
    rating = raw.get("rating")
    try:
        rating = float(rating) if rating not in (None, "") else None
    except (TypeError, ValueError):
        rating = None
    body = raw.get("body") or raw.get("blurb") or ""
    fields = dict(
        title=raw["title"],
        category="nightlife",
        subcategory=raw.get("subcategory") or "bar",
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        lat=raw.get("lat"),
        lng=raw.get("lng"),
        phone=raw.get("phone") or "",
        web=raw.get("web") or raw.get("source_url") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "orta",
        blurb=raw.get("blurb") or "",
        body=body[:4000],
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
            "source_url": raw.get("source_url") or raw.get("web") or "",
            "about": raw.get("about") or "",
            "reservation_note": raw.get("reservation_note")
            or "Masa ve giriş için mekanı doğrudan arayın — BursaApp rezervasyon almaz.",
        },
    )
    return st


def main() -> None:
    init_db()
    db = SessionLocal()
    n = u = 0
    try:
        moved, _ = migrate_existing(db)
        db.flush()
        if os.path.isfile(DATA):
            payload = json.load(open(DATA, encoding="utf-8"))
            rows = payload.get("venues") or payload
            if isinstance(rows, dict):
                rows = list(rows.values())
            for raw in rows:
                if not raw.get("slug") or not raw.get("title"):
                    continue
                st = _upsert(db, raw)
                if st == "new":
                    n += 1
                else:
                    u += 1
        db.commit()
        print(f"seed_nightlife: migrate={moved} new={n} upd={u}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Okullar + okul etkinlikleri seed.

  python3 BursaApp/seed_schools.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db, merge_place_extra


def _parse_iso(s: str | None):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", ""))


def upsert_school(db, raw: dict) -> str:
    raw = dict(raw)
    extra = raw.pop("extra", None)
    slug = raw["slug"]
    tags = list(raw.get("tags") or [])
    rating = None
    if raw.get("rating") not in (None, ""):
        try:
            rating = float(raw["rating"])
        except (TypeError, ValueError):
            rating = None
    fields = dict(
        title=raw["title"],
        category="school",
        subcategory=raw.get("subcategory") or "",
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=raw.get("body") or raw.get("blurb") or "",
        img_url=raw.get("img_url") or "",
        tags=tags_dump(tags),
        rating_admin=rating,
        featured=bool(raw.get("featured")),
        status="approved",
        lat=float(raw["lat"]) if raw.get("lat") not in (None, "") else None,
        lng=float(raw["lng"]) if raw.get("lng") not in (None, "") else None,
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        if fields["rating_admin"] is None:
            fields.pop("rating_admin", None)
        p = Place(slug=slug, **fields)
        db.add(p)
        db.flush()
        status = "new"
    else:
        for k, v in fields.items():
            if k == "rating_admin" and v is None:
                continue
            setattr(p, k, v)
        status = "upd"
    if extra:
        merge_place_extra(p, extra)
    return status


def upsert_event(db, raw: dict) -> str:
    slug = raw["slug"]
    school_slug = (raw.get("school_slug") or raw.get("venue_name") or "").strip()
    starts = _parse_iso(raw.get("starts"))
    ends = _parse_iso(raw.get("ends"))
    fields = dict(
        title=raw["title"],
        category="event",
        subcategory="okul-etkinlik",
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or (starts.strftime("%d.%m %H:%M") if starts else ""),
        price_band=raw.get("price_band") or "Okul",
        blurb=raw.get("blurb") or "",
        body=raw.get("blurb") or "",
        img_url=raw.get("img_url") or "",
        tags=tags_dump(raw.get("tags") or ["okul", "etkinlik"]),
        featured=bool(raw.get("featured")),
        status="approved",
        starts_at=starts,
        ends_at=ends,
        venue_name=school_slug,
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        db.add(Place(slug=slug, **fields))
        return "new"
    for k, v in fields.items():
        setattr(p, k, v)
    return "upd"


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        schools_path = os.path.join(_DIR, "data", "schools.json")
        if not os.path.isfile(schools_path):
            print("schools.json yok — önce: python3 BursaApp/schools_fetch.py --events")
            return
        sn = su = 0
        for raw in json.loads(open(schools_path, encoding="utf-8").read()):
            st = upsert_school(db, raw)
            sn += st == "new"
            su += st == "upd"
        en = eu = 0
        ev_path = os.path.join(_DIR, "data", "school_events.json")
        if os.path.isfile(ev_path):
            for raw in json.loads(open(ev_path, encoding="utf-8").read()):
                st = upsert_event(db, raw)
                en += st == "new"
                eu += st == "upd"
        db.commit()
        print(f"school new={sn} upd={su} · event new={en} upd={eu}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

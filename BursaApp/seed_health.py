#!/usr/bin/env python3
"""Hastane + doktor seed (venue_name = hastane slug).

  python3 BursaApp/seed_health.py
"""
from __future__ import annotations

import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db


def _upsert_hospital(db, raw: dict) -> str:
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
        category="hospital",
        subcategory="",
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=raw.get("blurb") or "",
        img_url=raw.get("img_url") or "",
        tags=tags_dump(tags),
        rating_admin=rating,
        featured=bool(raw.get("featured")),
        status="approved",
        venue_name=(raw.get("venue_name") or "").strip(),
        lat=float(raw["lat"]) if raw.get("lat") not in (None, "") else None,
        lng=float(raw["lng"]) if raw.get("lng") not in (None, "") else None,
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        if fields["rating_admin"] is None:
            fields.pop("rating_admin")
        db.add(Place(slug=slug, **fields))
        return "new"
    for k, v in fields.items():
        if k == "rating_admin" and v is None:
            continue
        setattr(p, k, v)
    return "upd"


def _upsert_doctor(db, raw: dict) -> str:
    slug = raw["slug"]
    hosp = (raw.get("hospital") or raw.get("venue_name") or "").strip()
    tags = list(raw.get("tags") or [])
    fields = dict(
        title=raw["title"],
        category="doctor",
        subcategory="",
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "https://www.mhrs.gov.tr/",
        hours_text=raw.get("hours_text") or "MHRS / 182",
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=raw.get("blurb") or "",
        img_url=raw.get("img_url") or "",
        tags=tags_dump(tags),
        rating_admin=float(raw.get("rating") or 0) or None,
        featured=False,
        status="approved",
        venue_name=hosp,
        lat=None,
        lng=None,
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
        hosp_path = os.path.join(_DIR, "data", "hospitals.json")
        doc_path = os.path.join(_DIR, "data", "doctors.json")
        hn = hu = dn = du = 0
        for raw in json.loads(open(hosp_path, encoding="utf-8").read()):
            r = _upsert_hospital(db, raw)
            hn += r == "new"
            hu += r == "upd"
        for raw in json.loads(open(doc_path, encoding="utf-8").read()):
            r = _upsert_doctor(db, raw)
            dn += r == "new"
            du += r == "upd"
        db.commit()
        print(f"hospital new={hn} upd={hu} doctor new={dn} upd={du}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

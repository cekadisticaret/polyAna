#!/usr/bin/env python3
"""Hastane + doktor + diş + veteriner seed.

  python3 BursaApp/seed_health.py
"""
from __future__ import annotations

import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from hospital_covers import resolve_img_url
from models import Place, SessionLocal, init_db


def _upsert_place(db, raw: dict, *, category: str) -> str:
    slug = raw["slug"]
    tags = list(raw.get("tags") or [])
    rating = None
    if raw.get("rating") not in (None, ""):
        try:
            rating = float(raw["rating"])
        except (TypeError, ValueError):
            rating = None
    p = db.query(Place).filter(Place.slug == slug).first()
    img_url = raw.get("img_url") or ""
    if category == "hospital":
        resolved = resolve_img_url(raw, p)
        if resolved is not None:
            img_url = resolved
        elif p is not None:
            img_url = p.img_url or ""
    fields = dict(
        title=raw["title"],
        category=category,
        subcategory=raw.get("subcategory") or "",
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=raw.get("blurb") or "",
        img_url=img_url,
        tags=tags_dump(tags),
        rating_admin=rating,
        featured=bool(raw.get("featured")),
        status="approved",
        venue_name=(raw.get("venue_name") or raw.get("hospital") or "").strip(),
        lat=float(raw["lat"]) if raw.get("lat") not in (None, "") else None,
        lng=float(raw["lng"]) if raw.get("lng") not in (None, "") else None,
    )
    if p is None:
        if fields["rating_admin"] is None:
            fields.pop("rating_admin")
        p = Place(slug=slug, **fields)
        db.add(p)
        db.flush()
        st = "new"
    else:
        st = "upd"
        for k, v in fields.items():
            if k == "rating_admin" and v is None:
                continue
            if k == "img_url" and category == "hospital" and resolve_img_url(raw, p) is None:
                continue
            setattr(p, k, v)
    if category == "dentist" and (raw.get("mhrs_url") or raw.get("price_band") == "Devlet"):
        from models import merge_place_extra

        patch = {
            "mhrs_url": (raw.get("mhrs_url") or "").strip() or "https://mhrs.gov.tr/vatandas/#/Randevu",
            "fee_note": "Devlet ADSM — randevu MHRS (182) veya mhrs.gov.tr. BursaApp randevu satmaz.",
        }
        merge_place_extra(p, patch)
    return st


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        counts = {}
        for fname, cat in (
            ("hospitals.json", "hospital"),
            ("doctors.json", "doctor"),
            ("dentists.json", "dentist"),
            ("vets.json", "vet"),
        ):
            path = os.path.join(_DIR, "data", fname)
            if not os.path.isfile(path):
                continue
            n = u = 0
            for raw in json.loads(open(path, encoding="utf-8").read()):
                r = _upsert_place(db, raw, category=cat)
                n += r == "new"
                u += r == "upd"
            counts[cat] = (n, u)
        db.commit()
        print(" ".join(f"{k} new={v[0]} upd={v[1]}" for k, v in counts.items()))
    finally:
        db.close()


if __name__ == "__main__":
    main()

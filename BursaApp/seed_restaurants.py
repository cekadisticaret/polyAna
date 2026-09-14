#!/usr/bin/env python3
"""Yeme-içme restoranlarını upsert eder. Alt tür + Google puan seed."""
from __future__ import annotations

import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import infer_food_subcategory, tags_dump
from models import Place, SessionLocal, init_db, merge_place_extra

SRC = os.path.join(_DIR, "data", "restaurants.json")
HIDE = ("iskender", "pideli-kofte", "kemalpasa", "kestane-sekeri")


def main() -> None:
    init_db()
    rows = json.loads(open(SRC, encoding="utf-8").read())
    db = SessionLocal()
    n_new = n_upd = 0
    try:
        for raw in rows:
            slug = raw["slug"]
            img = raw.get("photo") or ""
            img_url = f"/static/food/{img}" if img else ""
            tags = list(raw.get("tags") or []) + ["restoran"]
            sub = (raw.get("subcategory") or "").strip() or infer_food_subcategory(
                raw.get("price_band") or "", tags
            )
            p = db.query(Place).filter(Place.slug == slug).first()
            fields = dict(
                title=raw["title"],
                category="food",
                subcategory=sub,
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
                rating_admin=float(raw.get("rating") or 0) or None,
                featured=bool(raw.get("featured")),
                status="approved",
            )
            if raw.get("lat") is not None:
                fields["lat"] = float(raw["lat"])
            if raw.get("lng") is not None:
                fields["lng"] = float(raw["lng"])
            if p is None:
                db.add(Place(slug=slug, **fields))
                np = db.query(Place).filter(Place.slug == slug).first()
                if np and fields.get("rating_admin"):
                    merge_place_extra(
                        np,
                        {"rating_verified": True, "rating_source": "restaurants_json", "source": "restaurants_json"},
                    )
                n_new += 1
            else:
                for k, v in fields.items():
                    setattr(p, k, v)
                if fields.get("rating_admin"):
                    merge_place_extra(
                        p,
                        {"rating_verified": True, "rating_source": "restaurants_json", "source": "restaurants_json"},
                    )
                n_upd += 1
        for slug in HIDE:
            p = db.query(Place).filter(Place.slug == slug).first()
            if p and p.status == "approved":
                p.status = "rejected"
                p.reject_reason = "yemek kartı, restoran listesi değil"
        db.commit()
        print(f"restaurants new={n_new} upd={n_upd}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

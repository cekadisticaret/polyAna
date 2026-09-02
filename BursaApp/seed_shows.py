#!/usr/bin/env python3
"""Tarihli tiyatro / konser / film / etkinlik.

Kapak foto: önce mevcut gerçek dosya / events_fetch çıktısı korunur;
yoksa visit yedek kopyası (cron `events_fetch.py` gece günceller).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db


def parse_iso(s: str | None):
    if not s:
        return None
    return datetime.fromisoformat(s)


def photo(kind: str, raw: dict) -> str:
    slug = raw["slug"]
    dest_dir = os.path.join(_DIR, "static", kind)
    for ext in (".jpg", ".png", ".webp", ".avif"):
        dest = os.path.join(dest_dir, f"{slug}{ext}")
        if os.path.isfile(dest) and os.path.getsize(dest) > 4000:
            return f"/static/{kind}/{slug}{ext}"
    # seed yedek — gerçek poster için events_fetch.py
    copy = raw.get("copy") or "tophane"
    src = os.path.join(_DIR, "static", "visit", f"{copy}.jpg")
    if not os.path.isfile(src):
        src = os.path.join(_DIR, "static", "concert", "kulturpark-acikhava.jpg")
    if os.path.isfile(src):
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, f"{slug}.jpg")
        shutil.copy(src, dest)
        return f"/static/{kind}/{slug}.jpg"
    return ""


def upsert(db, kind: str, raw: dict, img: str) -> None:
    starts = parse_iso(raw.get("starts"))
    ends = parse_iso(raw.get("ends"))
    fields = dict(
        title=raw["title"],
        category=kind,
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or raw.get("venue_name") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or (starts.strftime("%d.%m %H:%M") if starts else ""),
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=raw.get("blurb") or "",
        img_url=img,
        tags=tags_dump(raw.get("tags") or [kind]),
        featured=bool(raw.get("featured")),
        status="approved",
        starts_at=starts,
        ends_at=ends,
        venue_name=raw.get("venue_name") or "",
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
        jobs = (
            ("theater", "shows_theater.json"),
            ("concert", "shows_concert.json"),
            ("cinema", "films.json"),
            ("event", "events.json"),
        )
        for kind, fname in jobs:
            rows = json.loads(open(os.path.join(_DIR, "data", fname), encoding="utf-8").read())
            for raw in rows:
                upsert(db, kind, raw, photo(kind, raw))
            print(kind, len(rows))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()

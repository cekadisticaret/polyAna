#!/usr/bin/env python3
"""shop / sport / family seed upsert + food subcategory backfill."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import infer_food_subcategory, tags_dump, tags_load
from models import Campaign, Place, SessionLocal, init_db, merge_place_extra

_TZ = ZoneInfo("Europe/Istanbul")


def _upsert(db, *, slug, category, raw, img_prefix=""):
    photo = raw.get("photo") or ""
    img_url = f"/static/{img_prefix}/{photo}" if photo and img_prefix else (raw.get("img_url") or "")
    tags = list(raw.get("tags") or [])
    sub = (raw.get("subcategory") or "").strip()
    fields = dict(
        title=raw["title"],
        category=category,
        subcategory=sub,
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or sub,
        blurb=raw.get("blurb") or "",
        body=raw.get("blurb") or "",
        img_url=img_url,
        tags=tags_dump(tags),
        rating_admin=float(raw.get("rating") or 0) or None,
        featured=bool(raw.get("featured")),
        status="approved",
        lat=float(raw["lat"]) if raw.get("lat") not in (None, "") else None,
        lng=float(raw["lng"]) if raw.get("lng") not in (None, "") else None,
    )
    if "starts_offset_days" in raw:
        now = datetime.now(_TZ).replace(tzinfo=None)
        day = datetime(now.year, now.month, now.day) + timedelta(days=int(raw.get("starts_offset_days") or 0))
        hour = int(raw.get("starts_hour") or 14)
        fields["starts_at"] = day.replace(hour=hour, minute=0)
        fields["ends_at"] = day.replace(hour=hour + 2, minute=0)
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        p = Place(slug=slug, **fields)
        db.add(p)
        db.flush()
        return "new", p
    for k, v in fields.items():
        setattr(p, k, v)
    return "upd", p


def seed_file(db, path: str, category: str) -> tuple[int, int]:
    rows = json.loads(open(path, encoding="utf-8").read())
    n_new = n_upd = 0
    for raw in rows:
        r, p = _upsert(db, slug=raw["slug"], category=category, raw=raw)
        extra = raw.get("extra")
        if extra and isinstance(extra, dict) and p is not None:
            merge_place_extra(p, extra)
        if r == "new":
            n_new += 1
        else:
            n_upd += 1
    return n_new, n_upd


def hide_old_market_branches(db) -> int:
    """Şube kayıtlarını gizle — /marketler zincir başına tek kart."""
    path = os.path.join(_DIR, "data", "markets.json")
    if not os.path.isfile(path):
        return 0
    keep = {raw["slug"] for raw in json.loads(open(path, encoding="utf-8").read())}
    n = 0
    for p in db.query(Place).filter(Place.category == "market").all():
        if p.slug in keep:
            continue
        if p.status == "approved":
            p.status = "rejected"
            n += 1
    return n


def seed_market_campaigns(db) -> int:
    """markets.json içindeki campaign alanlarını Campaign tablosuna yazar."""
    path = os.path.join(_DIR, "data", "markets.json")
    if not os.path.isfile(path):
        return 0
    rows = json.loads(open(path, encoding="utf-8").read())
    n = 0
    now = datetime.utcnow()
    for raw in rows:
        camp = raw.get("campaign")
        if not camp:
            continue
        p = db.query(Place).filter(Place.slug == raw["slug"], Place.category == "market").first()
        if not p:
            continue
        title = (camp.get("title") or "").strip()
        if not title:
            continue
        existing = (
            db.query(Campaign)
            .filter(Campaign.place_id == p.id, Campaign.title == title)
            .first()
        )
        if existing:
            existing.body = camp.get("body") or ""
            existing.badge = camp.get("badge") or ""
            existing.status = "approved"
            existing.ends_at = now + timedelta(days=90)
            continue
        db.add(
            Campaign(
                place_id=p.id,
                title=title,
                body=camp.get("body") or "",
                badge=camp.get("badge") or "",
                status="approved",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=60),
            )
        )
        n += 1
    return n


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        a = seed_file(db, os.path.join(_DIR, "data", "shops.json"), "shop")
        b = seed_file(db, os.path.join(_DIR, "data", "sports.json"), "sport")
        c = seed_file(db, os.path.join(_DIR, "data", "family.json"), "family")
        m = seed_file(db, os.path.join(_DIR, "data", "markets.json"), "market")
        hidden = hide_old_market_branches(db)
        db.flush()
        camp_n = seed_market_campaigns(db)
        food_n = backfill_food_sub(db)
        coord_n = backfill_coords_sample(db)
        today_n = ensure_today_shows(db)
        db.commit()
        print(
            f"shop {a} sport {b} family {c} market {m} hidden_branches={hidden} "
            f"market_camp={camp_n} food_sub={food_n} coords={coord_n} today_shows={today_n}"
        )
    finally:
        db.close()


def backfill_food_sub(db) -> int:
    n = 0
    for p in db.query(Place).filter(Place.category == "food").all():
        if (p.subcategory or "").strip():
            continue
        sub = infer_food_subcategory(p.price_band, tags_load(p.tags))
        p.subcategory = sub
        n += 1
    return n


def backfill_coords_sample(db) -> int:
    """Koordinatsız food kayıtlarına ilçe merkez yaklaşığı (yakınımda demosu)."""
    centers = {
        "Osmangazi": (40.1885, 29.0610),
        "Nilüfer": (40.2110, 28.9850),
        "Yıldırım": (40.1860, 29.1000),
        "Mudanya": (40.3750, 28.8820),
        "Gemlik": (40.4310, 29.1550),
        "İnegöl": (40.0781, 29.5133),
        "İznik": (40.4286, 29.7211),
    }
    n = 0
    for p in db.query(Place).filter(Place.status == "approved", Place.lat.is_(None)).limit(80).all():
        c = centers.get(p.ilce)
        if not c:
            continue
        # hafif jitter: id ile
        jitter = ((p.id % 17) - 8) * 0.0015
        p.lat = c[0] + jitter
        p.lng = c[1] - jitter * 0.7
        n += 1
    return n


def ensure_today_shows(db) -> int:
    """Bugün için tarihli kayıt yoksa sinema/konser/tiyatrodan örnekleri bugüne çeker."""
    from discover import today_bursa

    data = today_bursa(db)
    if data["total"] > 0:
        return 0
    now = datetime.now(_TZ).replace(tzinfo=None)
    day = datetime(now.year, now.month, now.day)
    n = 0
    hours = {"cinema": 19, "concert": 20, "theater": 20, "event": 18}
    for cat, hour in hours.items():
        rows = (
            db.query(Place)
            .filter(Place.status == "approved", Place.category == cat)
            .order_by(Place.id.desc())
            .limit(3)
            .all()
        )
        for i, p in enumerate(rows):
            p.starts_at = day.replace(hour=hour, minute=i * 15)
            p.ends_at = day.replace(hour=hour + 2, minute=0)
            n += 1
    return n


if __name__ == "__main__":
    main()

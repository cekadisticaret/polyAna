#!/usr/bin/env python3
"""Enuygun MCP otel listesini BursaApp Place kayıtlarına yazar + foto indirir.

Kaynak: uploads/_enuygun_hotels_all.json (MCP hotel_search).
Yalova şehir sonuçları elenir. Rezervasyon siteden yapılmaz.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db, merge_place_extra

SRC = os.path.join(_DIR, "uploads", "_enuygun_hotels_all.json")
OUT_JSON = os.path.join(_DIR, "data", "hotels_enuygun.json")
IMG_DIR = os.path.join(_DIR, "static", "hotel")
UA = {"User-Agent": "BursaApp/1.0 (https://bursaapp.com; city guide)"}

# Eski slug ↔ Enuygun adı eşlemesi (güncellemede çift kayıt olmasın)
_ALIAS = {
    "celik-palas": ("çelik palace", "çelik palas"),
    "almira-hotel": ("almira hotel",),
    "marigold-thermal": ("marigold thermal",),
    "movenpick-cekirge": ("mövenpick", "movenpick"),
    "ramada-cekirge": ("ramada by wyndham bursa çekirge", "ramada bursa çekirge"),
    "karinna-uludag": ("karinna",),
    "hilton-bursa": ("hilton bursa", "hampton by hilton bursa"),
    "sheraton-bursa": ("four points flex by sheraton", "sheraton"),
    "aloft-bursa": ("aloft",),
    "gonluferah": ("gönlüferah",),
    "kervansaray-thermal": ("kervansaray",),
    "grand-yazici-uludag": ("grand yazıcı", "grand yazici"),
    "beceren-uludag": ("beceren",),
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def _slugify(text: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = (text or "").translate(tr).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:72] or "otel"


def _slug_from_enuygun(raw_slug: str, name: str, hid: int) -> str:
    s = (raw_slug or "").strip()
    s = re.sub(r"-\d+$", "", s)
    if not s or len(s) < 4:
        s = _slugify(name)
    return f"{s}"[:80]


def _norm(s: str) -> str:
    tr = str.maketrans("çğıöşüâîû", "cgiosuaiu")
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower().translate(tr))


def _is_bursa(h: dict) -> bool:
    city = (h.get("city") or "").strip()
    if city and city.lower() not in ("bursa", "uludağ", "uludag"):
        return False
    blob = " ".join([h.get("name") or "", h.get("town") or "", city]).lower()
    if "yalova" in blob:
        return False
    return True


def _ilce(town: str) -> str:
    t = (town or "").strip()
    if not t:
        return ""
    if "Osmangazi" in t or "Merkez" in t:
        return "Osmangazi"
    if t == "Uludağ":
        return "Osmangazi"
    if t.startswith("Bursa "):
        return t.replace("Bursa ", "").strip()
    return t


def _band_and_sub(name: str, town: str, suits: list) -> tuple[str, str]:
    blob = " ".join([name or "", town or ""] + list(suits or [])).lower()
    if any(x in blob for x in ("termal", "thermal", "kaplıca", "kaplica", "spa")):
        return "termal", "termal"
    if any(x in blob for x in ("uludağ", "uludag", "orman köşk", "orman kosk", "kayak")):
        return "uludag", "dag-evi"
    if "bungalov" in blob or "bungalow" in blob:
        return "sehir", "bungalov"
    if "pansiyon" in blob:
        return "sehir", "pansiyon"
    if "butik" in blob or "villa" in blob or "suite" in blob or "suites" in blob:
        return "sehir", "butik"
    return "sehir", "otel"


def _score5(raw: str | None) -> float | None:
    if not raw:
        return None
    s = str(raw).replace(",", ".").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    if v <= 0.2:
        return None
    # Enuygun 0–10 → bizim 0–5
    return round(min(5.0, max(0.0, v / 2.0)), 2)


def _save_img(slug: str, url: str, idx: int = 0) -> str:
    if not url:
        return ""
    ext = ".jpg"
    name = f"{slug}.jpg" if idx == 0 else f"{slug}_{idx}.jpg"
    dest = os.path.join(IMG_DIR, name)
    if os.path.isfile(dest) and os.path.getsize(dest) > 8000:
        return f"/static/hotel/{name}"
    try:
        raw = _get(url)
    except Exception as e:
        print("img fail", slug, idx, e)
        return ""
    if len(raw) < 4000:
        return ""
    os.makedirs(IMG_DIR, exist_ok=True)
    open(dest, "wb").write(raw)
    return f"/static/hotel/{name}"


def _find_existing(db, slug: str, title: str) -> Place | None:
    p = db.query(Place).filter(Place.slug == slug).first()
    if p:
        return p
    nt = _norm(title)
    for old, keys in _ALIAS.items():
        if any(_norm(k) in nt or nt in _norm(k) for k in keys):
            p = db.query(Place).filter(Place.slug == old, Place.category == "hotel").first()
            if p:
                return p
    # başlık yakınlığı
    for p in db.query(Place).filter(Place.category == "hotel").all():
        if _norm(p.title) == nt:
            return p
        if nt and _norm(p.title) and (nt in _norm(p.title) or _norm(p.title) in nt):
            if abs(len(nt) - len(_norm(p.title))) < 12:
                return p
    return None


def _blurb(h: dict) -> str:
    parts = []
    town = _ilce(h.get("town") or "")
    if town:
        parts.append(town)
    suits = [s for s in (h.get("suitabilities") or []) if s][:3]
    if suits:
        parts.append(" · ".join(suits))
    price = h.get("formatted_price") or ""
    if price:
        parts.append(f"gecelik {price}")
    score = h.get("review_score")
    if score and str(score) not in ("0", "0,0", "0,1"):
        parts.append(f"misafir {score}/10")
    text = ". ".join(parts)
    return (text[:380] + ("…" if len(text) > 380 else "")) if text else "Bursa oteli."


def prepare_rows() -> list[dict]:
    rows = json.load(open(SRC, encoding="utf-8"))
    out = []
    seen = set()
    for h in rows:
        if not _is_bursa(h):
            continue
        hid = int(h["id"])
        if hid in seen:
            continue
        seen.add(hid)
        name = (h.get("name") or "").strip()
        if not name:
            continue
        slug = _slug_from_enuygun(h.get("slug") or "", name, hid)
        band, sub = _band_and_sub(name, h.get("town") or "", h.get("suitabilities") or [])
        coord = h.get("coordinate") or {}
        imgs = []
        if h.get("image_url"):
            imgs.append(h["image_url"])
        for im in h.get("images") or []:
            u = (im.get("url") or "").strip()
            if u and u not in imgs:
                imgs.append(u)
        out.append({
            "enuygun_id": hid,
            "slug": slug,
            "title": name,
            "ilce": _ilce(h.get("town") or ""),
            "lat": coord.get("latitude"),
            "lng": coord.get("longitude"),
            "price_band": band,
            "subcategory": sub,
            "review_score": h.get("review_score") or "",
            "rating_admin": _score5(h.get("review_score")),
            "min_price": h.get("min_price"),
            "formatted_price": h.get("formatted_price") or "",
            "price_fetched_at": h.get("price_fetched_at") or "",
            "price_check_in": h.get("price_check_in") or "",
            "price_check_out": h.get("price_check_out") or "",
            "price_room_from": h.get("price_room_from") or "",
            "image_urls": imgs[:8],
            "suitabilities": h.get("suitabilities") or [],
            "detail_link": (h.get("detail_link") or "").split("?")[0],
            "blurb": _blurb(h),
            "featured": False,
        })
    # puanı yüksek olanları featured
    ranked = sorted(
        [r for r in out if r.get("rating_admin")],
        key=lambda r: r["rating_admin"] or 0,
        reverse=True,
    )
    for r in ranked[:8]:
        r["featured"] = True
    out.sort(key=lambda r: (-(r.get("rating_admin") or 0), r["title"]))
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    open(OUT_JSON, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def upsert(db, raw: dict, img: str, gallery: list[str]) -> None:
    score = raw.get("review_score") or ""
    hours = ""
    if score and str(score) not in ("0", "0,0", "0,1"):
        hours = f"{score}/10"
    if raw.get("formatted_price"):
        hours = (hours + " · " if hours else "") + raw["formatted_price"]

    fields = dict(
        title=raw["title"],
        category="hotel",
        subcategory=raw.get("subcategory") or "otel",
        ilce=raw.get("ilce") or "",
        address=(raw.get("ilce") or "Bursa") + ", Bursa",
        lat=raw.get("lat"),
        lng=raw.get("lng"),
        phone="",
        web=raw.get("detail_link") or "",
        hours_text=hours[:160],
        price_band=raw.get("price_band") or "sehir",
        blurb=raw.get("blurb") or "",
        body=raw.get("blurb") or "",
        img_url=img or "",
        tags=tags_dump(
            [raw.get("price_band") or "otel"]
            + list(raw.get("suitabilities") or [])[:4]
        ),
        rating_admin=raw.get("rating_admin"),
        featured=bool(raw.get("featured")),
        status="approved",
    )
    p = _find_existing(db, raw["slug"], raw["title"])
    if p is None:
        # slug çakışırsa id ekle
        slug = raw["slug"]
        if db.query(Place).filter(Place.slug == slug).first():
            slug = f"{slug}-{raw['enuygun_id']}"
        p = Place(slug=slug, **fields)
        db.add(p)
        db.flush()
    else:
        for k, v in fields.items():
            setattr(p, k, v)

    extra = {
        "gallery": gallery if gallery else None,
        "facilities": list(raw.get("suitabilities") or [])[:8],
        "price_min": raw.get("formatted_price") or "",
        "source_url": raw.get("detail_link") or "",
        "reservation_note": (
            "Gecelik fiyat Enuygun’dan otomatik çekilir (1 gece · 2 kişi); rezervasyon BursaApp’ten yapılmaz."
        ),
        "enuygun_id": raw.get("enuygun_id"),
        "review_score": score,
    }
    if raw.get("price_fetched_at"):
        extra["price_fetched_at"] = raw["price_fetched_at"]
    if raw.get("price_check_in"):
        extra["price_check_in"] = raw["price_check_in"]
    if raw.get("price_check_out"):
        extra["price_check_out"] = raw["price_check_out"]
    if raw.get("price_room_from"):
        extra["price_room_from"] = raw["price_room_from"]
    merge_place_extra(p, {k: v for k, v in extra.items() if v not in (None, "", [])})


def upsert_prices_only(db, raw: dict) -> bool:
    """Yalnız fiyat alanlarını güncelle; foto dokunma."""
    p = _find_existing(db, raw["slug"], raw["title"])
    if p is None:
        return False
    score = raw.get("review_score") or ""
    if raw.get("formatted_price"):
        parts = []
        if score and str(score) not in ("0", "0,0", "0,1"):
            parts.append(f"{score}/10")
        parts.append(raw["formatted_price"])
        p.hours_text = " · ".join(parts)[:160]
        p.blurb = raw.get("blurb") or p.blurb
    merge_place_extra(
        p,
        {
            "price_min": raw.get("formatted_price") or "",
            "price_fetched_at": raw.get("price_fetched_at") or "",
            "price_check_in": raw.get("price_check_in") or "",
            "price_check_out": raw.get("price_check_out") or "",
            "price_room_from": raw.get("price_room_from") or "",
        },
    )
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices-only", action="store_true", help="Foto indirmeden yalnız fiyat güncelle")
    args = ap.parse_args()

    if not os.path.isfile(SRC):
        print("missing", SRC)
        sys.exit(1)
    rows = prepare_rows()
    print("prepared", len(rows), "->", OUT_JSON)
    init_db()
    db = SessionLocal()
    try:
        if args.prices_only:
            ok = 0
            for i, raw in enumerate(rows, 1):
                if upsert_prices_only(db, raw):
                    ok += 1
                if i % 20 == 0:
                    db.commit()
            db.commit()
            print("prices updated", ok, "/", len(rows))
        else:
            for i, raw in enumerate(rows, 1):
                gallery = []
                cover = ""
                for idx, url in enumerate(raw.get("image_urls") or []):
                    path = _save_img(raw["slug"], url, idx)
                    if path:
                        gallery.append(path)
                        if not cover:
                            cover = path
                    time.sleep(0.15)
                if not cover and raw.get("image_urls"):
                    cover = raw["image_urls"][0]
                    gallery = raw["image_urls"][:6]
                upsert(db, raw, cover, gallery)
                print(f"[{i}/{len(rows)}] {raw['title'][:48]} · {cover[:40] if cover else 'NOIMG'}")
                if i % 10 == 0:
                    db.commit()
            db.commit()
        n = db.query(Place).filter(Place.category == "hotel", Place.status == "approved").count()
        print("approved hotels", n)
    finally:
        db.close()


if __name__ == "__main__":
    main()

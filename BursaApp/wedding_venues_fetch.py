#!/usr/bin/env python3
"""Bursa düğün salonları — dugun.com listesi + JSON-LD + foto.

  python3 wedding_venues_fetch.py           # tam tur (slug keşfi + detay + foto)
  python3 wedding_venues_fetch.py --json    # yalnız JSON (foto indirme yok)
  python3 wedding_venues_fetch.py --seed    # JSON + DB seed

Kaynak: dugun.com/dugun-salonlari/bursa (kamuya açık liste + schema.org).
BursaApp rezervasyon / teklif satmaz — fiyat bilgilendirme amaçlıdır.
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

OUT_JSON = os.path.join(_DIR, "data", "wedding_venues.json")
LIST_BASE = "https://dugun.com/dugun-salonlari/bursa"
UA = "Mozilla/5.0 (compatible; BursaApp/1.0; +https://bursaapp.com)"
DEFAULT_COVER = "/static/visit/koza-han.jpg"

SKIP_NAME_RE = re.compile(r"\b(test|deneme|xxx)\b", re.I)


def _get(url: str, *, timeout: int = 35) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def discover_slugs(*, max_pages: int = 6) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    prev_n = -1
    for page in range(1, max_pages + 1):
        url = LIST_BASE if page == 1 else f"{LIST_BASE}?page={page}"
        try:
            html = _get(url)
        except Exception:
            break
        slugs = re.findall(r"dugun-salonlari/bursa/([a-z0-9-]+)", html)
        new = 0
        for s in slugs:
            if s not in seen:
                seen.add(s)
                ordered.append(s)
                new += 1
        if new == 0 or len(seen) == prev_n:
            break
        prev_n = len(seen)
        time.sleep(0.35)
    return ordered


def _fmt_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("90"):
        d = d[2:]
    if len(d) == 10:
        return f"0{d[:3]} {d[3:6]} {d[6:8]} {d[8:]}"
    return (raw or "").strip()


def _norm_ilce(loc: str, addr: str) -> str:
    from catalog import ILCELER

    blob = f"{loc} {addr}".lower()
    tr = str.maketrans("çğıöşü", "cgiosu")
    blob = blob.translate(tr)
    for ilce in ILCELER:
        if ilce.lower().translate(tr) in blob:
            return ilce
    if loc:
        return loc.strip().title()
    return ""


def _infer_sub(title: str, amenities: list[str]) -> str:
    t = (title or "").lower()
    am = " ".join(amenities).lower()
    if "belediye" in t:
        return "belediye"
    if any(x in t for x in ("hotel", "otel", "suite", "suites")):
        return "otel-salonu"
    if any(x in t for x in ("garden", "botanik", "bahce", "bahçe", "kır", "kir ", "açık", "acik", "teras", "göl")):
        return "acik-hava"
    if "davet" in t and "salon" not in t:
        return "davet"
    if any(x in am for x in ("açık hava", "acik hava", "bahçe", "bahce", "kır bahçe")):
        return "acik-hava"
    return "kapali-salon"


def _infer_band(low, high, price_range: str) -> str:
    try:
        lo = float(low) if low is not None else None
    except (TypeError, ValueError):
        lo = None
    if lo is not None:
        if lo < 45000:
            return "ekonomik"
        if lo < 75000:
            return "orta"
        return "premium"
    pr = (price_range or "").strip()
    if pr.count("₺") >= 3:
        return "premium"
    if pr.count("₺") == 1:
        return "ekonomik"
    return "orta"


def _hours_text(specs: list) -> str:
    if not specs:
        return "Randevu ile · detay için arayın"
    bits = []
    for s in specs[:2]:
        if not isinstance(s, dict):
            continue
        opens = s.get("opens") or ""
        closes = s.get("closes") or ""
        if opens and closes:
            bits.append(f"{opens}–{closes}")
    return " · ".join(bits) if bits else "Randevu ile · detay için arayın"


def _parse_ld(html: str) -> dict | None:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    graph = data.get("@graph") if isinstance(data, dict) else None
    if not graph:
        return data if isinstance(data, dict) and data.get("@type") == "LocalBusiness" else None
    for node in graph:
        if isinstance(node, dict) and node.get("@type") == "LocalBusiness":
            return node
    return None


def parse_venue(slug: str, html: str) -> dict | None:
    node = _parse_ld(html)
    if not node:
        return None
    title = (node.get("name") or "").strip()
    if not title or SKIP_NAME_RE.search(title):
        return None
    addr_obj = node.get("address") or {}
    street = (addr_obj.get("streetAddress") or "").strip()
    locality = (addr_obj.get("addressLocality") or "").strip()
    ilce = _norm_ilce(locality, street)
    geo = node.get("geo") or {}
    try:
        lat = float(geo.get("latitude")) if geo.get("latitude") not in (None, "") else None
        lng = float(geo.get("longitude")) if geo.get("longitude") not in (None, "") else None
    except (TypeError, ValueError):
        lat = lng = None
    amenities = [
        (a.get("name") or "").strip()
        for a in (node.get("amenityFeature") or [])
        if isinstance(a, dict) and (a.get("name") or "").strip()
    ]
    offer = node.get("makesOffer") or {}
    low = offer.get("lowPrice")
    high = offer.get("highPrice")
    rating_obj = node.get("aggregateRating") or {}
    rating = None
    try:
        rv = rating_obj.get("ratingValue")
        if rv not in (None, ""):
            rating = round(float(rv), 1)
    except (TypeError, ValueError):
        rating = None
    review_n = int(rating_obj.get("reviewCount") or rating_obj.get("ratingCount") or 0)
    images = []
    for u in node.get("image") or []:
        if isinstance(u, str) and u.startswith("http") and u not in images:
            images.append(u)
    phone = _fmt_phone(node.get("telephone") or "")
    web = (node.get("url") or f"https://dugun.com/dugun-salonlari/bursa/{slug}").strip()
    sub = _infer_sub(title, amenities)
    band = _infer_band(low, high, node.get("priceRange") or "")
    blurb_parts = []
    if ilce:
        blurb_parts.append(ilce)
    if amenities:
        blurb_parts.append(amenities[0][:80])
    if low and high:
        blurb_parts.append(f"paket {int(low):,}–{int(high):,} TL".replace(",", "."))
    elif low:
        blurb_parts.append(f"paket {int(low):,} TL'den".replace(",", "."))
    blurb = " · ".join(blurb_parts) or f"{title} — Bursa düğün salonu."
    fees = []
    if low or high:
        if low and high and low != high:
            price_txt = f"{int(low):,} – {int(high):,} TL".replace(",", ".")
        elif low:
            price_txt = f"{int(low):,} TL'den".replace(",", ".")
        else:
            price_txt = f"{int(high):,} TL'ye kadar".replace(",", ".")
        fees.append({
            "name": "Paket aralığı (Düğün.com)",
            "price": price_txt,
            "note": "Kişi sayısı ve menüye göre değişir",
        })
    return {
        "slug": f"dugun-{slug}"[:80],
        "dugun_slug": slug,
        "title": title,
        "ilce": ilce,
        "address": street or f"{locality}, Bursa".strip(", "),
        "lat": lat,
        "lng": lng,
        "phone": phone,
        "web": web,
        "hours_text": _hours_text(node.get("openingHoursSpecification") or [])[:160],
        "price_band": band,
        "subcategory": sub,
        "blurb": blurb[:380],
        "rating": rating,
        "review_count": review_n,
        "image_urls": images[:10],
        "facilities": amenities[:12],
        "fees": fees,
        "price_min": str(int(low)) if low not in (None, "") else "",
        "price_max": str(int(high)) if high not in (None, "") else "",
        "source_url": web,
        "fee_note": (
            "Fiyatlar Düğün.com listesinden bilgilendirme amaçlıdır; güncel teklif için salonu arayın. "
            "BursaApp rezervasyon veya ödeme almaz."
        ),
    }


def fetch_all(*, limit: int | None = None, sleep_s: float = 0.45) -> list[dict]:
    slugs = discover_slugs()
    if limit:
        slugs = slugs[:limit]
    out: list[dict] = []
    for i, slug in enumerate(slugs, 1):
        url = f"https://dugun.com/dugun-salonlari/bursa/{slug}"
        try:
            html = _get(url)
            row = parse_venue(slug, html)
            if row:
                out.append(row)
                print(f"[{i}/{len(slugs)}] ok {row['title'][:50]}", flush=True)
            else:
                print(f"[{i}/{len(slugs)}] skip {slug}", flush=True)
        except Exception as ex:
            print(f"[{i}/{len(slugs)}] err {slug}: {ex}", flush=True)
        time.sleep(sleep_s)
    out.sort(key=lambda r: (-(r.get("rating") or 0), r.get("title") or ""))
    for j, r in enumerate(out[:10]):
        r["featured"] = True
    return out


def cache_images(rows: list[dict]) -> None:
    from media_cache import ensure_cached

    for r in rows:
        slug = r["slug"]
        gallery: list[str] = []
        for i, url in enumerate(r.get("image_urls") or []):
            ext = ".jpg"
            if ".png" in url.lower():
                ext = ".png"
            elif ".jpeg" in url.lower():
                ext = ".jpeg"
            fn = f"{slug}-{i}{ext}"[:120]
            local = ensure_cached(url, category="wedding", filename=fn)
            if local:
                gallery.append(local)
        r["img_url"] = gallery[0] if gallery else DEFAULT_COVER
        r["gallery"] = gallery[:8]


def write_json(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    payload = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "dugun.com/dugun-salonlari/bursa",
        "total": len(rows),
        "venues": rows,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT_JSON} ({len(rows)} salon)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-only", action="store_true", help="foto indirme yok")
    ap.add_argument("--seed", action="store_true", help="JSON sonrası seed_wedding")
    ap.add_argument("--limit", type=int, default=0, help="test için üst sınır")
    args = ap.parse_args()
    lim = args.limit or None
    rows = fetch_all(limit=lim)
    if not args.json_only:
        cache_images(rows)
    write_json(rows)
    if args.seed:
        import seed_wedding

        seed_wedding.main()


if __name__ == "__main__":
    main()

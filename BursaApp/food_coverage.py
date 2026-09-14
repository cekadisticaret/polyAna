#!/usr/bin/env python3
"""Yeme-içme kapsam — ücretsiz kaynaklar (OSM, Panorama, Nominatim, Commons).

  python3 food_coverage.py stats
  python3 food_coverage.py cleanup [--apply]
  python3 food_coverage.py ratings-fix [--apply]
  python3 food_coverage.py osm-sync
  python3 food_coverage.py panorama
  python3 food_coverage.py geocode [--limit 60]
  python3 food_coverage.py enrich [--limit 40]
  python3 food_coverage.py run-all [--geocode-limit 60] [--enrich-limit 40]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

REMOVED_JSON = os.path.join(_DIR, "data", "places_removed.json")
UA = "BursaApp/1.0 (https://bursaapp.com; food coverage)"

# Semt-uydurma / test — gerçek işletme adı değil
SYNTHETIC_TITLE_RES = [
    re.compile(r"deneme lokant", re.I),
    re.compile(r"bildirim test", re.I),
    re.compile(r"sabah sofras", re.I),
    re.compile(r"kahvaltı bahçesi$", re.I),
    re.compile(r"sabah kahvaltı$", re.I),
    re.compile(r"serpme kahvaltı$", re.I),
    re.compile(r"kahvaltı salonu$", re.I),
    re.compile(r"^bursa kahvaltı ", re.I),
    re.compile(r"sabah cafe$", re.I),
    re.compile(r"sahil kahvaltı$", re.I),
    re.compile(r"göl kahvaltı$", re.I),
    re.compile(r"meydan kahvaltı$", re.I),
    re.compile(r"termal kahvaltı$", re.I),
    re.compile(r"park kahvaltı$", re.I),
    re.compile(r"^fsm cantık$", re.I),
    re.compile(r"^özlüce cantık$", re.I),
    re.compile(r"^beşevler cantık", re.I),
    re.compile(r"görükle cantık evi$", re.I),
    re.compile(r"cantık dünyası", re.I),
    re.compile(r"^nilüfer rakı sofras", re.I),
    re.compile(r"^özlüce rakı sofras", re.I),
    re.compile(r"^beşevler meyhane$", re.I),
    re.compile(r"^görükle meyhane$", re.I),
    re.compile(r"^odunluk meyhane$", re.I),
]

VERIFIED_RATING_SOURCES = frozenset(
    {"curated", "panorama", "restaurants_json", "burger_research", "manual"}
)


def _load_removed() -> tuple[set[str], set[str], dict]:
    try:
        with open(REMOVED_JSON, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        raw = {}
    titles = {str(x).strip() for x in raw.get("title_slugs") or [] if str(x).strip()}
    slugs = {str(x).strip() for x in raw.get("slugs") or [] if str(x).strip()}
    notes = raw.get("notes") if isinstance(raw.get("notes"), dict) else {}
    return titles, slugs, notes


def _save_removed(titles: set[str], slugs: set[str], notes: dict) -> None:
    os.makedirs(os.path.dirname(REMOVED_JSON), exist_ok=True)
    with open(REMOVED_JSON, "w", encoding="utf-8") as f:
        json.dump(
            {
                "title_slugs": sorted(titles),
                "slugs": sorted(slugs),
                "notes": notes,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def is_synthetic_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return any(rx.search(t) for rx in SYNTHETIC_TITLE_RES)


def stats() -> dict:
    from catalog import slugify
    from models import Place, SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        rows = db.query(Place).filter(Place.category == "food", Place.status == "approved").all()
        coord = sum(1 for p in rows if p.lat and p.lng)
        addr = sum(1 for p in rows if (p.address or "").strip())
        phone = sum(1 for p in rows if (p.phone or "").strip())
        syn = sum(1 for p in rows if is_synthetic_title(p.title or ""))
        from catalog import display_rating

        rated = sum(1 for p in rows if display_rating(p) is not None)
        return {
            "approved": len(rows),
            "coord": coord,
            "addr": addr,
            "phone": phone,
            "synthetic_left": syn,
            "rated_shown": rated,
        }
    finally:
        db.close()


def cleanup(*, apply: bool) -> dict:
    from catalog import slugify
    from models import Place, SessionLocal, init_db

    init_db()
    db = SessionLocal()
    out = {"reject": 0, "dry": 0, "titles": []}
    titles_rm, slugs_rm, notes = _load_removed()
    try:
        q = db.query(Place).filter(Place.category == "food", Place.status == "approved")
        for p in q.all():
            reason = None
            if is_synthetic_title(p.title or ""):
                reason = "sentetik semt adı"
            elif slugify(p.title or "") in titles_rm or (p.slug or "") in slugs_rm:
                reason = "places_removed"
            if not reason:
                continue
            out["titles"].append(p.title)
            if apply:
                p.status = "rejected"
                p.reject_reason = reason[:120]
                ts = slugify(p.title or "")
                if ts:
                    titles_rm.add(ts)
                if p.slug:
                    slugs_rm.add(p.slug)
                    notes[p.slug] = reason
                out["reject"] += 1
            else:
                out["dry"] += 1
        if apply:
            _save_removed(titles_rm, slugs_rm, notes)
            db.commit()
    finally:
        db.close()
    return out


def ratings_fix(*, apply: bool) -> dict:
    from catalog import slugify, tags_load
    from models import Place, SessionLocal, init_db, merge_place_extra, place_extra

    init_db()
    db = SessionLocal()
    out = {"verified": 0, "cleared": 0, "dry": 0}
    try:
        for p in db.query(Place).filter(Place.category == "food").all():
            ex = place_extra(p)
            tags = {t.lower() for t in tags_load(p.tags)}
            src = ex.get("rating_source") or ex.get("source") or ""
            slug = p.slug or ""

            should_verify = False
            if src in VERIFIED_RATING_SOURCES:
                should_verify = True
            elif p.featured and p.rating_admin:
                should_verify = True
            elif slug and not slug.startswith("osm-") and "osm" not in tags:
                if p.rating_admin and (ex.get("burger_research") or "burger" in slug):
                    should_verify = True
                elif p.rating_admin and len((p.blurb or "")) > 60:
                    should_verify = True

            if should_verify:
                if apply and ex.get("rating_verified") is not True:
                    merge_place_extra(p, {"rating_verified": True, "rating_source": src or "curated"})
                    out["verified"] += 1
                elif not apply:
                    out["dry"] += 1
                continue

            is_osm = slug.startswith("osm-") or "osm" in tags or ex.get("source") == "osm"
            if is_osm or (p.rating_admin and not should_verify):
                if apply:
                    if p.rating_admin is not None:
                        p.rating_admin = None
                        out["cleared"] += 1
                    merge_place_extra(p, {"rating_verified": False, "rating_source": "osm"})
                else:
                    out["dry"] += 1
        if apply:
            db.commit()
    finally:
        db.close()
    return out


def osm_sync() -> dict:
    from seed_food_expand import LOCAL_IMG, import_osm_delta
    from models import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        return import_osm_delta(db, max_age_h=None, imgs=LOCAL_IMG)
    finally:
        db.close()


def panorama_sync() -> dict:
    from seed_panorama_food import main as panorama_main

    return panorama_main(refresh=True) or {}


def nominatim_geocode(query: str) -> tuple[float, float] | None:
    q = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "tr"})
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{q}",
        headers={"User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def photon_geocode(query: str) -> tuple[float, float] | None:
    q = urllib.parse.urlencode(
        {
            "q": query,
            "limit": 1,
            "lat": "40.19",
            "lon": "29.06",
        }
    )
    req = urllib.request.Request(
        f"https://photon.komoot.io/api/?{q}",
        headers={"User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    feats = data.get("features") or []
    if not feats:
        return None
    coords = feats[0].get("geometry", {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    lng, lat = float(coords[0]), float(coords[1])
    if not (39.8 <= lat <= 40.7 and 28.3 <= lng <= 29.8):
        return None
    return lat, lng


def osm_geocode_name(title: str) -> tuple[float, float] | None:
    from seed_food_expand import BBOX, overpass

    safe = re.sub(r'["\\]', "", (title or "").strip())[:48]
    if len(safe) < 3:
        return None
    ql = (
        f'[out:json][timeout:45];('
        f'node["name"~"{safe}",i]({BBOX});'
        f'way["name"~"{safe}",i]({BBOX});'
        f');out center 3;'
    )
    try:
        els = overpass(ql)
    except Exception:
        return None
    for e in els:
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lng = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is not None and lng is not None:
            return float(lat), float(lng)
    return None


def geocode_missing(*, limit: int = 60, apply: bool = True) -> dict:
    from models import Place, SessionLocal, init_db, merge_place_extra

    init_db()
    db = SessionLocal()
    out = {"ok": 0, "fail": 0, "skip": 0}
    try:
        rows = (
            db.query(Place)
            .filter(
                Place.category == "food",
                Place.status == "approved",
                Place.lat.is_(None),
            )
            .all()
        )
        rows += (
            db.query(Place)
            .filter(
                Place.category == "food",
                Place.status == "approved",
                Place.lng.is_(None),
            )
            .all()
        )
        seen = set()
        todo = []
        for p in rows:
            if p.id in seen:
                continue
            seen.add(p.id)
            if (p.address or "").strip() or (p.title or "").strip():
                todo.append(p)
        for p in todo[: max(0, limit)]:
            hit = None
            src = None
            parts = [p.title or "", p.address or "", p.ilce or "", "Bursa", "Türkiye"]
            query = ", ".join(x for x in parts if x)
            try:
                hit = photon_geocode(query)
                if hit:
                    src = "photon"
            except Exception as exc:
                print("photon fail", p.title, exc, flush=True)
            if not hit:
                try:
                    hit = nominatim_geocode(query)
                    if hit:
                        src = "nominatim"
                except Exception as exc:
                    print("nominatim fail", p.title, exc, flush=True)
            if not hit:
                try:
                    hit = osm_geocode_name(p.title or "")
                    if hit:
                        src = "osm_name"
                except Exception as exc:
                    print("osm geocode fail", p.title, exc, flush=True)
            time.sleep(1.05)
            if not hit:
                out["fail"] += 1
                continue
            if apply:
                p.lat, p.lng = hit
                merge_place_extra(p, {"geocode_source": src or "nominatim"})
                out["ok"] += 1
            else:
                out["ok"] += 1
        if apply:
            db.commit()
    finally:
        db.close()
    return out


def enrich_photos(*, limit: int = 40) -> int:
    cmd = [sys.executable, os.path.join(_DIR, "enrich_food_venues.py"), "--limit", str(limit)]
    r = subprocess.run(cmd, cwd=_DIR, capture_output=True, text=True, timeout=3600)
    tail = ((r.stdout or "") + (r.stderr or ""))[-600:]
    print(tail, flush=True)
    return r.returncode


def run_all(*, geocode_limit: int, enrich_limit: int, apply: bool) -> None:
    print("=== stats (önce) ===", stats(), flush=True)
    c = cleanup(apply=apply)
    print("cleanup", c, flush=True)
    r = ratings_fix(apply=apply)
    print("ratings_fix", r, flush=True)
    print("osm-sync", osm_sync(), flush=True)
    print("panorama", panorama_sync(), flush=True)
    if apply:
        g = geocode_missing(limit=geocode_limit, apply=True)
        print("geocode", g, flush=True)
        if enrich_limit > 0:
            enrich_photos(limit=enrich_limit)
    print("=== stats (sonra) ===", stats(), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Bursa yeme-içme kapsam (ücretsiz)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats")
    p_cl = sub.add_parser("cleanup")
    p_cl.add_argument("--apply", action="store_true")
    p_rf = sub.add_parser("ratings-fix")
    p_rf.add_argument("--apply", action="store_true")
    sub.add_parser("osm-sync")
    sub.add_parser("panorama")
    p_geo = sub.add_parser("geocode")
    p_geo.add_argument("--limit", type=int, default=60)
    p_geo.add_argument("--dry-run", action="store_true")
    p_en = sub.add_parser("enrich")
    p_en.add_argument("--limit", type=int, default=40)
    p_all = sub.add_parser("run-all")
    p_all.add_argument("--geocode-limit", type=int, default=60)
    p_all.add_argument("--enrich-limit", type=int, default=40)
    p_all.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    if args.cmd == "stats":
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    elif args.cmd == "cleanup":
        print(cleanup(apply=args.apply))
    elif args.cmd == "ratings-fix":
        print(ratings_fix(apply=args.apply))
    elif args.cmd == "osm-sync":
        print(osm_sync())
    elif args.cmd == "panorama":
        print(panorama_sync())
    elif args.cmd == "geocode":
        print(geocode_missing(limit=args.limit, apply=not args.dry_run))
    elif args.cmd == "enrich":
        sys.exit(enrich_photos(limit=args.limit))
    elif args.cmd == "run-all":
        run_all(
            geocode_limit=args.geocode_limit,
            enrich_limit=args.enrich_limit,
            apply=not args.dry_run,
        )


if __name__ == "__main__":
    main()

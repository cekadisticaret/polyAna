#!/usr/bin/env python3
"""BursaApp gece turu — OSM + Panorama delta, onarım, SEO, görsel.

Cron (02:30 İST ≈ 23:30 UTC):
  30 23 * * * cd /root/aiProject && python3 BursaApp/bursaapp_nightly.py >> /tmp/bursaapp_nightly.log 2>&1

Emir / Poly open yok.
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import re
import subprocess
import sys
import traceback
from collections import defaultdict
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import ILCELER, slugify, tags_load
from models import Campaign, Place, SessionLocal, init_db
from seed_food_expand import LOCAL_IMG, import_osm_delta as food_osm_delta
from seed_panorama_food import SUB_IMG as FOOD_STOCK
from seed_panorama_food import guess_ilce as guess_ilce_addr
from seed_panorama_food import main as panorama_main
from seed_visit_expand import SUB_IMG as VISIT_STOCK
from seed_visit_expand import import_osm_delta as visit_osm_delta

LOCK_PATH = "/tmp/bursaapp_nightly.lock"
LAST_PATH = "/tmp/bursaapp_nightly_last.json"
CACHE_MAX_AGE_H = 16.0
REPAIR_LIMIT = 80


def log(msg: str) -> None:
    print(msg, flush=True)


def _lock():
    fp = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("zaten çalışıyor — çıkış")
        sys.exit(0)
    fp.write(str(os.getpid()))
    fp.flush()
    return fp


def _osm_hours_index() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in glob.glob("/tmp/osm_*.json"):
        try:
            els = json.load(open(path))
        except Exception:
            continue
        if not isinstance(els, list):
            continue
        for e in els:
            t = e.get("tags") or {}
            name = (t.get("name") or t.get("name:tr") or "").strip()
            hours = (t.get("opening_hours") or "").strip()
            if name and hours:
                out[slugify(name)] = hours[:160]
    return out


def _img_ok(img: str) -> bool:
    img = (img or "").strip()
    if not img:
        return False
    if img.startswith("/static/"):
        return os.path.isfile(os.path.join(_DIR, img.lstrip("/")))
    return True


def _stock_cover(p: Place) -> str:
    sub = p.subcategory or ""
    if p.category == "food":
        return FOOD_STOCK.get(sub) or LOCAL_IMG.get(sub) or FOOD_STOCK.get("restoran") or ""
    if p.category == "visit":
        return VISIT_STOCK.get(sub) or VISIT_STOCK.get("anit") or ""
    return ""


def _ilce_confident(addr: str) -> str | None:
    a = (addr or "").strip()
    if not a:
        return None
    if re.search(
        r"/\s*(Nilüfer|Osmangazi|Yıldırım|Mudanya|Gemlik|İnegöl|Kestel|Karacabey|Orhangazi|Gürsu|İznik)\b",
        a,
        re.I,
    ):
        g = guess_ilce_addr(a)
        return g if g in ILCELER else None
    if re.search(
        r"\b(Osmangazi|Yıldırım|Mudanya|Gemlik|İnegöl|Kestel|Karacabey|Nilüfer)\s*/\s*Bursa",
        a,
        re.I,
    ):
        g = guess_ilce_addr(a)
        return g if g in ILCELER else None
    blob = slugify(a)
    for ad in ILCELER:
        sl = slugify(ad)
        if sl not in blob and ad.lower() not in a.lower():
            continue
        if re.search(rf"{sl}\s+(cd|cad|caddesi|sk|sokak)", blob):
            continue
        return ad
    return None


def _is_import(p: Place) -> bool:
    sl = p.slug or ""
    if sl.startswith("osm-"):
        return True
    tags = {t.lower() for t in tags_load(p.tags)}
    return "osm" in tags or "panorama" in tags


def repair_places(db, *, limit: int = REPAIR_LIMIT) -> dict:
    stats = {"hours": 0, "ilce": 0, "img": 0, "blurb": 0, "dup": 0, "campaign": 0, "touched": 0}
    hours_idx = _osm_hours_index()
    rows = (
        db.query(Place)
        .filter(Place.category.in_(("food", "visit")), Place.status == "approved")
        .all()
    )

    def score(p: Place) -> int:
        s = 0
        if not (p.hours_text or "").strip() and slugify(p.title) in hours_idx:
            s += 4
        if not _img_ok(p.img_url or ""):
            s += 3
        g = _ilce_confident(p.address or "")
        if g and g != (p.ilce or "") and g in ILCELER:
            s += 2
        if not (p.blurb or "").strip() or len((p.blurb or "").strip()) < 20:
            s += 1
        return s

    ranked = sorted((p for p in rows if score(p) > 0), key=score, reverse=True)
    for p in ranked:
        if stats["touched"] >= limit:
            break
        did = False
        if not (p.hours_text or "").strip():
            h = hours_idx.get(slugify(p.title))
            if h:
                p.hours_text = h[:160]
                stats["hours"] += 1
                did = True
        if not _img_ok(p.img_url or ""):
            cover = _stock_cover(p)
            if cover:
                p.img_url = cover
                stats["img"] += 1
                did = True
        g = _ilce_confident(p.address or "")
        if g and g != (p.ilce or "") and g in ILCELER:
            p.ilce = g
            stats["ilce"] += 1
            did = True
        if not (p.blurb or "").strip() or len((p.blurb or "").strip()) < 20:
            kind = p.subcategory or ("restoran" if p.category == "food" else "gezilecek")
            p.blurb = f"Bursa {kind} · {p.ilce or ''}.".strip()[:400]
            stats["blurb"] += 1
            did = True
        if did:
            stats["touched"] += 1
    db.commit()

    by_key: dict[tuple[str, str], list[Place]] = defaultdict(list)
    for p in (
        db.query(Place)
        .filter(Place.category.in_(("food", "visit")), Place.status == "approved")
        .all()
    ):
        nm = slugify(p.title)
        if nm:
            by_key[(p.category or "", nm)].append(p)
    for _k, group in by_key.items():
        if len(group) < 2:
            continue
        keepers = [p for p in group if not _is_import(p)]
        extras = [p for p in group if _is_import(p)]
        if not keepers or not extras:
            continue
        for p in extras:
            p.status = "rejected"
            stats["dup"] += 1
    if stats["dup"]:
        db.commit()

    now = datetime.utcnow()
    for c in db.query(Campaign).filter(Campaign.status == "approved").all():
        if c.ends_at and c.ends_at < now:
            c.status = "expired"
            stats["campaign"] += 1
    if stats["campaign"]:
        db.commit()
    return stats


def step(name: str, fn):
    log(f"--- {name} ---")
    try:
        out = fn()
        log(f"{name}: {out}")
        return out, None
    except Exception as e:
        log(f"{name} FAIL: {e}")
        traceback.print_exc()
        return None, str(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-osm", action="store_true")
    ap.add_argument("--skip-panorama", action="store_true")
    ap.add_argument("--skip-repair", action="store_true")
    ap.add_argument("--skip-seo", action="store_true")
    ap.add_argument("--skip-images", action="store_true")
    ap.add_argument("--repair-limit", type=int, default=REPAIR_LIMIT)
    args = ap.parse_args()

    lock = _lock()
    started = datetime.utcnow()
    log(f"=== bursaapp_nightly {started.strftime('%Y-%m-%d %H:%M')} UTC ===")
    summary: dict = {"started_utc": started.isoformat(), "new": 0, "upd": 0, "reject": 0, "errors": []}

    init_db()

    if not args.skip_osm:
        def _food():
            db = SessionLocal()
            try:
                return food_osm_delta(db, max_age_h=CACHE_MAX_AGE_H)
            finally:
                db.close()

        def _visit():
            db = SessionLocal()
            try:
                return visit_osm_delta(db, max_age_h=CACHE_MAX_AGE_H)
            finally:
                db.close()

        s, err = step("1 osm yeme-içme", _food)
        if s:
            summary["osm_food"] = s
            summary["new"] += int(s.get("new") or 0)
            summary["upd"] += int(s.get("upd") or 0)
        if err:
            summary["errors"].append(f"osm_food: {err}")

        s, err = step("1 osm gezilecek", _visit)
        if s:
            summary["osm_visit"] = s
            summary["new"] += int(s.get("new") or 0)
            summary["upd"] += int(s.get("upd") or 0)
        if err:
            summary["errors"].append(f"osm_visit: {err}")
    else:
        log("OSM atlandı")

    if not args.skip_panorama:
        s, err = step("2 panorama delta", lambda: panorama_main(refresh=True) or {})
        if s:
            summary["panorama"] = s
            summary["new"] += int(s.get("new") or 0)
        if err:
            summary["errors"].append(f"panorama: {err}")
    else:
        log("Panorama atlandı")

    if not args.skip_repair:
        def _repair():
            db = SessionLocal()
            try:
                return repair_places(db, limit=max(0, args.repair_limit))
            finally:
                db.close()

        s, err = step("3 saat/kapak/ilçe onarım", _repair)
        if s:
            summary["repair"] = s
            summary["upd"] += int(s.get("touched") or 0)
            summary["reject"] += int(s.get("dup") or 0)
        if err:
            summary["errors"].append(f"repair: {err}")
    else:
        log("Onarım atlandı")

    if not args.skip_seo:
        import fix_seo_content
        import seo_nightly

        s, err = step("4 fix_seo_content", lambda: (fix_seo_content.main() or "ok"))
        if err:
            summary["errors"].append(f"fix_seo: {err}")
        summary["fix_seo"] = s if s else ("fail" if err else "ok")

        s, err = step("5 seo_nightly", lambda: (seo_nightly.main() or "ok"))
        if err:
            summary["errors"].append(f"seo: {err}")
        summary["seo"] = s if s else ("fail" if err else "ok")
    else:
        log("SEO atlandı")

    if not args.skip_images:
        def _imgs():
            cmd = [
                sys.executable,
                os.path.join(_DIR, "optimize_images.py"),
                "--dirs",
                "food",
                "visit",
            ]
            r = subprocess.run(cmd, cwd="/root/aiProject", capture_output=True, text=True, timeout=1800)
            tail = ((r.stdout or "") + (r.stderr or ""))[-800:]
            if r.returncode != 0:
                raise RuntimeError(f"exit {r.returncode}: {tail}")
            return tail.strip() or "ok"

        s, err = step("4 görsel optimize", _imgs)
        summary["images"] = s if s else (err or "")
        if err:
            summary["errors"].append(f"images: {err}")
    else:
        log("Görsel atlandı")

    summary["ended_utc"] = datetime.utcnow().isoformat()
    summary["elapsed_s"] = round((datetime.utcnow() - started).total_seconds(), 1)
    try:
        json.dump(summary, open(LAST_PATH, "w"), ensure_ascii=False, indent=2)
    except Exception:
        pass
    log(
        f"log: new={summary['new']} upd={summary['upd']} reject={summary['reject']} "
        f"err={len(summary['errors'])} {summary['elapsed_s']}s"
    )
    log("DONE")
    lock.close()
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())

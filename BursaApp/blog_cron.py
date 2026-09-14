#!/usr/bin/env python3
"""BursaApp blog otomasyonu — günlük + hafta sonu yazıları.

  python3 BursaApp/blog_cron.py
  python3 BursaApp/blog_cron.py --daily-only
  python3 BursaApp/blog_cron.py --weekend-only

Cron (İST 06:00 ≈ UTC 03:00 — her gün):
  0 3 * * * cd /root/aiProject && python3 BursaApp/blog_cron.py >> /tmp/blog_cron.log 2>&1

Perşembe ek tur (hafta sonu rotası, yedek):
  0 6 * * 4 cd /root/aiProject && python3 BursaApp/blog_cron.py --weekend-only >> /tmp/blog_cron.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from blog_generate import run_blog_cron
from models import SessionLocal, init_db


def main() -> None:
    ap = argparse.ArgumentParser(description="BursaApp blog cron")
    ap.add_argument("--daily-only", action="store_true")
    ap.add_argument("--weekend-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    weekend = not args.daily_only
    daily = not args.weekend_only

    if args.dry_run:
        from blog_generate import generate_daily_blog, ensure_weekend_blogs
        from datetime import datetime
        from zoneinfo import ZoneInfo

        init_db()
        db = SessionLocal()
        try:
            pub = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d")
            if weekend:
                for p in ensure_weekend_blogs(db):
                    print("weekend", p["slug"], p["h1"][:50])
            if daily:
                from blog_generate import (
                    build_events_post,
                    build_food_list_post,
                    build_ilce_post,
                    build_spotlight_post,
                    FOOD_THEMES,
                    ILCELER,
                )
                from catalog import ILCELER as IL

                day = datetime.now(ZoneInfo("Europe/Istanbul")).timetuple().tm_yday
                previews = [
                    ("spotlight", build_spotlight_post(db, pub)),
                    ("food", build_food_list_post(db, FOOD_THEMES[day % len(FOOD_THEMES)], pub)),
                    ("ilce", build_ilce_post(db, IL[day % len(IL)], pub)),
                    ("events", build_events_post(db, pub)),
                ]
                for name, p in previews:
                    if p:
                        print(name, p["slug"], p["h1"][:50])
                        break
        finally:
            db.close()
        return

    init_db()
    db = SessionLocal()
    try:
        result = run_blog_cron(db, weekend=weekend, daily=daily)
        if result.get("weekend"):
            for s in result["weekend"]:
                print(f"weekend /blog/{s}")
        if result.get("daily"):
            print(f"daily /blog/{result['daily']}")
        if not result.get("weekend") and not result.get("daily"):
            print("skip — bugün için yeni yazı yok")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()

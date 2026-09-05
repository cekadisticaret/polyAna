#!/usr/bin/env python3
"""Her Perşembe 1–2 alternatif hafta sonu rota blog yazısı üretir.

  python3 BursaApp/blog_weekend_cron.py
  python3 BursaApp/blog_weekend_cron.py --dry-run
  python3 BursaApp/blog_weekend_cron.py --count 1

Cron (İST Perşembe 09:00 ≈ UTC 06:00):
  0 6 * * 4 cd /root/aiProject && python3 BursaApp/blog_weekend_cron.py >> /tmp/blog_weekend_cron.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from models import SessionLocal, init_db
from weekend_blog import generate_weekend_blogs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Dosya yazmadan önizleme")
    ap.add_argument("--count", type=int, default=2, help="Üretilecek yazı (1–2)")
    args = ap.parse_args()
    count = max(1, min(2, int(args.count)))
    init_db()
    db = SessionLocal()
    try:
        if args.dry_run:
            from weekend_blog import build_weekend_post, pick_themes_for_week
            from discover import _next_weekend
            from datetime import datetime
            from zoneinfo import ZoneInfo

            sat, sun = _next_weekend()
            week_num = datetime.now(ZoneInfo("Europe/Istanbul")).isocalendar()[1]
            themes = pick_themes_for_week(week_num=week_num, count=count)
            pub = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d")
            for th in themes:
                post = build_weekend_post(db, th, sat=sat, sun=sun, pub_date=pub)
                print(json.dumps({"slug": post["slug"], "h1": post["h1"], "sections": len(post["sections"])}, ensure_ascii=False))
            return
        posts = generate_weekend_blogs(db, count=count)
        if not posts:
            print("skip — bu hafta sonu için yazı zaten var")
            return
        for p in posts:
            print(f"wrote /blog/{p['slug']} · {p['h1'][:60]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Cron: sanal üyeler feed/ziyaret/beğeni üretir."""
from __future__ import annotations

import json
import sys
import time

_DIR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
sys.path.insert(0, _DIR)

from models import SessionLocal, init_db
from virtual_users import run_activity, seed_virtual_users, stats


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        if stats(db).get("users", 0) < 10:
            seed_virtual_users(db, bootstrap_posts=1)
        out = run_activity(db, max_actions=3)
        out["stats"] = stats(db)
        print(json.dumps(out, ensure_ascii=False), flush=True)
    except Exception as exc:
        print(f"virtual_users_activity ERROR {time.strftime('%Y-%m-%d %H:%M:%S')} {exc}", flush=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Sanal topluluk üyeleri — oluştur / istatistik / tek seferlik aktivite."""
from __future__ import annotations

import argparse
import json
import sys

_DIR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
sys.path.insert(0, _DIR)

from models import SessionLocal, init_db
from virtual_users import run_activity, seed_virtual_users, stats


def main() -> None:
    ap = argparse.ArgumentParser(description="BursaApp sanal topluluk üyeleri")
    ap.add_argument(
        "cmd",
        choices=("seed", "stats", "tick"),
        help="seed=10 üye oluştur · stats=özet · tick=tek tur aktivite",
    )
    ap.add_argument("--posts", type=int, default=2, help="seed: kullanıcı başına ilk gönderi")
    ap.add_argument("--actions", type=int, default=3, help="tick: max aksiyon")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.cmd == "seed":
            out = seed_virtual_users(db, bootstrap_posts=max(0, args.posts))
            print(json.dumps(out, ensure_ascii=False))
        elif args.cmd == "stats":
            print(json.dumps(stats(db), ensure_ascii=False, indent=2))
        else:
            out = run_activity(db, max_actions=max(1, args.actions))
            print(json.dumps(out, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()

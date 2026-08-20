"""GPSUSDT sanal — CEM01 ile aynı cron ritmi, ayrı defter.

CEM01 (forex_paper.py) çalışmaya devam eder; bu betik ona dokunmaz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpsusdt_book import snapshot
from gpsusdt_data import gps_spot


def run() -> dict:
    q = gps_spot("1m")
    book = q.get("book") or snapshot(q.get("bid"), q.get("ask"))
    sig = q.get("signal") or {}
    pos = (book.get("positions") or [])
    print(
        f"gps binance dir={sig.get('direction')} bal={book.get('balance')} "
        f"eq={book.get('equity')} open={book.get('open_count')} "
        f"pos={[(p.get('side'), p.get('qty')) for p in pos]}"
    )
    return book


if __name__ == "__main__":
    out = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False))

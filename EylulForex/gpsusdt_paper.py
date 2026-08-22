"""GPSUSDT cron — CEM01 ile aynı ritim, ayrı defter.

Sinyal gelince Isolated MARKET $20×10x canlı Binance emri. gece penceresi yok.
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
    live = book.get("live") or {}
    print(
        f"gps binance live={live.get('enabled')} dir={sig.get('direction')} "
        f"bal={book.get('balance')} eq={book.get('equity')} "
        f"open={book.get('open_count')} "
        f"pos={[(p.get('side'), p.get('qty')) for p in pos]}"
    )
    return book


if __name__ == "__main__":
    out = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False))

"""GPSUSDT_2 cron — canlı GPSUSDT kopyası, sanal $160.

Kalman+VWAP aynı; Isolated MARKET $50×15x kâğıt VWAP.
gpsusdt_paper.py / canlı emir yoluna dokunmaz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gps2_book import snapshot
from gps2_data import gps_spot


def run() -> dict:
    q = gps_spot("1m")
    book = q.get("book") or snapshot(q.get("bid"), q.get("ask"))
    sig = q.get("signal") or {}
    pos = (book.get("positions") or [])
    print(
        f"gps2 paper dir={sig.get('direction')} "
        f"bal={book.get('balance')} eq={book.get('equity')} "
        f"open={book.get('open_count')} "
        f"pos={[(p.get('side'), p.get('qty')) for p in pos]}"
    )
    return book


if __name__ == "__main__":
    out = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False))

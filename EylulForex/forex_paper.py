"""Sanal XAUUSD — canlı sinyali deftere işler (cron + grafik spot)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forex_book import snapshot
from forex_data import forex_spot


def run() -> dict:
    q = forex_spot("1m")
    book = q.get("book") or snapshot(q.get("bid"), q.get("ask"))
    sig = q.get("signal") or {}
    print(
        f"g1 dir={sig.get('direction')} bal={book.get('balance')} "
        f"eq={book.get('equity')} open={book.get('open_count')} "
        f"pos={[p.get('side') for p in (book.get('positions') or [])]}"
    )
    a2 = forex_spot("1m", algo="a2")
    b2 = a2.get("book") or snapshot(a2.get("bid"), a2.get("ask"), book="a2")
    s2 = a2.get("signal") or {}
    print(
        f"a2 dir={s2.get('direction')} score={s2.get('score')} "
        f"allow={s2.get('allow_entry')} bal={b2.get('balance')} "
        f"open={b2.get('open_count')}"
    )
    bb = forex_spot("1m", algo="bybit")
    b3 = bb.get("book") or snapshot(bb.get("bid"), bb.get("ask"), book="bybit")
    s3 = bb.get("signal") or {}
    print(
        f"bybit dir={s3.get('direction')} bal={b3.get('balance')} "
        f"open={b3.get('open_count')} src={bb.get('src')} "
        f"pos={[p.get('side') for p in (b3.get('positions') or [])]}"
    )
    print("exness live=paused")
    return book


if __name__ == "__main__":
    out = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False))

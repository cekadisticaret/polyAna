"""B1#03 cron — CEM01 ritim, B1#03 MUM sinyal, ayrı defter.

forex_paper.py / CEM01 çalışmaya devam eder; bu betik ona dokunmaz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from b103_book import snapshot
from b103_data import forex_spot


def run() -> dict:
    q = forex_spot("1m")
    book = q.get("book") or snapshot(q.get("bid"), q.get("ask"))
    sig = q.get("signal") or {}
    print(
        f"b103 dir={sig.get('direction')} score={sig.get('score')} "
        f"bal={book.get('balance')} eq={book.get('equity')} "
        f"open={book.get('open_count')} "
        f"pos={[p.get('side') for p in (book.get('positions') or [])]}"
    )
    return book


if __name__ == "__main__":
    out = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False))

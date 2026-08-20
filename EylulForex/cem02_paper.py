"""CAPITAL cron — Capital.com demo oturumunu canlı tutar. CEM01'e dokunmaz."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capital_api import configured, ping, status
from cem02_book import snapshot
from cem02_data import forex_spot


def run() -> dict:
    if configured():
        st = status()
        print(
            f"capital ok={st.get('ok')} demo={st.get('demo')} "
            f"bal={st.get('balance')} eq={st.get('equity')} "
            f"open={st.get('open_count')} epic={st.get('epic')} "
            f"err={st.get('error')}"
        )
        ping()
        return st
    q = forex_spot("1m")
    book = q.get("book") or snapshot(q.get("bid"), q.get("ask"))
    sig = q.get("signal") or {}
    print(
        f"c2 dir={sig.get('direction')} bal={book.get('balance')} "
        f"eq={book.get('equity')} open={book.get('open_count')} "
        f"pos={[p.get('side') for p in (book.get('positions') or [])]}"
    )
    return book


if __name__ == "__main__":
    out = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False))

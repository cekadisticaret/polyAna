"""OPEN API cron — cTrader DEMO emir + oturum. CAPITAL / CEM01'e dokunmaz."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctrader_api import configured, orders_allowed, ping, status
from oapi_book import snapshot
from oapi_data import forex_spot


def run() -> dict:
    if configured() and orders_allowed():
        from oapi_trader import tick
        out = tick()
        print(
            f"ctrader g1-mirror ok={out.get('ok')} want={out.get('want')} "
            f"opened={bool(out.get('opened'))} "
            f"closed={len(out.get('closed') or [])} reject={out.get('reject')} "
            f"bal={out.get('balance')} err={out.get('error')}"
        )
        return out
    if configured():
        st = status()
        print(
            f"ctrader ok={st.get('ok')} demo={st.get('demo')} "
            f"trade=0 need_grant={st.get('need_trade_grant')} "
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
        f"oapi dir={sig.get('direction')} bal={book.get('balance')} "
        f"eq={book.get('equity')} open={book.get('open_count')} "
        f"pos={[p.get('side') for p in (book.get('positions') or [])]}"
    )
    return book


if __name__ == "__main__":
    out = run()
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False))

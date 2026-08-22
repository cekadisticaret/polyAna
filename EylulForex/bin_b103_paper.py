"""BIN_XAUUSDT cron — seçilen sanal defterin (D104) birebir aynası, Isolated $20×10x.

  python3 EylulForex/bin_b103_paper.py close|open|trail|scan|status

Yön / zaman sanal `fx_algo_*` defterinden kopyalanır. Kendi sinyalini koşturmaz.
GPSUSDT / fx_algo_runner / CEM01 dokunulmaz. Manuel open yok — cron D104'dan sonra.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bin_b103_book import snapshot, sync_from_engine
from bin_b103_data import live_quote


def _quote() -> dict:
    return live_quote()


def _ba(q: dict | None = None) -> tuple[float, float]:
    q = q or _quote()
    return float(q.get("bid") or 0), float(q.get("ask") or 0)


def _sync(tag: str) -> dict:
    bid, ask = _ba()
    if bid <= 0 or ask <= 0:
        print(f"[bin_b103 {tag}] fiyat yok")
        return {"ok": False, "error": "no_quote"}
    r = sync_from_engine(bid, ask)
    eng = (r.get("engine") or {}).get("uid") or "?"
    print(
        f"[bin_b103 {tag}] ayna {eng} action={r.get('action')} "
        f"side={r.get('side')} src={r.get('src_id')} "
        f"closed={r.get('closed')} opened={r.get('opened')} held={r.get('held')}"
    )
    return r


def run_close() -> dict:
    return _sync("close")


def run_trail() -> dict:
    return _sync("trail")


def run_open() -> dict:
    return _sync("open")


def run_scan() -> dict:
    return _sync("scan")


def run_status() -> dict:
    bid, ask = _ba()
    return snapshot(bid, ask)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["close", "open", "trail", "scan", "status"])
    args = p.parse_args()
    fn = {
        "close": run_close,
        "open": run_open,
        "trail": run_trail,
        "scan": run_scan,
        "status": run_status,
    }[args.cmd]
    out = fn()
    print(json.dumps({k: v for k, v in out.items() if k not in ("history", "positions", "pos")}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

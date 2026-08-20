"""Forex Algoritma işlemler runner — XAUUSD sanal, CEM01'e dokunmaz.

  python3 EylulForex/fx_algo_runner.py close|open|trail|scan|status
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_DIR, ".."))
sys.path.insert(0, _DIR)

from forex_data import forex_quote, get_xau_klines  # noqa: E402
from fx_algo_book import (  # noqa: E402
    close_expired,
    close_if_reverse,
    open_position,
    snapshot,
    snapshot_all,
    trail,
)
from fx_algo_catalog import ALL_BOOKS, SYMBOL  # noqa: E402
from fx_algo_signals import signal_for_book  # noqa: E402


def _quote() -> dict:
    return forex_quote()


def _mark(q: dict | None = None) -> float:
    q = q or _quote()
    mid = q.get("mid") or q.get("bid") or q.get("ask")
    return float(mid or 0)


def _kl(tf: str, n: int = 180) -> list:
    rows, _src = get_xau_klines(tf, n)
    return rows or []


def _pick_tf(sig1: str, sig4: str) -> tuple[str, str]:
    if sig1 in ("UP", "DOWN"):
        return "1h", sig1
    if sig4 in ("UP", "DOWN"):
        return "4h", sig4
    return "1h", "NEUTRAL"


def _side(sig: str) -> str | None:
    if sig == "UP":
        return "LONG"
    if sig == "DOWN":
        return "SHORT"
    return None


def run_close() -> dict:
    mark = _mark()
    kl = _kl("1h", 80)
    if mark <= 0:
        return {"ok": False, "error": "no_mark"}
    out = []
    for b in ALL_BOOKS:
        r = close_expired(b["uid"], mark, kl)
        if r.get("closed"):
            out.append({"uid": b["uid"], **r})
    print(f"[fx_algo close] kapanan defter={len(out)}")
    return {"ok": True, "books": out}


def run_trail() -> dict:
    q = _quote()
    mark = _mark(q)
    kl = _kl("1h", 80)
    if mark <= 0:
        return {"ok": False, "error": "no_mark"}
    n = 0
    bid, ask = q.get("bid"), q.get("ask")
    for b in ALL_BOOKS:
        r = trail(b["uid"], mark, kl, bid=bid, ask=ask)
        n += int(r.get("closed") or 0)
    print(f"[fx_algo trail] kapanan={n}")
    return {"ok": True, "closed": n}


def run_open() -> dict:
    mark = _mark()
    kl1 = _kl("1h", 180)
    kl4 = _kl("4h", 120)
    if mark <= 0 or len(kl1) < 30:
        print("[fx_algo open] mum/fiyat yok")
        return {"ok": False, "error": "no_data"}
    opened = []
    for b in ALL_BOOKS:
        s1 = signal_for_book(b, kl1)
        s4 = signal_for_book(b, kl4)
        tf, sig = _pick_tf(s1, s4)
        side = _side(sig)
        if not side:
            continue
        pos = open_position(b["uid"], side, mark, kl1 if tf == "1h" else kl4, signal=sig, tf=tf)
        if pos:
            opened.append({"uid": b["uid"], "side": side, "tf": tf})
            print(f"[fx_algo open] {b['uid']} {side} {tf} @{mark:.2f}")
    print(f"[fx_algo open] yeni={len(opened)}")
    return {"ok": True, "opened": opened}


def run_scan() -> dict:
    q = _quote()
    mark = _mark(q)
    kl1 = _kl("1h", 180)
    kl4 = _kl("4h", 120)
    if mark <= 0:
        return {"ok": False, "error": "no_mark"}
    closed = 0
    opened = []
    bid, ask = q.get("bid"), q.get("ask")
    for b in ALL_BOOKS:
        s1 = signal_for_book(b, kl1)
        s4 = signal_for_book(b, kl4)
        tf, sig = _pick_tf(s1, s4)
        side = _side(sig)
        if side:
            r = close_if_reverse(b["uid"], side, mark, kl1)
            closed += int(r.get("closed") or 0)
            pos = open_position(b["uid"], side, mark, kl1 if tf == "1h" else kl4, signal=sig, tf=tf)
            if pos:
                opened.append(b["uid"])
        trail(b["uid"], mark, kl1, bid=bid, ask=ask)
    print(f"[fx_algo scan] reverse={closed} open={len(opened)}")
    return {"ok": True, "closed": closed, "opened": opened}


def run_status() -> dict:
    return snapshot_all(_mark() or None)


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
    if args.cmd == "status":
        print(json.dumps({
            "ok": out.get("ok"),
            "count": out.get("count"),
            "total_balance": out.get("total_balance"),
            "total_open": out.get("total_open"),
        }, ensure_ascii=False))
    else:
        print(json.dumps({k: v for k, v in out.items() if k != "books"}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

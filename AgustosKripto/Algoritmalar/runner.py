#!/usr/bin/env python3
"""Algoritmalar — 17× ALGO2 sanal futures saatlik open/close.

  python3 AgustosKripto/Algoritmalar/runner.py close
  python3 AgustosKripto/Algoritmalar/runner.py open
  python3 AgustosKripto/Algoritmalar/runner.py trail
  python3 AgustosKripto/Algoritmalar/runner.py status
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGUSTOS = os.path.dirname(_DIR)
_ROOT = os.path.dirname(_AGUSTOS)
sys.path.insert(0, _AGUSTOS)
sys.path.insert(0, _DIR)

from virtual_book import (  # noqa: E402
    MAX_OPENS_PER_HOUR,
    SYMBOLS,
    book_status,
    cached_status,
    close_all_positions,
    fetch_all_klines,
    load_state,
    open_signals,
    refresh_status,
    trail_positions,
)
from catalog import ALGOS, pick_candidates, signal_for_algo  # noqa: E402

DATA = os.path.join(_DIR, "data")


def _paths(algo_id: int) -> tuple[str, str]:
    tag = f"algo_{algo_id:02d}"
    return (
        os.path.join(DATA, f"{tag}_state.json"),
        os.path.join(DATA, f"{tag}_history.json"),
    )


def label(algo_id: int, name: str = "") -> str:
    meta = next((a for a in ALGOS if a["id"] == algo_id), None)
    nm = name or (meta["name"] if meta else f"Algo{algo_id}")
    return f"ALG{algo_id:02d} {nm}"


def run_close() -> dict:
    kl = fetch_all_klines(SYMBOLS, limit=5)
    results = []
    for a in ALGOS:
        sp, hp = _paths(a["id"])
        r = close_all_positions(sp, hp, label=label(a["id"], a["name"]), kl_cache=kl)
        results.append({"id": a["id"], "name": a["name"], **r})
    return {"ok": True, "results": results}


def run_open() -> dict:
    kl = fetch_all_klines(SYMBOLS, limit=80)
    results = []
    for a in ALGOS:
        sp, hp = _paths(a["id"])
        sigs = signal_for_algo(a["id"], kl)
        cands = pick_candidates(sigs, max_n=MAX_OPENS_PER_HOUR)
        for c in cands:
            c["algo"] = a["name"]
        r = open_signals(
            sp, hp,
            label=label(a["id"], a["name"]),
            candidates=cands,
            kl_cache=kl,
        )
        results.append({"id": a["id"], "name": a["name"], **r})
    return {"ok": True, "results": results}


def run_trail() -> dict:
    open_syms: set[str] = set()
    for a in ALGOS:
        sp, _hp = _paths(a["id"])
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    kl = fetch_all_klines(sorted(open_syms) or SYMBOLS[:1], limit=80) if open_syms else {}
    results = []
    for a in ALGOS:
        sp, hp = _paths(a["id"])
        r = trail_positions(sp, hp, label=label(a["id"], a["name"]), kl_cache=kl)
        results.append({"id": a["id"], "name": a["name"], **r})
    return {"ok": True, "results": results}


def _build_status(*, with_marks: bool = True) -> dict:
    open_syms: set[str] = set()
    for a in ALGOS:
        sp, _hp = _paths(a["id"])
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    kl = fetch_all_klines(sorted(open_syms), limit=2) if with_marks and open_syms else {}
    books = []
    tot_bal = 0.0
    tot_pnl = 0.0
    tot_open = 0
    for a in ALGOS:
        sp, hp = _paths(a["id"])
        st = book_status(
            sp, hp,
            label=label(a["id"], a["name"]),
            kl_cache=kl,
            live_marks=with_marks,
        )
        st["id"] = a["id"]
        st["name"] = a["name"]
        st["category"] = a["category"]
        books.append(st)
        tot_bal += float(st.get("balance") or 0)
        tot_pnl += float(st.get("total_pnl") or 0)
        tot_open += int(st.get("open_count") or 0)
    return {
        "ok": True,
        "kind": "algoritmalar",
        "count": len(books),
        "margin_usd": 15,
        "leverage": 15,
        "deposit_each": 300,
        "max_opens": MAX_OPENS_PER_HOUR,
        "total_balance": round(tot_bal, 2),
        "total_pnl": round(tot_pnl, 4),
        "total_open": tot_open,
        "books": books,
    }


def status_block(*, with_marks: bool = True) -> dict:
    return cached_status("algoritmalar", lambda: _build_status(with_marks=with_marks))


def refresh_status_block(*, with_marks: bool = True) -> dict:
    return refresh_status("algoritmalar", lambda: _build_status(with_marks=with_marks))



def main() -> None:
    p = argparse.ArgumentParser(description="AgustosKripto Algoritmalar sanal runner")
    p.add_argument("cmd", choices=["open", "close", "trail", "status"])
    args = p.parse_args()
    if args.cmd == "open":
        r = run_open()
    elif args.cmd == "close":
        r = run_close()
    elif args.cmd == "trail":
        r = run_trail()
    else:
        r = status_block()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

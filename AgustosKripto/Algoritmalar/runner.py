#!/usr/bin/env python3
"""Algoritmalar — ALGO2 Top-17 + ALGO1 (Poly) sanal futures.

  python3 AgustosKripto/Algoritmalar/runner.py close
  python3 AgustosKripto/Algoritmalar/runner.py open
  python3 AgustosKripto/Algoritmalar/runner.py trail
  python3 AgustosKripto/Algoritmalar/runner.py status
  python3 AgustosKripto/Algoritmalar/runner.py reset
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
    DEPOSIT,
    MAX_OPENS_PER_HOUR,
    SYMBOLS,
    book_status,
    cached_status,
    close_all_positions,
    fetch_all_klines,
    in_weekend_pause_tr,
    load_state,
    open_signals,
    refresh_status,
    reset_book,
    trail_positions,
    write_snapshot,
)
from catalog import ALL_BOOKS, pick_candidates, signal_for_book  # noqa: E402

DATA = os.path.join(_DIR, "data")


def _paths(book: dict) -> tuple[str, str]:
    tag = book["book_key"]
    return (
        os.path.join(DATA, f"{tag}_state.json"),
        os.path.join(DATA, f"{tag}_history.json"),
    )


def label(book: dict) -> str:
    panel = "A2" if book.get("panel") == "v2" else "A1"
    return f"{panel}#{int(book['id']):02d} {book.get('title') or book.get('name')}"


def _skip_weekend(cmd: str) -> dict | None:
    if not in_weekend_pause_tr():
        return None
    print(f"[Algoritmalar] hafta sonu — {cmd} skip (Cum 22:00 – Pzt 08:00 İST)")
    return {"ok": True, "skipped": "weekend_pause", "cmd": cmd, "results": []}


def run_close() -> dict:
    skipped = _skip_weekend("close")
    if skipped:
        return skipped
    kl = fetch_all_klines(SYMBOLS, limit=5)
    results = []
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        r = close_all_positions(sp, hp, label=label(book), kl_cache=kl)
        results.append({"id": book["uid"], "name": book["name"], "panel": book["panel"], **r})
    return {"ok": True, "results": results}


def run_open() -> dict:
    skipped = _skip_weekend("open")
    if skipped:
        return skipped
    kl = fetch_all_klines(SYMBOLS, limit=80)
    results = []
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        sigs = signal_for_book(book, kl)
        cands = pick_candidates(sigs, max_n=MAX_OPENS_PER_HOUR)
        for c in cands:
            c["algo"] = book["name"]
        r = open_signals(
            sp, hp,
            label=label(book),
            candidates=cands,
            kl_cache=kl,
        )
        results.append({"id": book["uid"], "name": book["name"], "panel": book["panel"], **r})
    return {"ok": True, "results": results}


def run_trail() -> dict:
    skipped = _skip_weekend("trail")
    if skipped:
        return skipped
    open_syms: set[str] = set()
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    kl = fetch_all_klines(sorted(open_syms) or SYMBOLS[:1], limit=80) if open_syms else {}
    results = []
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        r = trail_positions(sp, hp, label=label(book), kl_cache=kl)
        results.append({"id": book["uid"], "name": book["name"], "panel": book["panel"], **r})
    return {"ok": True, "results": results}


def _build_status(*, with_marks: bool = True) -> dict:
    open_syms: set[str] = set()
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    kl = fetch_all_klines(sorted(open_syms), limit=2) if with_marks and open_syms else {}
    books = []
    tot_bal = 0.0
    tot_pnl = 0.0
    tot_open = 0
    n_v1 = 0
    n_v2 = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        st = book_status(
            sp, hp,
            label=label(book),
            kl_cache=kl,
            live_marks=with_marks,
        )
        st["id"] = book["uid"]
        st["name"] = book["name"]
        st["title"] = book.get("title") or book["name"]
        st["category"] = book.get("category") or ""
        st["panel"] = book["panel"]
        st["algo_num"] = book["id"]
        books.append(st)
        tot_bal += float(st.get("balance") or 0)
        tot_pnl += float(st.get("total_pnl") or 0)
        tot_open += int(st.get("open_count") or 0)
        if book["panel"] == "v1":
            n_v1 += 1
        else:
            n_v2 += 1
    return {
        "ok": True,
        "kind": "algoritmalar",
        "count": len(books),
        "count_v1": n_v1,
        "count_v2": n_v2,
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


def run_reset(*, balance: float = DEPOSIT) -> dict:
    """Tüm ALGO1+ALGO2 defterlerini kapat + bakiyeyi $300'e çek."""
    results = []
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        st = reset_book(sp, balance=balance)
        results.append({
            "id": book["uid"],
            "name": book["name"],
            "panel": book["panel"],
            "balance": st.get("balance"),
            "open_count": 0,
        })
    out = {
        "ok": True,
        "kind": "algoritmalar",
        "reset_balance": float(balance),
        "count": len(results),
        "results": results,
    }
    try:
        write_snapshot("algoritmalar", refresh_status_block(with_marks=False))
    except Exception:
        pass
    print(f"[Algoritmalar] reset → ${balance:.0f} × {len(results)} defter (A2+A1)")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="AgustosKripto Algoritmalar sanal runner")
    p.add_argument("cmd", choices=["open", "close", "trail", "status", "reset"])
    args = p.parse_args()
    if args.cmd == "open":
        r = run_open()
    elif args.cmd == "close":
        r = run_close()
    elif args.cmd == "trail":
        r = run_trail()
    elif args.cmd == "reset":
        r = run_reset()
    else:
        r = status_block()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

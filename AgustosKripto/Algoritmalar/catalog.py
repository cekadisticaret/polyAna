#!/usr/bin/env python3
"""ALGO2 Top-17 klon kataloğu.

Sinyal fonksiyonları temmuzPoly/algo_signals_v2 üzerinden import edilir —
Poly kaynak dosyalarına dokunulmaz.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
if _POLY not in sys.path:
    sys.path.insert(0, _POLY)

from algo_signals_v2 import ALGO_V2_META  # noqa: E402
import algo_signals as sig  # noqa: E402

# Yerel görünen liste (id, name, category)
ALGOS = [
    {"id": n, "name": name, "category": cat, "kind": kind}
    for n, name, cat, kind, _fn in ALGO_V2_META
]


def algo_fn(algo_id: int):
    for n, name, cat, kind, fn in ALGO_V2_META:
        if n == algo_id:
            return name, kind, fn
    return None, None, None


def signal_for_algo(algo_id: int, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    """symbol → UP|DOWN|NEUTRAL."""
    name, kind, fn = algo_fn(algo_id)
    out = {sym: "NEUTRAL" for sym in kl_by_symbol}
    if kind == "pairs":
        # pairs_trading BTC/ETH/SOL kısa anahtar ister
        short_map = {}
        for short, pair in sig.SYMBOLS.items():
            short_map[short] = kl_by_symbol.get(pair) or []
        try:
            pairs = sig.pairs_trading(short_map)
            for short, pair in sig.SYMBOLS.items():
                out[pair] = pairs.get(short, "NEUTRAL")
        except Exception as e:
            print(f"[Algoritmalar#{algo_id}] pairs: {e}")
        return out
    if kind == "fn" and fn:
        for sym, kl in kl_by_symbol.items():
            if not kl:
                continue
            try:
                out[sym] = fn(kl) or "NEUTRAL"
            except Exception as e:
                print(f"[Algoritmalar#{algo_id}] {sym}: {e}")
                out[sym] = "NEUTRAL"
    return out


def pick_candidates(signals: dict[str, str], *, max_n: int = 6) -> list[dict]:
    """UP/DOWN sinyallerinden en fazla max_n aday (majors önce)."""
    major = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    rows = []
    for sym, d in signals.items():
        if d not in ("UP", "DOWN"):
            continue
        rows.append({
            "symbol": sym,
            "side": "LONG" if d == "UP" else "SHORT",
            "signal": d,
            "score": 2 if sym in major else 1,
        })
    rows.sort(key=lambda x: (-x["score"], x["symbol"]))
    return rows[:max_n]

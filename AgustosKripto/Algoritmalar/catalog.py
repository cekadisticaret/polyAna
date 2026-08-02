#!/usr/bin/env python3
"""ALGO1 (Poly panel) + ALGO2 Top-17 kataloğu.

Sinyal fonksiyonları temmuzPoly/algo_signals(+_v2) üzerinden —
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

# ALGO2 Top-17 (mevcut defterler: algo_01 … algo_17)
ALGOS_V2 = [
    {
        "id": n,
        "uid": str(n),
        "panel": "v2",
        "book_key": f"algo_{n:02d}",
        "name": name,
        "category": cat,
        "kind": kind,
    }
    for n, name, cat, kind, _fn in ALGO_V2_META
]

# Geriye uyum
ALGOS = ALGOS_V2

# ALGO1 — Poly algo_signals.ALGO_META (13/14 skip)
_ALGO1_CATS = {
    1: "Trend", 2: "Momentum", 3: "Trend", 4: "Trend", 5: "Momentum",
    6: "Momentum", 7: "Volatilite", 8: "Hacim", 9: "Hacim", 10: "Hacim",
    11: "İstatistik", 12: "Pairs", 15: "Multi-TF", 16: "Breakout", 17: "Trend",
    18: "Trend", 19: "Regime", 20: "Order Flow", 21: "Sentiment",
    25: "Trend", 26: "Momentum", 27: "Momentum", 28: "Trend", 29: "Trend",
    30: "Volatilite", 31: "Breakout", 32: "Hacim", 33: "Hacim", 34: "ML",
    35: "İstatistik", 36: "Trend", 37: "Trend", 38: "Momentum", 39: "Kombinasyon",
}

_ALGO1_SIMPLE = {
    1: sig.ema_crossover, 2: sig.macd_div, 3: sig.supertrend, 4: sig.ichimoku,
    5: sig.rsi_div, 6: sig.stoch_rsi, 7: sig.bb_squeeze, 8: sig.vwap, 9: sig.obv,
    10: sig.volume_profile, 11: sig.mean_reversion, 16: sig.atr_breakout,
    17: sig.heikin_ashi, 18: sig.tema_crossover, 19: sig.adx_regime,
    25: sig.parabolic_sar_adx, 26: sig.macd_histogram_div, 27: sig.stoch_rsi_kd,
    28: sig.triple_ema, 29: sig.hull_ma, 30: sig.keltner_channel,
    31: sig.donchian_channel, 32: sig.vwap_volume_profile, 33: sig.money_flow_index,
    34: sig.random_forest_clf, 35: sig.markov_chain, 36: sig.supertrend_v2,
    37: sig.ichimoku_v2, 38: sig.rsi_divergence_strict, 39: sig.h1_combination,
}


def _algo1_kind(num: int) -> str:
    if num in sig.SKIP:
        return "skip"
    if num == 12:
        return "pairs"
    if num == 15:
        return "multi_tf"
    if num == 20:
        return "oi"
    if num == 21:
        return "fear_greed"
    if num in _ALGO1_SIMPLE:
        return "fn"
    return "skip"


ALGOS_V1 = []
for num, name in sig.ALGO_META:
    kind = _algo1_kind(num)
    if kind == "skip":
        continue
    ALGOS_V1.append({
        "id": num,
        "uid": f"a1_{num:02d}",
        "panel": "v1",
        "book_key": f"algo1_{num:02d}",
        "name": f"A1#{num:02d} {name}",
        "title": name,
        "category": f"ALGO1 · {_ALGO1_CATS.get(num, '?')}",
        "kind": kind,
    })

# Dashboard / cron — ALGO2 önce, sonra ALGO1
ALL_BOOKS = ALGOS_V2 + ALGOS_V1


def algo_fn_v2(algo_id: int):
    for n, name, cat, kind, fn in ALGO_V2_META:
        if n == algo_id:
            return name, kind, fn
    return None, None, None


def algo_fn(algo_id: int):
    """Geriye uyum — ALGO2."""
    return algo_fn_v2(algo_id)


def _oi_signal(kl: list, oi: list) -> str:
    if len(oi) < 5 or len(kl) < 5:
        return "NEUTRAL"
    try:
        c = [float(k.get("c") if k.get("c") is not None else k.get("close") or 0) for k in kl[-10:]]
        if not c[-5]:
            return "NEUTRAL"
        pc = (c[-1] - c[-5]) / c[-5]
        oc = (oi[-1] - oi[-5]) / oi[-5] if oi[-5] else 0
        if pc > 0.005 and oc > 0.005:
            return "UP"
        if pc < -0.005 and oc > 0.005:
            return "DOWN"
        if pc > 0.005 and oc < -0.005:
            return "DOWN"
        if pc < -0.005 and oc < -0.005:
            return "UP"
    except Exception:
        pass
    return "NEUTRAL"


def _bars_ohlc(kl: list) -> list:
    """virtual_book kline → algo_signals o/h/l/c/v."""
    out = []
    for k in kl or []:
        out.append({
            "o": float(k.get("o") if k.get("o") is not None else k.get("open") or 0),
            "h": float(k.get("h") if k.get("h") is not None else k.get("high") or 0),
            "l": float(k.get("l") if k.get("l") is not None else k.get("low") or 0),
            "c": float(k.get("c") if k.get("c") is not None else k.get("close") or 0),
            "v": float(k.get("v") if k.get("v") is not None else k.get("volume") or 0),
        })
    return out


def _resample_4h(bars_1h: list) -> list:
    out = []
    bucket = []
    for b in bars_1h:
        bucket.append(b)
        if len(bucket) == 4:
            out.append({
                "o": bucket[0]["o"],
                "h": max(x["h"] for x in bucket),
                "l": min(x["l"] for x in bucket),
                "c": bucket[-1]["c"],
                "v": sum(x["v"] for x in bucket),
            })
            bucket = []
    return out


def signal_for_book(book: dict, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    """symbol → UP|DOWN|NEUTRAL — panel v1/v2."""
    panel = book.get("panel") or "v2"
    algo_id = int(book["id"])
    out = {sym: "NEUTRAL" for sym in kl_by_symbol}

    if panel == "v2":
        name, kind, fn = algo_fn_v2(algo_id)
        if kind == "pairs":
            short_map = {}
            for short, pair in sig.SYMBOLS.items():
                short_map[short] = _bars_ohlc(kl_by_symbol.get(pair) or [])
            try:
                pairs = sig.pairs_trading(short_map)
                for short, pair in sig.SYMBOLS.items():
                    out[pair] = pairs.get(short, "NEUTRAL")
            except Exception as e:
                print(f"[Algoritmalar A2#{algo_id}] pairs: {e}")
            return out
        if kind == "fn" and fn:
            for sym, kl in kl_by_symbol.items():
                bars = _bars_ohlc(kl)
                if not bars:
                    continue
                try:
                    out[sym] = fn(bars) or "NEUTRAL"
                except Exception as e:
                    print(f"[Algoritmalar A2#{algo_id}] {sym}: {e}")
                    out[sym] = "NEUTRAL"
        return out

    # ALGO1
    kind = book.get("kind") or "fn"
    if kind == "pairs":
        short_map = {}
        for short, pair in sig.SYMBOLS.items():
            short_map[short] = _bars_ohlc(kl_by_symbol.get(pair) or [])
        try:
            pairs = sig.pairs_trading(short_map)
            for short, pair in sig.SYMBOLS.items():
                out[pair] = pairs.get(short, "NEUTRAL")
        except Exception as e:
            print(f"[Algoritmalar A1#{algo_id}] pairs: {e}")
        return out

    if kind == "multi_tf":
        for sym, kl in kl_by_symbol.items():
            bars = _bars_ohlc(kl)
            htf = _resample_4h(bars)
            if not bars or not htf:
                continue
            try:
                out[sym] = sig.multi_tf(bars, htf) or "NEUTRAL"
            except Exception as e:
                print(f"[Algoritmalar A1#{algo_id}] {sym}: {e}")
        return out

    if kind == "fear_greed":
        try:
            fg = sig.fetch_fear_greed()
        except Exception as e:
            print(f"[Algoritmalar A1#{algo_id}] fg: {e}")
            fg = "NEUTRAL"
        for sym in out:
            out[sym] = fg
        return out

    if kind == "oi":
        for sym in list(out.keys()):
            try:
                oi = sig.fetch_oi_hist(sym, 10)
                out[sym] = _oi_signal(_bars_ohlc(kl_by_symbol.get(sym) or []), oi)
            except Exception as e:
                print(f"[Algoritmalar A1#{algo_id}] oi {sym}: {e}")
                out[sym] = "NEUTRAL"
        return out

    fn = _ALGO1_SIMPLE.get(algo_id)
    if fn:
        for sym, kl in kl_by_symbol.items():
            bars = _bars_ohlc(kl)
            if not bars:
                continue
            try:
                out[sym] = fn(bars) or "NEUTRAL"
            except Exception as e:
                print(f"[Algoritmalar A1#{algo_id}] {sym}: {e}")
                out[sym] = "NEUTRAL"
    return out


def signal_for_algo(algo_id: int, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    """Geriye uyum — ALGO2 id."""
    book = next((b for b in ALGOS_V2 if b["id"] == algo_id), None)
    if not book:
        return {sym: "NEUTRAL" for sym in kl_by_symbol}
    return signal_for_book(book, kl_by_symbol)


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

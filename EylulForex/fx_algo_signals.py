"""XAUUSD sinyal adaptörleri — aynı indikatör, altın mumu.

Poly state yazılmaz. c101_v2 trader import edilmez.
"""
from __future__ import annotations

import math
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_DIR, ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
_ALGO_DIR = os.path.join(_ROOT, "AgustosKripto", "Algoritmalar")
for p in (_POLY, _ALGO_DIR, _DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import algo_signals as sig  # noqa: E402
from algo_signals_v2 import ALGO_V2_META  # noqa: E402
from algo_signals import macd_histogram_div, mean_reversion, rsi_divergence_strict  # noqa: E402
from fx_algo_d import signal_for_d  # noqa: E402

SYMBOL = "XAUUSD"
Z_LO = 1.0
Z_HI = 1.5


def _bars(kl: list) -> list[dict]:
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


def _dir(val) -> str:
    return val if val in ("UP", "DOWN") else "NEUTRAL"


def _fn_on_bars(fn, kl: list) -> str:
    bars = _bars(kl)
    if len(bars) < 20 or not fn:
        return "NEUTRAL"
    try:
        return _dir(fn(bars))
    except Exception as e:
        print(f"[fx_algo] fn: {e}")
        return "NEUTRAL"


def _zscore(kl: list) -> float | None:
    bars = _bars(kl)
    c = [k["c"] for k in bars]
    if len(c) < 20:
        return None
    window = c[-20:]
    mean = sum(window) / 20.0
    var = sum((x - mean) ** 2 for x in window) / 20.0
    std = math.sqrt(var)
    if not std:
        return None
    return (c[-1] - mean) / std


def _a2(num: int, kl: list) -> str:
    for n, _name, _cat, kind, fn in ALGO_V2_META:
        if n != num:
            continue
        if kind == "pairs":
            return "NEUTRAL"
        return _fn_on_bars(fn, kl)
    return "NEUTRAL"


def _analiz1(kl: list) -> str:
    votes = [
        _fn_on_bars(sig.ema_crossover, kl),
        _fn_on_bars(sig.macd_div, kl),
        _fn_on_bars(sig.rsi_div, kl),
    ]
    up = votes.count("UP")
    down = votes.count("DOWN")
    if up >= 2 and up > down:
        return "UP"
    if down >= 2 and down > up:
        return "DOWN"
    return "NEUTRAL"


def _c101(kl: list, band: float) -> str:
    bars = _bars(kl)
    if len(bars) < 24:
        return "NEUTRAL"
    last = bars[-1]
    hour_open = last["o"]
    spot = last["c"]
    if hour_open <= 0 or spot <= 0:
        return "NEUTRAL"
    n12 = bars[-12:]
    n72 = bars[-72:] if len(bars) >= 72 else bars
    def parkinson(rows):
        acc = 0.0
        k = 0
        for r in rows:
            if r["l"] > 0 and r["h"] > r["l"]:
                acc += math.log(r["h"] / r["l"]) ** 2
                k += 1
        if k < 4:
            return None
        return math.sqrt(acc / (4.0 * k * math.log(2)))
    s12 = parkinson(n12)
    s72 = parkinson(n72)
    if not s12:
        return "NEUTRAL"
    sigma = 0.6 * s12 + 0.4 * (s72 or s12)
    t_left = 0.5
    if sigma <= 0:
        return "NEUTRAL"
    z = math.log(spot / hour_open) / (sigma * math.sqrt(t_left))
    p_up = 0.5 * math.erfc(-z / math.sqrt(2.0))
    if p_up >= 0.5 + band:
        return "UP"
    if p_up <= 0.5 - band:
        return "DOWN"
    return "NEUTRAL"


def _x101(kl: list) -> str:
    votes = [
        _fn_on_bars(mean_reversion, kl),
        _fn_on_bars(macd_histogram_div, kl),
        _fn_on_bars(rsi_divergence_strict, kl),
        _fn_on_bars(sig.supertrend, kl),
        _fn_on_bars(sig.ema_crossover, kl),
        _a2(2, kl),
        _a2(8, kl),
        _a2(16, kl),
    ]
    up = votes.count("UP")
    down = votes.count("DOWN")
    if up >= 5 and up > down:
        return "UP"
    if down >= 5 and down > up:
        return "DOWN"
    return "NEUTRAL"


def _b1_mum(kl: list) -> str:
    try:
        from b1_mum_signal import resolve_direction
        return _dir(resolve_direction(SYMBOL, _bars(kl)))
    except Exception as e:
        print(f"[fx_algo] b1_mum: {e}")
        return _fn_on_bars(mean_reversion, kl)


def _analiz15(kl: list) -> str:
    try:
        from analiz15_signal import resolve_direction
        import asyncio

        async def _one():
            return await resolve_direction(SYMBOL, _bars(kl))

        try:
            d = asyncio.run(_one())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                d = loop.run_until_complete(_one())
            finally:
                loop.close()
        return _dir(d)
    except Exception as e:
        print(f"[fx_algo] a15: {e}")
        return _fn_on_bars(macd_histogram_div, kl)


def _best_from_histories(motors: list[str]) -> str | None:
    """Bu sistemin XAU geçmişinden en yüksek WR motor; yoksa None."""
    from fx_algo_book import load_history

    best_uid, best_wr, best_n = None, -1.0, 0
    for uid in motors:
        hist = load_history(uid)
        if len(hist) < 5:
            continue
        wins = sum(1 for t in hist if float(t.get("pnl") or 0) > 0)
        wr = wins / len(hist)
        if wr > best_wr or (wr == best_wr and len(hist) > best_n):
            best_uid, best_wr, best_n = uid, wr, len(hist)
    return best_uid


def _run_uid(uid: str, kl: list) -> str:
    if uid == "a2_05":
        return _fn_on_bars(mean_reversion, kl)
    if uid.startswith("a2_"):
        try:
            return _a2(int(uid.split("_")[1]), kl)
        except Exception:
            return "NEUTRAL"
    if uid in ("analiz6", "analiz6_v3"):
        return _fn_on_bars(macd_histogram_div, kl)
    if uid == "analiz6_v2":
        return _fn_on_bars(rsi_divergence_strict, kl)
    if uid == "melez":
        return _fn_on_bars(mean_reversion, kl)
    if uid == "analiz15":
        return _analiz15(kl)
    if uid == "b1_mum":
        return _b1_mum(kl)
    return _fn_on_bars(mean_reversion, kl)


def _b1(source_key: str, kl: list) -> str:
    if source_key == "b1_02":
        return _analiz15(kl) or _fn_on_bars(macd_histogram_div, kl)
    pool = ["a2_05", "analiz6", "analiz6_v3", "melez", "b1_mum", "analiz15", "a2_02", "a2_01"]
    picked = _best_from_histories(pool)
    return _run_uid(picked or "a2_05", kl)


def signal_for_book(book: dict, kl: list) -> str:
    src = book.get("source") or ""
    key = book.get("source_key") or book.get("uid") or ""
    if src == "d_family" or key.startswith("d10"):
        return signal_for_d(key, kl)
    if src == "placeholder" or key.startswith("a40"):
        return "NEUTRAL"
    if src == "a2":
        return _a2(int(book.get("id") or 0), kl)
    if key == "a2_05_v2":
        z = _zscore(kl)
        if z is None or not (Z_LO <= abs(z) < Z_HI):
            return "NEUTRAL"
        return _fn_on_bars(mean_reversion, kl)
    if key in ("analiz1", "analiz2"):
        return _analiz1(kl)
    if key in ("analiz6", "analiz6_v3"):
        return _fn_on_bars(macd_histogram_div, kl)
    if key == "analiz6_v2":
        return _fn_on_bars(rsi_divergence_strict, kl)
    if key == "melez":
        return _fn_on_bars(mean_reversion, kl)
    if key == "analiz15":
        return _analiz15(kl)
    if key == "b1_mum":
        return _b1_mum(kl)
    if key in ("b1_01", "b1_02", "b1_04", "b1_05"):
        return _b1(key, kl)
    if key == "c101":
        return _c101(kl, 0.05)
    if key == "c101_v2":
        return _c101(kl, float(os.environ.get("C101_V2_EDGE_MIN") or 0.03))
    if key == "x101":
        return _x101(kl)
    return "NEUTRAL"

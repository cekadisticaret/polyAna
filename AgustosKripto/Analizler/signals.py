#!/usr/bin/env python3
"""Analiz sinyal sarmalayıcıları — A1 A2 A10 A6(Supertrend).

Poly trader dosyalarına dokunulmaz. A3 Freqtrade / A8 Jesse kaldırıldı.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Callable

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
if _POLY not in sys.path:
    sys.path.insert(0, _POLY)

ANALIZ_META = [
    {"id": "a1", "name": "A1", "title": "1. Analiz"},
    {"id": "a2", "name": "A2", "title": "2. Analiz (SOL motor)"},
    {"id": "a10", "name": "A10", "title": "10. Analiz Dual"},
    {"id": "a6", "name": "A6", "title": "Supertrend · $10×15x · max 4 · alt (BTC/ETH yok)"},
]


def _dir_from_pred(pred) -> str | None:
    if pred is None:
        return None
    d = getattr(pred, "predicted_dir", None) or (pred.get("predicted_dir") if isinstance(pred, dict) else None)
    if d in ("UP", "DOWN"):
        return d
    return None


def signal_a1(symbol: str, kl: list) -> str:
    try:
        from poly_predictor_analysis import predict
        pred = asyncio.run(predict(symbol))
        return _dir_from_pred(pred) or "NEUTRAL"
    except Exception as e:
        print(f"[Analizler A1] {symbol}: {e}")
        return "NEUTRAL"


def signal_a2(symbol: str, kl: list) -> str:
    # A2 motoru aynı predictor (poly dokunulmaz)
    return signal_a1(symbol, kl)


def signal_a10(symbol: str, kl: list) -> str:
    try:
        from poly_analiz_dual_core import CONFIG_A10, evaluate_symbol
        r, _reason, _diag = asyncio.run(evaluate_symbol(symbol, CONFIG_A10))
        if not r:
            return "NEUTRAL"
        d = r.get("direction") or r.get("predicted_dir")
        return d if d in ("UP", "DOWN") else "NEUTRAL"
    except Exception as e:
        print(f"[Analizler A10] {symbol}: {e}")
        return "NEUTRAL"


def supertrend_scored(kl: list, p: int = 10, mult: float = 3.0) -> tuple[str, float]:
    """Supertrend yön + güç skoru (yüksek = daha başarılı aday).

    Skor: fiyat–ST mesafesi/ATR + streak + taze flip bonusu.
    """
    if not kl or len(kl) < p + 5:
        return "NEUTRAL", 0.0
    try:
        from algo_signals import _atr
    except Exception:
        return "NEUTRAL", 0.0

    c = [float(k["c"]) for k in kl]
    h = [float(k["h"]) for k in kl]
    l = [float(k["l"]) for k in kl]
    av = _atr(kl, p)
    up = [None] * len(kl)
    dn = [None] * len(kl)
    st = [None] * len(kl)
    dr = [0] * len(kl)
    for i in range(p, len(kl)):
        if av[i] is None:
            continue
        hl2 = (h[i] + l[i]) / 2
        bu = hl2 + mult * av[i]
        bl = hl2 - mult * av[i]
        up[i] = min(bu, up[i - 1]) if up[i - 1] and c[i - 1] > up[i - 1] else bu
        dn[i] = max(bl, dn[i - 1]) if dn[i - 1] and c[i - 1] < dn[i - 1] else bl
        if st[i - 1] is None:
            st[i] = up[i]
            dr[i] = -1
        elif st[i - 1] == up[i - 1]:
            if c[i] < up[i]:
                st[i] = up[i]
                dr[i] = -1
            else:
                st[i] = dn[i]
                dr[i] = 1
        else:
            if c[i] > dn[i]:
                st[i] = dn[i]
                dr[i] = 1
            else:
                st[i] = up[i]
                dr[i] = -1

    d = "UP" if dr[-1] == 1 else "DOWN" if dr[-1] == -1 else "NEUTRAL"
    if d == "NEUTRAL" or st[-1] is None or not av[-1]:
        return d, 0.0

    atr = float(av[-1]) or 1e-9
    dist = abs(c[-1] - float(st[-1])) / atr  # trend tarafında ne kadar içeride
    streak = 0
    for x in reversed(dr):
        if x == dr[-1] and x != 0:
            streak += 1
        else:
            break
    flip = 1.0 if len(dr) >= 2 and dr[-1] != 0 and dr[-2] != 0 and dr[-1] != dr[-2] else 0.0
    # Taze flip + orta mesafe iyi; aşırı uzamış trend biraz kırpılır
    score = dist * 2.0 + min(streak, 8) * 0.35 + flip * 1.5
    if dist > 4:
        score *= 0.85  # aşırı uzamış — mean-revert riski
    return d, round(score, 4)


def signal_a6(symbol: str, kl: list) -> str:
    """Eski A6 (MACD/RSI) yerine Supertrend — ALGO2 #16 ile aynı mantık."""
    try:
        d, _sc = supertrend_scored(kl)
        return d if d in ("UP", "DOWN") else "NEUTRAL"
    except Exception as e:
        print(f"[Analizler Supertrend] {symbol}: {e}")
        return "NEUTRAL"


_HANDLERS: dict[str, Callable] = {
    "a1": signal_a1,
    "a2": signal_a2,
    "a10": signal_a10,
    "a6": signal_a6,
}


def resolve(analiz_id: str, symbol: str, kl: list) -> str:
    fn = _HANDLERS.get(analiz_id)
    if not fn:
        return "NEUTRAL"
    return fn(symbol, kl) or "NEUTRAL"

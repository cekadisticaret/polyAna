#!/usr/bin/env python3
"""Analiz sinyal sarmalayıcıları — A1 A2 A3 A8 A10 A6(Supertrend).

Poly trader dosyalarına dokunulmaz; temmuzPoly / freqtrade / jesse import.
A3 → freqtrade/.venv (talib), A8 → jesse/.venv (jesse) — sistem python'da yok.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from typing import Callable

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
_FT = os.path.join(_ROOT, "freqtrade")
_JESSE = os.path.join(_ROOT, "jesse")
_FT_PY = os.path.join(_FT, ".venv", "bin", "python")
_JESSE_PY = os.path.join(_JESSE, ".venv", "bin", "python")
for p in (_POLY, _FT, _JESSE):
    if p not in sys.path:
        sys.path.insert(0, p)

ANALIZ_META = [
    {"id": "a1", "name": "A1", "title": "1. Analiz"},
    {"id": "a2", "name": "A2", "title": "2. Analiz (SOL motor)"},
    {"id": "a3", "name": "A3", "title": "3. Analiz Freqtrade"},
    {"id": "a8", "name": "A8", "title": "8. Analiz Jesse"},
    {"id": "a10", "name": "A10", "title": "10. Analiz Dual"},
    {"id": "a6", "name": "A6", "title": "Supertrend · $10×15x · max 4 · alt (BTC/ETH yok)"},
]

# Saatlik open sırasında A3/A8 batch cache
_VENV_CACHE: dict[str, dict[str, str]] = {}


def _dir_from_pred(pred) -> str | None:
    if pred is None:
        return None
    d = getattr(pred, "predicted_dir", None) or (pred.get("predicted_dir") if isinstance(pred, dict) else None)
    if d in ("UP", "DOWN"):
        return d
    return None


def clear_venv_cache() -> None:
    _VENV_CACHE.clear()


def _venv_batch(kind: str, symbols: list[str]) -> dict[str, str]:
    """A3/A8 sinyallerini ilgili .venv içinde toplu hesapla."""
    if kind == "a3":
        py, cwd, mod = _FT_PY, _FT, "analiz3_signal"
    elif kind == "a8":
        py, cwd, mod = _JESSE_PY, _JESSE, "analiz8_signal"
    else:
        return {s: "NEUTRAL" for s in symbols}

    if not os.path.isfile(py):
        print(f"[Analizler {kind.upper()}] venv yok: {py}")
        return {s: "NEUTRAL" for s in symbols}

    script = (
        "import json, sys\n"
        f"from {mod} import predict_pm_direction\n"
        "syms = json.loads(sys.argv[1])\n"
        "out = {}\n"
        "for s in syms:\n"
        "    try:\n"
        "        p = predict_pm_direction(s)\n"
        "        d = getattr(p, 'predicted_dir', None) if p is not None else None\n"
        "        out[s] = d if d in ('UP', 'DOWN') else 'NEUTRAL'\n"
        "    except Exception as e:\n"
        "        out[s] = 'NEUTRAL'\n"
        "        print(f'[{mod}] {s}: {e}', file=sys.stderr)\n"
        "print(json.dumps(out))\n"
    )
    try:
        r = subprocess.run(
            [py, "-c", script, json.dumps(list(symbols))],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except Exception as e:
        print(f"[Analizler {kind.upper()}] venv spawn: {e}")
        return {s: "NEUTRAL" for s in symbols}

    if r.stderr:
        for line in r.stderr.strip().splitlines()[-8:]:
            print(f"[Analizler {kind.upper()}] {line}")
    if r.returncode != 0:
        print(f"[Analizler {kind.upper()}] venv exit {r.returncode}")
        return {s: "NEUTRAL" for s in symbols}

    lines = [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]
    if not lines:
        return {s: "NEUTRAL" for s in symbols}
    try:
        data = json.loads(lines[-1])
        if isinstance(data, dict):
            return {s: (data.get(s) if data.get(s) in ("UP", "DOWN") else "NEUTRAL") for s in symbols}
    except Exception as e:
        print(f"[Analizler {kind.upper()}] JSON: {e}")
    return {s: "NEUTRAL" for s in symbols}


def prefetch_a3_a8(symbols: list[str]) -> None:
    """Open turu başında bir kez çağır — sembol başına subprocess yok."""
    _VENV_CACHE["a3"] = _venv_batch("a3", symbols)
    _VENV_CACHE["a8"] = _venv_batch("a8", symbols)
    a3_n = sum(1 for v in _VENV_CACHE["a3"].values() if v in ("UP", "DOWN"))
    a8_n = sum(1 for v in _VENV_CACHE["a8"].values() if v in ("UP", "DOWN"))
    print(f"[Analizler] prefetch A3={a3_n}/{len(symbols)} A8={a8_n}/{len(symbols)} yön")


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


def signal_a3(symbol: str, kl: list) -> str:
    cached = _VENV_CACHE.get("a3")
    if cached is not None:
        return cached.get(symbol, "NEUTRAL")
    return _venv_batch("a3", [symbol]).get(symbol, "NEUTRAL")


def signal_a8(symbol: str, kl: list) -> str:
    cached = _VENV_CACHE.get("a8")
    if cached is not None:
        return cached.get(symbol, "NEUTRAL")
    return _venv_batch("a8", [symbol]).get(symbol, "NEUTRAL")


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
    "a3": signal_a3,
    "a8": signal_a8,
    "a10": signal_a10,
    "a6": signal_a6,
}


def resolve(analiz_id: str, symbol: str, kl: list) -> str:
    fn = _HANDLERS.get(analiz_id)
    if not fn:
        return "NEUTRAL"
    return fn(symbol, kl) or "NEUTRAL"

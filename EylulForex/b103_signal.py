"""B1#03 mum confluence — `b1_mum_signal` (Poly B1#03 MUM), XAUUSD 1h.

b1_mum_signal.py / forex_signal.py / CEM01 dokunulmaz.
"""
from __future__ import annotations

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_DIR, ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
if _POLY not in sys.path:
    sys.path.insert(0, _POLY)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from b1_mum_signal import (  # noqa: E402
    CANDLE_LIMIT,
    SCORE_GATE,
    _PATTERN_TR,
    _dominant_pattern,
    _normalize_klines,
    _run_analysis,
    resolve_direction,
)

SYMBOL = "XAUUSD"


def _klines(n: int | None = None) -> list[dict]:
    from forex_data import get_xau_klines
    rows, _ = get_xau_klines("1h", int(n or CANDLE_LIMIT))
    return list(rows or [])


def _pack(rows: list[dict]) -> dict:
    info = _run_analysis(_normalize_klines(rows)) if rows else None
    raw = resolve_direction(SYMBOL, rows)
    direction = raw if raw in ("UP", "DOWN") else "NEUTRAL"
    score = float((info or {}).get("score") or 0)
    dom = _dominant_pattern((info or {}).get("patterns") or {})
    pat = _PATTERN_TR.get(dom or "", dom or "")
    detail = f"skor {score:+.0f}"
    if pat:
        detail += f" · {pat}"
    expl = (info or {}).get("explanation") or ""
    if expl:
        detail += f" — {expl}"
    if direction == "NEUTRAL":
        detail = f"nötr {score:+.0f} (eşik ±{SCORE_GATE:.0f})"
    return {
        "direction": direction,
        "confidence": round(min(100.0, abs(score)), 1),
        "is_stable": direction in ("UP", "DOWN"),
        "engine": "b1_mum",
        "score": round(score, 2),
        "gate": SCORE_GATE,
        "tf": "1h",
        "meta": detail,
        "explanation": detail,
        "patterns": (info or {}).get("patterns") or {},
    }


def live_signal(tf: str = "1h", candles=None, klines_fn=None, **_kw) -> dict:
    rows = list(candles) if candles else _klines()
    if klines_fn is not None and not candles:
        try:
            rows = list(klines_fn("1h", CANDLE_LIMIT) or [])
        except Exception:
            rows = _klines()
    out = _pack(rows)
    try:
        from forex_signal import rail_signals
        out["rail"] = rail_signals(klines_fn=klines_fn) if klines_fn is not None else rail_signals()
    except Exception:
        out["rail"] = {}
    return out


def overlay_signals(tf: str, candles: list[dict], klines_fn=None, **_kw) -> tuple[dict, list[dict]]:
    packed = live_signal(tf, klines_fn=klines_fn)
    markers: list[dict] = []
    rows = []
    if klines_fn is not None:
        try:
            rows = list(klines_fn("1h", max(CANDLE_LIMIT, 80)) or [])
        except Exception:
            rows = []
    if not rows:
        rows = _klines(80)
    last = None
    start = max(5, len(rows) - 36)
    for i in range(start, len(rows)):
        d = resolve_direction(SYMBOL, rows[: i + 1])
        d = d if d in ("UP", "DOWN") else "NEUTRAL"
        if d in ("UP", "DOWN") and d != last:
            last = d
            markers.append({
                "time": int(rows[i].get("time") or 0),
                "direction": d,
                "confidence": 0,
            })
    packed["rail"] = packed.get("rail") or {}
    return packed, markers[-48:]


def rail_signals(klines_fn=None):
    from forex_signal import rail_signals as _rail
    return _rail(klines_fn=klines_fn) if klines_fn is not None else _rail()


def sr_levels(candles):
    from forex_signal import sr_levels as _sr
    return _sr(candles)

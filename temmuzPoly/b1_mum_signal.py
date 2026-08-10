"""B1#03 MUM ANALİZ — Sonnet candle_pattern_engine1 saatlik confluence sinyali."""
from __future__ import annotations

import importlib
import os
import sys

import numpy as np

_DIR_POLY = os.path.dirname(os.path.abspath(__file__))
_DIR_SONNET = os.path.join(_DIR_POLY, "..", "Sonnet")

sys.path.insert(0, _DIR_POLY)
from poly_predictor_analysis import _fetch_klines

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SCORE_GATE = 15.0
CANDLE_LIMIT = 72

_PATTERN_TR = {
    "doji": "doji",
    "marubozu": "marubozu",
    "hammer": "çekiç",
    "shooting_star": "yıldız",
    "engulfing": "engulfing",
    "piercing_darkcloud": "piercing",
    "star": "yıldız form.",
    "three_soldiers_crows": "3 asker/karga",
}


def engine_label(_symbol: str = "") -> str:
    return "Mum confluence 1h"


def _dominant_pattern(pats: dict) -> str | None:
    if not pats:
        return None
    weights = {
        "engulfing": 3, "star": 3, "three_soldiers_crows": 2.5,
        "hammer": 2, "shooting_star": 2, "marubozu": 1.5,
        "piercing_darkcloud": 1.5, "doji": 0.3,
    }
    best, best_w = None, 0.0
    for name, val in pats.items():
        if not val:
            continue
        w = abs(float(val)) * weights.get(name, 1.0)
        if w > best_w:
            best_w = w
            best = name
    return best


def _run_analysis(klines: list[dict]) -> dict | None:
    if not klines or len(klines) < 5:
        return None
    if _DIR_SONNET not in sys.path:
        sys.path.insert(0, _DIR_SONNET)
    engine_mod = importlib.import_module("candle_pattern_engine1")
    CandleEngine = engine_mod.CandleEngine

    o = np.array([float(k["open"]) for k in klines], dtype=float)
    h = np.array([float(k["high"]) for k in klines], dtype=float)
    l = np.array([float(k["low"]) for k in klines], dtype=float)
    cl = np.array([float(k["close"]) for k in klines], dtype=float)
    engine = CandleEngine(o, h, l, cl)
    result = engine.confluence_score()
    all_patterns = engine.detect_patterns()
    active = {k: v for k, v in all_patterns[-1].items() if v != 0}
    return {
        "score": float(result.score),
        "explanation": result.explanation,
        "patterns": active,
    }


def _normalize_klines(klines: list) -> list[dict]:
    out: list[dict] = []
    for k in klines:
        out.append({
            "open": float(k.get("open", k.get("o", 0))),
            "high": float(k.get("high", k.get("h", 0))),
            "low": float(k.get("low", k.get("l", 0))),
            "close": float(k.get("close", k.get("c", 0))),
            "volume": float(k.get("volume", k.get("v", 0))),
        })
    return out


def resolve_direction(symbol: str, klines: list | None = None, *, poly_symbols_only: bool = False) -> str | None:
    """Önceden yüklenmiş 1h mumlardan yön (Kripto Test/backtest).

    poly_symbols_only=True → yalnızca SYMBOLS (Poly sanal B1 MUM).
  """
    if poly_symbols_only and symbol not in SYMBOLS:
        return None
    if not klines or len(klines) < 5:
        return None
    info = _run_analysis(_normalize_klines(klines))
    if not info:
        return None
    score = info["score"]
    if score > SCORE_GATE:
        return "UP"
    if score < -SCORE_GATE:
        return "DOWN"
    return None


async def resolve_live_signal(symbol: str) -> tuple[str | None, float | None, str]:
    """(UP|DOWN|None, fiyat, açıklama) — skor ±15 eşiği."""
    klines = await _fetch_klines(symbol, "1h", CANDLE_LIMIT)
    if not klines:
        return None, None, "veri yok"
    price = float(klines[-1]["close"])
    info = _run_analysis(_normalize_klines(klines))
    if not info:
        return None, price, "yetersiz mum"

    score = info["score"]
    dom = _dominant_pattern(info.get("patterns") or {})
    pat_lbl = _PATTERN_TR.get(dom or "", dom or "")
    detail = f"skor {score:+.0f}"
    if pat_lbl:
        detail += f" · {pat_lbl}"
    if info.get("explanation"):
        detail += f" — {info['explanation']}"

    if score > SCORE_GATE:
        return "UP", price, detail
    if score < -SCORE_GATE:
        return "DOWN", price, detail
    return None, price, f"nötr {score:+.0f} (eşik ±{SCORE_GATE:.0f})"

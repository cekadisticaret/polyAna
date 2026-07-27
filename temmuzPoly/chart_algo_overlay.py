"""
Grafik overlay — 5M110Analiz FeatureEngine (110/111/109 mantığı).
Pine Script değil; Python motorundan EMA, composite ve sinyal okları.
"""
from __future__ import annotations

import math
import sys
import os
from typing import Any

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_A110 = os.path.join(os.path.dirname(_DIR), "5M110Analiz")
sys.path.insert(0, _DIR)
sys.path.insert(0, _A110)

from btc_5m_105_algo import fetch_klines_15m
from core.base import OHLCV
from features.engine import FeatureEngine
from predictor import predict_from_klines

ALGO_META = {
    "110": {"label": "110", "default_gate": 15.0},
    "111": {"label": "a1", "default_gate": 15.0},
    "109": {"label": "a2", "default_gate": 15.0},
}


def _dec(symbol: str) -> int:
    return 1 if symbol.replace("USDT", "") == "BTC" else 2


def _klines_to_ohlcv(klines: list[dict]) -> OHLCV:
    return OHLCV(
        open_=np.array([k["open"] for k in klines], dtype=np.float64),
        high=np.array([k["high"] for k in klines], dtype=np.float64),
        low=np.array([k["low"] for k in klines], dtype=np.float64),
        close=np.array([k["close"] for k in klines], dtype=np.float64),
        volume=np.array([k["volume"] for k in klines], dtype=np.float64),
    )


def _series(times: list[int], arr, dec: int) -> list[dict]:
    out: list[dict] = []
    for t, v in zip(times, arr):
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            continue
        out.append({"time": int(t), "value": round(fv, dec)})
    return out


def _composite_series(times: list[int], arr) -> list[dict]:
    out: list[dict] = []
    for t, v in zip(times, arr):
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            continue
        out.append({"time": int(t), "value": round(fv, 1)})
    return out


def _signal_at_bar(composite: float, trend: float, algo: str, gate: float) -> str | None:
    if algo == "111":
        if composite >= gate and trend > 0:
            return "UP"
        if composite <= -gate and trend < 0:
            return "DOWN"
        return None
    if composite >= gate:
        return "UP"
    if composite <= -gate:
        return "DOWN"
    return None


def compute_algo_overlay(
    symbol: str,
    algo: str = "110",
    ema_fast: int = 9,
    ema_slow: int = 21,
    gate: float | None = None,
) -> dict[str, Any]:
    """15m FeatureEngine serileri + sinyal okları."""
    algo = algo if algo in ALGO_META else "110"
    meta = ALGO_META[algo]
    gate = float(gate if gate is not None else meta["default_gate"])
    ema_fast = max(2, min(50, int(ema_fast)))
    ema_slow = max(3, min(100, int(ema_slow)))
    if ema_slow <= ema_fast:
        ema_slow = ema_fast + 1
    dec = _dec(symbol)

    try:
        klines = fetch_klines_15m(symbol, 150)
    except Exception as e:
        return {"ok": False, "error": str(e), "algo": algo}

    if not klines or len(klines) < 80:
        return {"ok": False, "error": "yetersiz 15m veri", "algo": algo}

    closed = klines[:-1]
    times = [int(k["open_time"] // 1000) for k in closed]

    engine = FeatureEngine(trend_periods=[ema_fast, ema_slow, 50])
    fv = engine.compute(_klines_to_ohlcv(closed))
    by = fv.to_dict()

    ema_f_key = f"ema_{ema_fast}"
    ema_s_key = f"ema_{ema_slow}"
    composite = by.get("composite_signal", np.array([]))
    trend = by.get("trend_score", np.array([]))
    momentum = by.get("momentum_score", np.array([]))

    overlays = {
        "ema_fast": _series(times, by.get(ema_f_key, []), dec),
        "ema_slow": _series(times, by.get(ema_s_key, []), dec),
        "composite": _composite_series(times, composite),
        "trend": _composite_series(times, trend),
    }

    signals: list[dict] = []
    n = min(len(times), len(composite))
    for i in range(n):
        comp = float(composite[i])
        tr = float(trend[i]) if i < len(trend) else 0.0
        if math.isnan(comp):
            continue
        d = _signal_at_bar(comp, tr, algo, gate)
        if d:
            signals.append({"time": times[i], "dir": d})

    pred = predict_from_klines(symbol, klines)
    current: dict[str, Any] = {
        "composite": 0.0,
        "trend": 0.0,
        "momentum": 0.0,
        "up_score": 0,
        "down_score": 0,
        "direction": None,
        "confidence": 0.0,
        "label": "—",
        "gate": gate,
    }
    if pred:
        comp_last = float(composite[-1]) if len(composite) else 0.0
        tr_last = float(trend[-1]) if len(trend) else 0.0
        mom_last = float(momentum[-1]) if len(momentum) else 0.0
        direction = _signal_at_bar(comp_last, tr_last, algo, gate)
        up_pct = int(round(max(0.0, min(100.0, abs(comp_last)))))
        down_pct = int(round(max(0.0, min(100.0, abs(comp_last)))))
        if direction == "UP":
            lbl = f"YUKARI {up_pct}%"
        elif direction == "DOWN":
            lbl = f"AŞAĞI {down_pct}%"
        elif comp_last > 0:
            lbl = f"YUKARI {up_pct}%"
        elif comp_last < 0:
            lbl = f"AŞAĞI {down_pct}%"
        else:
            lbl = "NÖTR"
        guide_dir = direction
        if guide_dir is None:
            if comp_last > 0:
                guide_dir = "UP"
            elif comp_last < 0:
                guide_dir = "DOWN"
        current = {
            "composite": round(comp_last, 1),
            "trend": round(tr_last, 1),
            "momentum": round(mom_last, 1),
            "up_score": pred.up_score,
            "down_score": pred.down_score,
            "direction": direction,
            "guide_dir": guide_dir,
            "confidence": round(pred.confidence, 2),
            "label": lbl,
            "gate": gate,
            "factors": pred.factors,
        }

    return {
        "ok": True,
        "algo": algo,
        "algo_label": meta["label"],
        "engine_tf": "15m",
        "params": {"ema_fast": ema_fast, "ema_slow": ema_slow, "gate": gate},
        "overlays": overlays,
        "signals": signals[-40:],
        "current": current,
    }

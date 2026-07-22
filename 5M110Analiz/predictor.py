"""
5M110Analiz trader adaptörü.

FeatureEngine / CompositeScores çıktısını (composite_signal) saatlik
UP/DOWN tahminine çevirir. core/ ve features/ algoritmasına dokunmaz.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from core.base import OHLCV
from features.engine import FeatureEngine

# Adaptör eşiği — kütüphane içi skorları değiştirmez; yalnızca trade gate
_SIGNAL_GATE = 15.0
_MIN_BARS = 80
_ENGINE = FeatureEngine()


@dataclass
class Prediction:
    symbol: str
    current_price: float
    predicted_dir: Optional[str]
    prob_up: float
    prob_down: float
    confidence: float
    up_score: int
    down_score: int
    up_gate: int
    down_gate: int
    factors: list
    htf_bias: str
    timestamp: float


def _klines_to_ohlcv(klines: list[dict]) -> OHLCV:
    return OHLCV(
        open_=np.array([k["open"] for k in klines], dtype=np.float64),
        high=np.array([k["high"] for k in klines], dtype=np.float64),
        low=np.array([k["low"] for k in klines], dtype=np.float64),
        close=np.array([k["close"] for k in klines], dtype=np.float64),
        volume=np.array([k["volume"] for k in klines], dtype=np.float64),
    )


def _last(arr, default=0.0) -> float:
    """Son geçerli (non-NaN) değer; yoksa default."""
    if arr is None or len(arr) == 0:
        return default
    for v in arr[::-1]:
        fv = float(v)
        if not np.isnan(fv):
            return fv
    return default


def predict_from_klines(symbol: str, klines: list[dict]) -> Optional[Prediction]:
    """Kapalı mumlar üzerinde FeatureEngine → Prediction."""
    if not klines or len(klines) < _MIN_BARS:
        return None

    # Son bar çoğu zaman oluşumda; özellik için kapalı mumlar
    closed = klines[:-1] if len(klines) > _MIN_BARS else klines
    if len(closed) < _MIN_BARS:
        return None

    ohlcv = _klines_to_ohlcv(closed)
    fv = _ENGINE.compute(ohlcv)
    by_name = fv.to_dict()

    composite = _last(by_name.get("composite_signal"))
    trend = _last(by_name.get("trend_score"))
    momentum = _last(by_name.get("momentum_score"))
    vol_pressure = _last(by_name.get("volume_pressure"))
    regime = _last(by_name.get("market_regime"))
    price = float(closed[-1]["close"])

    up_score = int(round(max(0.0, composite)))
    down_score = int(round(max(0.0, -composite)))
    gate = int(_SIGNAL_GATE)

    predicted_dir = None
    if composite >= _SIGNAL_GATE:
        predicted_dir = "UP"
    elif composite <= -_SIGNAL_GATE:
        predicted_dir = "DOWN"

    if predicted_dir:
        strength = min(1.0, abs(composite) / 100.0)
        confidence = max(0.50, min(0.90, 0.50 + strength * 0.40))
        prob_up = confidence if predicted_dir == "UP" else 1.0 - confidence
        prob_down = confidence if predicted_dir == "DOWN" else 1.0 - confidence
    else:
        confidence = 0.0
        prob_up = prob_down = 0.0

    factors: List[str] = [
        f"composite:{composite:+.1f}",
        f"trend:{trend:+.1f}",
        f"momentum:{momentum:+.1f}",
        f"vol_pressure:{vol_pressure:+.1f}",
        f"regime:{regime:+.0f}",
    ]

    regime_lbl = {2: "strong_up", 1: "up", 0: "range", -1: "down", -2: "strong_down"}.get(
        int(regime), f"{regime:+.0f}"
    )
    htf_str = f"regime:{regime_lbl} trend:{trend:+.0f}"

    return Prediction(
        symbol=symbol,
        current_price=price,
        predicted_dir=predicted_dir,
        prob_up=prob_up,
        prob_down=prob_down,
        confidence=confidence,
        up_score=up_score,
        down_score=down_score,
        up_gate=gate,
        down_gate=gate,
        factors=factors,
        htf_bias=htf_str,
        timestamp=time.time(),
    )


async def analyze(symbol: str) -> Optional[Prediction]:
    """Trader entegrasyonu — 1h Binance verisi + FeatureEngine."""
    from data_fetcher import fetch_klines

    klines = await fetch_klines(symbol, "1h", 150)
    return predict_from_klines(symbol, klines)

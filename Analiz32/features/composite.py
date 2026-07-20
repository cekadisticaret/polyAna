"""
features/composite.py

Composite scores: trend, momentum, volatility, regime.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from typing import Dict

from core.base import OHLCV


class CompositeScores:
    """Compute composite feature scores."""

    def compute(
        self,
        ohlcv: OHLCV,
        trend: Dict[str, NDArray[np.float64]],
        momentum: Dict[str, NDArray[np.float64]],
        volatility: Dict[str, NDArray[np.float64]],
        volume: Dict[str, NDArray[np.float64]],
    ) -> Dict[str, NDArray[np.float64]]:
        n = len(ohlcv)
        features: Dict[str, NDArray[np.float64]] = {}

        # Trend score
        trend_score = np.zeros(n, dtype=np.float64)
        if "ema_alignment" in trend:
            trend_score += trend["ema_alignment"] * 30
        if "ema_9_slope" in trend:
            trend_score += np.clip(trend["ema_9_slope"] * 10, -30, 30)
        if "ema_21_slope" in trend:
            trend_score += np.clip(trend["ema_21_slope"] * 10, -30, 30)
        features["trend_score"] = np.clip(trend_score, -100, 100)

        # Momentum score
        mom_score = np.zeros(n, dtype=np.float64)
        if "rsi_norm" in momentum:
            mom_score += momentum["rsi_norm"] * 40
        if "macd_above_signal" in momentum:
            mom_score += momentum["macd_above_signal"] * 30
        if "macd_hist_momentum" in momentum:
            mom_score += np.clip(momentum["macd_hist_momentum"] * 50, -30, 30)
        features["momentum_score"] = np.clip(mom_score, -100, 100)

        # Volatility score
        vol_score = np.zeros(n, dtype=np.float64)
        if "atr_pct" in volatility:
            atr_pct = volatility["atr_pct"]
            vol_score += np.clip(atr_pct * 10, 0, 50)
        if "bb_width" in volatility:
            bbw = volatility["bb_width"]
            vol_score += np.clip(bbw * 100, 0, 50)
        features["volatility_score"] = np.clip(vol_score, 0, 100)

        # Volume pressure
        vol_pressure = np.zeros(n, dtype=np.float64)
        if "cmf" in volume:
            vol_pressure += volume["cmf"] * 50
        if "obv_slope" in volume:
            vol_pressure += np.clip(volume["obv_slope"], -50, 50)
        features["volume_pressure"] = np.clip(vol_pressure, -100, 100)

        # Market regime
        regime = np.zeros(n, dtype=np.float64)
        for i in range(n):
            ts = features["trend_score"][i]
            vs = features["volatility_score"][i]

            if np.isnan(ts) or np.isnan(vs):
                regime[i] = np.nan
                continue

            if vs > 60:
                regime[i] = 2.0 if ts > 0 else -2.0
            elif abs(ts) > 50:
                regime[i] = 1.0 if ts > 0 else -1.0
            else:
                regime[i] = 0.0

        features["market_regime"] = regime

        # Composite signal
        composite = (
            features["trend_score"] * 0.3 +
            features["momentum_score"] * 0.3 +
            features["volume_pressure"] * 0.2 +
            (50 - features["volatility_score"]) * 0.2
        )
        features["composite_signal"] = np.clip(composite, -100, 100)

        return features

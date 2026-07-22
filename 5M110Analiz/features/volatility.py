"""
features/volatility.py

Volatility features: ATR, Bollinger Bands, expansion.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from typing import Dict

from core.base import OHLCV
from core.indicators import ATR, BollingerBands


class VolatilityFeatures:
    """Extract volatility features."""

    def __init__(
        self,
        atr_period: int = 14,
        bb_period: int = 20,
    ) -> None:
        self.atr_period = atr_period
        self.bb_period = bb_period

    def compute(self, ohlcv: OHLCV) -> Dict[str, NDArray[np.float64]]:
        close = ohlcv.close
        n = len(close)
        features: Dict[str, NDArray[np.float64]] = {}

        # ATR
        atr = ATR(period=self.atr_period).calculate(ohlcv)
        features["atr"] = atr.values
        features["atr_pct"] = np.where(close > 0, atr.values / close * 100, np.nan)

        # ATR expansion
        atr_ema = np.empty(n, dtype=np.float64)
        atr_ema[:] = np.nan
        alpha = 2.0 / (self.atr_period + 1)
        for i in range(n):
            if not np.isnan(atr.values[i]):
                if i == 0 or np.isnan(atr_ema[i-1]):
                    atr_ema[i] = atr.values[i]
                else:
                    atr_ema[i] = atr.values[i] * alpha + atr_ema[i-1] * (1 - alpha)
        features["atr_expansion"] = np.where(
            atr_ema > 0, (atr.values - atr_ema) / atr_ema, np.nan
        )

        # Bollinger Bands
        bb = BollingerBands(period=self.bb_period, num_std=2.0).calculate(close)
        features["bb_upper"] = bb.upper
        features["bb_lower"] = bb.lower
        features["bb_middle"] = bb.middle
        features["bb_width"] = bb.metadata["bandwidth"]
        features["bb_percent_b"] = bb.metadata["percent_b"]

        # Bollinger squeeze
        bb_width_ma = np.empty(n, dtype=np.float64)
        bb_width_ma[:] = np.nan
        for i in range(self.bb_period - 1, n):
            window = features["bb_width"][max(0, i-self.bb_period+1):i+1]
            valid = window[~np.isnan(window)]
            if len(valid) > 0:
                bb_width_ma[i] = np.mean(valid)
        features["bb_squeeze"] = np.where(
            bb_width_ma > 0, features["bb_width"] / bb_width_ma, np.nan
        )

        # Volatility regime
        features["vol_regime"] = np.where(
            features["atr_pct"] > np.nanpercentile(features["atr_pct"], 75), 2.0,
            np.where(features["atr_pct"] > np.nanpercentile(features["atr_pct"], 25), 1.0, 0.0)
        )

        return features

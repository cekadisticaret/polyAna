"""
features/volume.py

Volume features: spike, z-score, delta, profile.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from typing import Dict

from core.base import OHLCV
from core.indicators import VWAP, OBV, CMF


class VolumeFeatures:
    """Extract volume-based features."""

    def __init__(self, lookback: int = 20) -> None:
        self.lookback = lookback

    def compute(self, ohlcv: OHLCV) -> Dict[str, NDArray[np.float64]]:
        volume = ohlcv.volume
        if volume is None:
            return {"volume_dummy": np.zeros(len(ohlcv))}

        close = ohlcv.close
        n = len(close)
        features: Dict[str, NDArray[np.float64]] = {}

        # Volume z-score
        vol_mean = np.empty(n, dtype=np.float64)
        vol_std = np.empty(n, dtype=np.float64)
        vol_mean[:] = np.nan
        vol_std[:] = np.nan

        for i in range(self.lookback - 1, n):
            window = volume[i-self.lookback+1:i+1]
            vol_mean[i] = np.mean(window)
            vol_std[i] = np.std(window)

        features["volume_zscore"] = np.where(
            vol_std > 0, (volume - vol_mean) / vol_std, np.nan
        )

        # Volume spike
        features["volume_spike"] = np.where(features["volume_zscore"] > 2.0, 1.0, 0.0)

        # Volume trend
        vol_slope = np.empty(n, dtype=np.float64)
        vol_slope[:] = np.nan
        for i in range(self.lookback, n):
            if vol_mean[i-1] > 0:
                vol_slope[i] = (vol_mean[i] - vol_mean[i-1]) / vol_mean[i-1] * 100
        features["volume_trend"] = vol_slope

        # Relative volume
        features["relative_volume"] = np.where(vol_mean > 0, volume / vol_mean, np.nan)

        # VWAP distance
        vwap = VWAP().calculate(ohlcv)
        features["vwap"] = vwap.values
        features["vwap_dist"] = np.where(
            vwap.values > 0, (close - vwap.values) / vwap.values * 100, np.nan
        )

        # OBV
        obv = OBV().calculate(ohlcv)
        features["obv"] = obv.values

        # OBV slope
        obv_slope = np.empty(n, dtype=np.float64)
        obv_slope[:] = np.nan
        for i in range(1, n):
            if not np.isnan(obv.values[i]) and not np.isnan(obv.values[i-1]) and obv.values[i-1] != 0:
                obv_slope[i] = (obv.values[i] - obv.values[i-1]) / abs(obv.values[i-1]) * 100
        features["obv_slope"] = obv_slope

        # CMF
        cmf = CMF(period=20).calculate(ohlcv)
        features["cmf"] = cmf.values

        # Delta volume
        delta = np.empty(n, dtype=np.float64)
        for i in range(n):
            if ohlcv.close[i] > ohlcv.open[i]:
                delta[i] = volume[i]
            elif ohlcv.close[i] < ohlcv.open[i]:
                delta[i] = -volume[i]
            else:
                delta[i] = 0
        features["delta_volume"] = delta

        # Cumulative delta
        features["cum_delta"] = np.cumsum(delta)

        return features

"""
features/trend.py

Trend features: EMA alignment, slope, distance, crossovers.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from typing import Dict, List

from core.base import OHLCV
from core.indicators import EMA


class TrendFeatures:
    """Extract trend-related features."""

    def __init__(self, periods: List[int] = None) -> None:
        self.periods = periods or [9, 21, 50]

    def compute(self, ohlcv: OHLCV) -> Dict[str, NDArray[np.float64]]:
        close = ohlcv.close
        n = len(close)
        features: Dict[str, NDArray[np.float64]] = {}

        # EMA values
        emas = {}
        for p in self.periods:
            ema = EMA(period=p).calculate(close).values
            emas[p] = ema
            features[f"ema_{p}"] = ema

        # EMA alignment
        if len(self.periods) >= 2:
            alignment = np.zeros(n, dtype=np.float64)
            for i in range(n):
                vals = [emas[p][i] for p in self.periods]
                if all(np.isnan(v) for v in vals):
                    alignment[i] = np.nan
                else:
                    is_asc = all(vals[j] <= vals[j+1] for j in range(len(vals)-1) if not np.isnan(vals[j]) and not np.isnan(vals[j+1]))
                    is_desc = all(vals[j] >= vals[j+1] for j in range(len(vals)-1) if not np.isnan(vals[j]) and not np.isnan(vals[j+1]))
                    if is_asc:
                        alignment[i] = 1.0
                    elif is_desc:
                        alignment[i] = -1.0
                    else:
                        alignment[i] = 0.0
            features["ema_alignment"] = alignment

        # EMA slopes
        for p in self.periods:
            ema = emas[p]
            slope = np.empty(n, dtype=np.float64)
            slope[:] = np.nan
            for i in range(1, n):
                if not np.isnan(ema[i]) and not np.isnan(ema[i-1]) and ema[i-1] != 0:
                    slope[i] = (ema[i] - ema[i-1]) / ema[i-1] * 100
            features[f"ema_{p}_slope"] = slope

        # Price distance from EMAs
        for p in self.periods:
            ema = emas[p]
            dist = np.empty(n, dtype=np.float64)
            dist[:] = np.nan
            for i in range(n):
                if not np.isnan(ema[i]) and ema[i] != 0:
                    dist[i] = (close[i] - ema[i]) / ema[i] * 100
            features[f"price_dist_ema_{p}"] = dist

        # EMA crossovers
        if len(self.periods) >= 2:
            fast = emas[self.periods[0]]
            slow = emas[self.periods[1]]
            crossover = np.zeros(n, dtype=np.float64)
            for i in range(1, n):
                if np.isnan(fast[i]) or np.isnan(slow[i]) or np.isnan(fast[i-1]) or np.isnan(slow[i-1]):
                    continue
                if fast[i-1] <= slow[i-1] and fast[i] > slow[i]:
                    crossover[i] = 1.0
                elif fast[i-1] >= slow[i-1] and fast[i] < slow[i]:
                    crossover[i] = -1.0
            features["ema_crossover"] = crossover

        return features

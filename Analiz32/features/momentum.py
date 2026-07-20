"""
features/momentum.py

Momentum features: RSI, MACD, StochRSI, WilliamsR, CCI, ROC.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from typing import Dict, Tuple

from core.base import OHLCV
from core.indicators import RSI, MACD, StochasticRSI, WilliamsR, CCI, ROC, Momentum


class MomentumFeatures:
    """Extract momentum oscillator features."""

    def __init__(
        self,
        rsi_period: int = 14,
        macd_params: Tuple[int, int, int] = (12, 26, 9),
    ) -> None:
        self.rsi_period = rsi_period
        self.macd_params = macd_params

    def compute(self, ohlcv: OHLCV) -> Dict[str, NDArray[np.float64]]:
        close = ohlcv.close
        n = len(close)
        features: Dict[str, NDArray[np.float64]] = {}

        # RSI
        rsi = RSI(period=self.rsi_period).calculate(close)
        features["rsi"] = rsi.values
        features["rsi_norm"] = (rsi.values - 50) / 50

        # MACD
        macd = MACD(*self.macd_params).calculate(close)
        features["macd"] = macd.values
        features["macd_signal"] = macd.signal
        features["macd_hist"] = macd.histogram
        features["macd_above_signal"] = np.where(
            np.isnan(macd.values) | np.isnan(macd.signal), np.nan,
            np.where(macd.values > macd.signal, 1.0, -1.0)
        )

        # MACD histogram momentum
        hist_momentum = np.empty(n, dtype=np.float64)
        hist_momentum[:] = np.nan
        for i in range(1, n):
            if not np.isnan(macd.histogram[i]) and not np.isnan(macd.histogram[i-1]):
                hist_momentum[i] = macd.histogram[i] - macd.histogram[i-1]
        features["macd_hist_momentum"] = hist_momentum

        # Stochastic RSI
        stoch = StochasticRSI().calculate(close)
        features["stoch_rsi_k"] = stoch.values
        features["stoch_rsi_d"] = stoch.signal

        # Williams %R
        williams = WilliamsR(period=14).calculate(ohlcv)
        features["williams_r"] = williams.values
        features["williams_r_norm"] = williams.values / -100

        # CCI
        cci = CCI(period=20).calculate(ohlcv)
        features["cci"] = cci.values
        features["cci_norm"] = np.clip(cci.values / 200, -1, 1)

        # ROC
        roc = ROC(period=12).calculate(close)
        features["roc"] = roc.values

        # Momentum
        mom = Momentum(period=10).calculate(close)
        features["momentum"] = mom.values

        return features

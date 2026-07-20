"""
core/indicators/volatility.py

Volatility indicators: ATR, Bollinger Bands

ATR uses Wilder smoothing (TA-Lib compatible).
Bollinger Bands use population standard deviation.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from core.base import BaseIndicator, IndicatorResult, TimeSeries, OHLCV
from core.indicators._numba_kernels import _atr_kernel, _bollinger_kernel


class ATR(BaseIndicator):
    """
    Average True Range with Wilder smoothing.

    True Range = max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close)
    )

    ATR = WilderSMMA(TR, period)

    Args:
        period: ATR period (default 14)

    Reference:
        Wilder, J. Welles. "New Concepts in Technical Trading Systems", 1978
    """

    name = "ATR"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._lookback = period + 1  # Need prev close for TR

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if not isinstance(data, OHLCV):
            raise TypeError("ATR requires OHLCV data")

        values = _atr_kernel(data.high, data.low, data.close, self.period)

        return IndicatorResult(
            values=values,
            metadata={
                "smoothing": "wilder",
                "alpha": 1.0 / self.period,
            }
        )


class BollingerBands(BaseIndicator):
    """
    Bollinger Bands — volatility bands around SMA.

    Formula:
        Middle = SMA(close, period)
        Upper = Middle + (num_std * std_dev)
        Lower = Middle - (num_std * std_dev)

    Std dev uses population standard deviation (N, not N-1).

    Args:
        period: SMA period (default 20)
        num_std: Number of standard deviations (default 2.0)

    Metadata:
        bandwidth: (Upper - Lower) / Middle
        percent_b: (Close - Lower) / (Upper - Lower)
    """

    name = "BollingerBands"

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        super().__init__(period=period)
        self.num_std = num_std
        self._lookback = period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        upper, middle, lower = _bollinger_kernel(close, self.period, self.num_std)

        # Calculate bandwidth and %B
        bandwidth = np.empty_like(close)
        percent_b = np.empty_like(close)

        for i in range(len(close)):
            if np.isnan(middle[i]) or middle[i] == 0:
                bandwidth[i] = np.nan
                percent_b[i] = np.nan
            else:
                bandwidth[i] = (upper[i] - lower[i]) / middle[i]
                if upper[i] == lower[i]:
                    percent_b[i] = 0.5
                else:
                    percent_b[i] = (close[i] - lower[i]) / (upper[i] - lower[i])

        return IndicatorResult(
            values=middle.copy(),
            upper=upper,
            lower=lower,
            middle=middle,
            metadata={
                "num_std": self.num_std,
                "bandwidth": bandwidth,
                "percent_b": percent_b,
            }
        )

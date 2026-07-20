"""
core/indicators/trend.py

Trend indicators: EMA, SMA, WMA, VWMA

All use Numba JIT kernels for performance.
EMA uses standard alpha = 2/(N+1).
SMA uses simple arithmetic mean.
WMA uses linearly weighted mean.
VWMA uses volume-weighted mean.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from core.base import BaseIndicator, IndicatorResult, TimeSeries, OHLCV
from core.indicators._numba_kernels import _ema_kernel


class EMA(BaseIndicator):
    """
    Exponential Moving Average.

    Formula:
        EMA_t = alpha * price_t + (1 - alpha) * EMA_{t-1}
        alpha = 2 / (period + 1)

    Args:
        period: EMA period (default 14)

    Example:
        >>> ema = EMA(period=20)
        >>> result = ema.calculate(close_prices)
        >>> print(f"EMA: {result.last:.2f}")
    """

    name = "EMA"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._lookback = period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        values = _ema_kernel(close, self.period)

        return IndicatorResult(
            values=values,
            middle=values.copy(),
            metadata={"alpha": 2.0 / (self.period + 1.0)}
        )


class SMA(BaseIndicator):
    """
    Simple Moving Average.

    Formula:
        SMA = sum(close[i-period+1 : i+1]) / period

    Args:
        period: SMA period (default 14)
    """

    name = "SMA"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._lookback = period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        n = len(close)
        values = np.empty(n, dtype=np.float64)
        values[:self.period - 1] = np.nan

        # Cumulative sum for efficiency
        cumsum = np.cumsum(close)
        for i in range(self.period - 1, n):
            if i == self.period - 1:
                values[i] = cumsum[i] / self.period
            else:
                values[i] = (cumsum[i] - cumsum[i - self.period]) / self.period

        return IndicatorResult(
            values=values,
            middle=values.copy(),
        )


class WMA(BaseIndicator):
    """
    Weighted Moving Average (linear weights).

    Formula:
        WMA = sum(weight[i] * close[i]) / sum(weight)
        weight[i] = i + 1 (most recent = highest weight)

    Args:
        period: WMA period (default 14)
    """

    name = "WMA"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._lookback = period
        self._weights = np.arange(1, period + 1, dtype=np.float64)
        self._weight_sum = np.sum(self._weights)

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        n = len(close)
        values = np.empty(n, dtype=np.float64)
        values[:self.period - 1] = np.nan

        for i in range(self.period - 1, n):
            window = close[i - self.period + 1 : i + 1]
            values[i] = np.sum(window * self._weights) / self._weight_sum

        return IndicatorResult(
            values=values,
            middle=values.copy(),
        )


class VWMA(BaseIndicator):
    """
    Volume-Weighted Moving Average.

    Formula:
        VWMA = sum(close * volume) / sum(volume)

    Requires OHLCV data with volume.

    Args:
        period: VWMA period (default 14)
    """

    name = "VWMA"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._lookback = period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if not isinstance(data, OHLCV):
            raise TypeError("VWMA requires OHLCV data with volume")

        if data.volume is None:
            raise ValueError("VWMA requires volume data")

        close = data.close
        volume = data.volume
        n = len(close)

        values = np.empty(n, dtype=np.float64)
        values[:self.period - 1] = np.nan

        for i in range(self.period - 1, n):
            c_window = close[i - self.period + 1 : i + 1]
            v_window = volume[i - self.period + 1 : i + 1]
            values[i] = np.sum(c_window * v_window) / np.sum(v_window)

        return IndicatorResult(
            values=values,
            middle=values.copy(),
        )

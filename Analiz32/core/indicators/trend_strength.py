"""
core/indicators/trend_strength.py

Trend strength indicators: ADX

ADX uses Wilder smoothing for +DI, -DI, and ADX itself.
TA-Lib compatible implementation.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from core.base import BaseIndicator, IndicatorResult, TimeSeries, OHLCV
from core.indicators._numba_kernels import _adx_kernel


class ADX(BaseIndicator):
    """
    Average Directional Index — trend strength indicator.

    Components:
        +DM = max(high[i] - high[i-1], 0) if up_move > down_move else 0
        -DM = max(low[i-1] - low[i], 0) if down_move > up_move else 0
        TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
        +DI = 100 * WilderSMMA(+DM) / WilderSMMA(TR)
        -DI = 100 * WilderSMMA(-DM) / WilderSMMA(TR)
        DX = 100 * abs(+DI - -DI) / (+DI + -DI)
        ADX = WilderSMMA(DX, period)

    Interpretation:
        ADX < 20: Weak or no trend
        ADX 20-40: Trend present
        ADX 40+: Strong trend

    Args:
        period: ADX period (default 14)

    Reference:
        Wilder, J. Welles. "New Concepts in Technical Trading Systems", 1978
    """

    name = "ADX"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._lookback = period * 2 + 1  # Need 2*period for valid ADX

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if not isinstance(data, OHLCV):
            raise TypeError("ADX requires OHLCV data")

        adx, plus_di, minus_di = _adx_kernel(
            data.high, data.low, data.close, self.period
        )

        return IndicatorResult(
            values=adx,
            metadata={
                "plus_di": plus_di,
                "minus_di": minus_di,
                "di_diff": np.abs(plus_di - minus_di),
                "trend_threshold": 20.0,
                "strong_trend": 40.0,
            }
        )

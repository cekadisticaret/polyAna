"""
core/indicators/volume.py

Volume-based indicators: VWAP, OBV, CMF

VWAP: Volume-Weighted Average Price (cumulative)
OBV: On-Balance Volume
CMF: Chaikin Money Flow
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from core.base import BaseIndicator, IndicatorResult, TimeSeries, OHLCV


class VWAP(BaseIndicator):
    """
    Volume-Weighted Average Price (cumulative).

    Formula:
        VWAP = cumulative(TP * Volume) / cumulative(Volume)
        TP = (High + Low + Close) / 3

    Reset period: Daily by default (can be customized).

    Args:
        anchor: Reset anchor — "D" daily, "W" weekly, "session" (default "D")

    Note:
        This implementation assumes continuous data without gaps.
        For production, pass timestamps to handle session resets.
    """

    name = "VWAP"

    def __init__(self, anchor: str = "D") -> None:
        super().__init__(period=1)  # VWAP is cumulative
        self.anchor = anchor
        self._lookback = 1

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if not isinstance(data, OHLCV):
            raise TypeError("VWAP requires OHLCV data")

        if data.volume is None:
            raise ValueError("VWAP requires volume data")

        tp = data.hlc3
        volume = data.volume
        n = len(tp)

        values = np.empty(n, dtype=np.float64)
        cum_tp_vol = 0.0
        cum_vol = 0.0

        for i in range(n):
            cum_tp_vol += tp[i] * volume[i]
            cum_vol += volume[i]

            if cum_vol == 0:
                values[i] = tp[i]
            else:
                values[i] = cum_tp_vol / cum_vol

        return IndicatorResult(
            values=values,
            middle=values.copy(),
            metadata={"anchor": self.anchor}
        )


class OBV(BaseIndicator):
    """
    On-Balance Volume — cumulative volume flow.

    Formula:
        If close[i] > close[i-1]: OBV += volume[i]
        If close[i] < close[i-1]: OBV -= volume[i]
        If close[i] == close[i-1]: OBV unchanged

    Args:
        period: SMA smoothing period (default 1, no smoothing)
    """

    name = "OBV"

    def __init__(self, period: int = 1) -> None:
        super().__init__(period=period)
        self._lookback = 2

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if not isinstance(data, OHLCV):
            raise TypeError("OBV requires OHLCV data")

        if data.volume is None:
            raise ValueError("OBV requires volume data")

        close = data.close
        volume = data.volume
        n = len(close)

        values = np.empty(n, dtype=np.float64)
        values[0] = volume[0]  # Start with first volume

        for i in range(1, n):
            if close[i] > close[i - 1]:
                values[i] = values[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                values[i] = values[i - 1] - volume[i]
            else:
                values[i] = values[i - 1]

        # Optional SMA smoothing
        if self.period > 1:
            smoothed = np.empty(n, dtype=np.float64)
            smoothed[:self.period - 1] = np.nan
            for i in range(self.period - 1, n):
                smoothed[i] = np.mean(values[i - self.period + 1 : i + 1])
            values = smoothed

        return IndicatorResult(
            values=values,
        )


class CMF(BaseIndicator):
    """
    Chaikin Money Flow — volume-weighted accumulation/distribution.

    Formula:
        MFM = ((Close - Low) - (High - Close)) / (High - Low)
        MFV = MFM * Volume
        CMF = SMA(MFV, period) / SMA(Volume, period)

    Range: -1 to +1
    Positive = accumulation, Negative = distribution

    Args:
        period: CMF period (default 20)
    """

    name = "CMF"

    def __init__(self, period: int = 20) -> None:
        super().__init__(period=period)
        self._lookback = period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if not isinstance(data, OHLCV):
            raise TypeError("CMF requires OHLCV data")

        if data.volume is None:
            raise ValueError("CMF requires volume data")

        high = data.high
        low = data.low
        close = data.close
        volume = data.volume
        n = len(close)

        # Money Flow Multiplier
        mfm = np.empty(n, dtype=np.float64)
        for i in range(n):
            hl = high[i] - low[i]
            if hl == 0:
                mfm[i] = 0.0
            else:
                mfm[i] = ((close[i] - low[i]) - (high[i] - close[i])) / hl

        # Money Flow Volume
        mfv = mfm * volume

        # CMF = SMA(MFV) / SMA(Volume)
        values = np.empty(n, dtype=np.float64)
        values[:self.period - 1] = np.nan

        for i in range(self.period - 1, n):
            mfv_window = mfv[i - self.period + 1 : i + 1]
            vol_window = volume[i - self.period + 1 : i + 1]
            vol_sum = np.sum(vol_window)

            if vol_sum == 0:
                values[i] = 0.0
            else:
                values[i] = np.sum(mfv_window) / vol_sum

        return IndicatorResult(
            values=values,
            metadata={
                "overbought": 0.1,
                "oversold": -0.1,
            }
        )

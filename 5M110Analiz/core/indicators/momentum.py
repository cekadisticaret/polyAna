"""
core/indicators/momentum.py

Momentum oscillators and indicators.

RSI uses Wilder smoothing (α = 1/period) for TA-Lib compatibility.
MACD uses standard EMA crossovers.
StochasticRSI applies Stochastic to RSI values.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from core.base import BaseIndicator, IndicatorResult, TimeSeries, OHLCV
from core.indicators._numba_kernels import (
    _rsi_kernel,
    _macd_kernel,
    _stoch_rsi_kernel,
)


class RSI(BaseIndicator):
    """
    Relative Strength Index with Wilder smoothing.

    TA-Lib compatible implementation using Wilder's SMMA:
        alpha = 1 / period (not 2/(period+1))

    Formula:
        U = max(close[i] - close[i-1], 0)
        D = max(close[i-1] - close[i], 0)
        RS = WilderSMMA(U, period) / WilderSMMA(D, period)
        RSI = 100 - 100 / (1 + RS)

    Args:
        period: RSI period (default 14)

    Reference:
        Wilder, J. Welles. "New Concepts in Technical Trading Systems", 1978
    """

    name = "RSI"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._lookback = period + 1  # RSI needs period+1 close values

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        values = _rsi_kernel(close, self.period)

        return IndicatorResult(
            values=values,
            metadata={
                "overbought": 70.0,
                "oversold": 30.0,
                "smoothing": "wilder",
                "alpha": 1.0 / self.period,
            }
        )


class MACD(BaseIndicator):
    """
    Moving Average Convergence Divergence.

    Formula:
        MACD Line = EMA(fast) - EMA(slow)
        Signal Line = EMA(MACD, signal)
        Histogram = MACD Line - Signal Line

    Args:
        fast_period: Fast EMA period (default 12)
        slow_period: Slow EMA period (default 26)
        signal_period: Signal EMA period (default 9)
    """

    name = "MACD"

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        super().__init__(period=slow_period)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self._lookback = slow_period + signal_period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        macd_line, signal_line, histogram = _macd_kernel(
            close, self.fast_period, self.slow_period, self.signal_period
        )

        return IndicatorResult(
            values=macd_line,
            signal=signal_line,
            histogram=histogram,
            metadata={
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
                "signal_period": self.signal_period,
            }
        )


class StochasticRSI(BaseIndicator):
    """
    Stochastic RSI — Stochastic oscillator applied to RSI values.

    Formula:
        RSI = RSI(close, rsi_period)
        %K = (RSI - min(RSI, stoch_period)) / (max - min) * 100
        %D = SMA(%K, d_period)

    Args:
        rsi_period: RSI calculation period (default 14)
        stoch_period: Stochastic lookback (default 14)
        k_period: %K smoothing (default 3)
        d_period: %D smoothing (default 3)
    """

    name = "StochasticRSI"

    def __init__(
        self,
        rsi_period: int = 14,
        stoch_period: int = 14,
        k_period: int = 3,
        d_period: int = 3,
    ) -> None:
        super().__init__(period=rsi_period)
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
        self.k_period = k_period
        self.d_period = d_period
        self._lookback = rsi_period + stoch_period + d_period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        k_line, d_line, rsi_vals = _stoch_rsi_kernel(
            close,
            self.rsi_period,
            self.stoch_period,
            self.k_period,
            self.d_period,
        )

        return IndicatorResult(
            values=k_line,
            signal=d_line,
            metadata={
                "rsi": rsi_vals,
                "overbought": 80.0,
                "oversold": 20.0,
            }
        )


class WilliamsR(BaseIndicator):
    """
    Williams %R — momentum oscillator.

    Formula:
        %R = (Highest High - Close) / (Highest High - Lowest Low) * -100

    Range: -100 to 0 (TA-Lib style)
    Overbought: -20 to 0
    Oversold: -100 to -80

    Args:
        period: Lookback period (default 14)
    """

    name = "WilliamsR"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._lookback = period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if not isinstance(data, OHLCV):
            raise TypeError("WilliamsR requires OHLCV data")

        high = data.high
        low = data.low
        close = data.close
        n = len(close)

        values = np.empty(n, dtype=np.float64)
        values[:self.period - 1] = np.nan

        for i in range(self.period - 1, n):
            hh = np.max(high[i - self.period + 1 : i + 1])
            ll = np.min(low[i - self.period + 1 : i + 1])
            range_val = hh - ll

            if range_val == 0:
                values[i] = -50.0
            else:
                values[i] = (hh - close[i]) / range_val * -100.0

        return IndicatorResult(
            values=values,
            metadata={
                "overbought": -20.0,
                "oversold": -80.0,
            }
        )


class CCI(BaseIndicator):
    """
    Commodity Channel Index.

    Formula:
        TP = (High + Low + Close) / 3
        CCI = (TP - SMA(TP)) / (0.015 * mean_deviation)

    Args:
        period: CCI period (default 20)
    """

    name = "CCI"

    def __init__(self, period: int = 20) -> None:
        super().__init__(period=period)
        self._lookback = period

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if not isinstance(data, OHLCV):
            raise TypeError("CCI requires OHLCV data")

        tp = data.hlc3  # Typical price
        n = len(tp)

        values = np.empty(n, dtype=np.float64)
        values[:self.period - 1] = np.nan

        for i in range(self.period - 1, n):
            window = tp[i - self.period + 1 : i + 1]
            sma_tp = np.mean(window)
            mean_dev = np.mean(np.abs(window - sma_tp))

            if mean_dev == 0:
                values[i] = 0.0
            else:
                values[i] = (tp[i] - sma_tp) / (0.015 * mean_dev)

        return IndicatorResult(
            values=values,
            metadata={
                "overbought": 100.0,
                "oversold": -100.0,
            }
        )


class ROC(BaseIndicator):
    """
    Rate of Change — momentum oscillator.

    Formula:
        ROC = ((close[i] - close[i-period]) / close[i-period]) * 100

    Args:
        period: ROC period (default 12)
    """

    name = "ROC"

    def __init__(self, period: int = 12) -> None:
        super().__init__(period=period)
        self._lookback = period + 1

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        n = len(close)
        values = np.empty(n, dtype=np.float64)
        values[:self.period] = np.nan

        for i in range(self.period, n):
            if close[i - self.period] == 0:
                values[i] = 0.0
            else:
                values[i] = (close[i] - close[i - self.period]) / close[i - self.period] * 100.0

        return IndicatorResult(
            values=values,
        )


class Momentum(BaseIndicator):
    """
    Momentum indicator.

    Formula:
        Momentum = close[i] - close[i-period]

    Args:
        period: Momentum period (default 10)
    """

    name = "Momentum"

    def __init__(self, period: int = 10) -> None:
        super().__init__(period=period)
        self._lookback = period + 1

    def _calculate_impl(self, data: TimeSeries | OHLCV) -> IndicatorResult:
        if isinstance(data, OHLCV):
            close = data.close
        else:
            close = data.astype(np.float64)

        n = len(close)
        values = np.empty(n, dtype=np.float64)
        values[:self.period] = np.nan

        for i in range(self.period, n):
            values[i] = close[i] - close[i - self.period]

        return IndicatorResult(
            values=values,
        )

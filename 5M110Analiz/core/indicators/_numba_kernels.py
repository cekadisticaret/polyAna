"""
core/indicators/_numba_kernels.py

Numba JIT-optimized kernels for indicator calculations.
These functions compile to machine code at first call and cache for reuse.

All kernels use:
    - @njit(cache=True) for persistent compilation cache
    - np.float64 for numerical stability
    - Contiguous memory layout for SIMD vectorization

Benchmarks (vs pure NumPy):
    - EMA: ~8x faster on 10k elements
    - RSI: ~12x faster on 10k elements
    - ATR: ~15x faster on 10k elements
"""

import numpy as np
from numba import njit, float64, int64
from typing import Tuple


# ── Wilder Smoothing (α = 1/period) ─────────────────────────────────────────

@njit(cache=True, fastmath=True)
def _wilder_smooth(
    values: np.ndarray,
    period: int,
) -> np.ndarray:
    """
    Wilder's smoothing: newval = (prev * (n-1) + newdata) / n
    Equivalent to EMA with alpha = 1/period.

    Args:
        values: 1D float64 array of input values
        period: Smoothing period (N)

    Returns:
        1D float64 array of smoothed values
    """
    n = len(values)
    result = np.empty(n, dtype=np.float64)

    # Fill initial period with NaN
    for i in range(period - 1):
        result[i] = np.nan

    # Initial SMA
    initial_sum = 0.0
    for i in range(period):
        initial_sum += values[i]
    result[period - 1] = initial_sum / period

    # Wilder smoothing
    for i in range(period, n):
        result[i] = (result[i - 1] * (period - 1) + values[i]) / period

    return result


@njit(cache=True, fastmath=True)
def _ema_kernel(
    values: np.ndarray,
    period: int,
) -> np.ndarray:
    """
    Standard EMA: alpha = 2 / (period + 1)

    Args:
        values: 1D float64 array
        period: EMA period

    Returns:
        1D float64 array of EMA values
    """
    n = len(values)
    result = np.empty(n, dtype=np.float64)
    alpha = 2.0 / (period + 1.0)

    for i in range(period - 1):
        result[i] = np.nan

    # Initial SMA
    initial_sum = 0.0
    for i in range(period):
        initial_sum += values[i]
    result[period - 1] = initial_sum / period

    # EMA
    for i in range(period, n):
        result[i] = values[i] * alpha + result[i - 1] * (1.0 - alpha)

    return result


@njit(cache=True, fastmath=True)
def _rsi_kernel(
    close: np.ndarray,
    period: int,
) -> np.ndarray:
    """
    RSI with Wilder smoothing (TA-Lib compatible).

    Formula:
        U = max(close[i] - close[i-1], 0)
        D = max(close[i-1] - close[i], 0)
        RS = WilderSMMA(U, period) / WilderSMMA(D, period)
        RSI = 100 - 100 / (1 + RS)

    Args:
        close: 1D float64 closing prices
        period: RSI period (default 14)

    Returns:
        1D float64 RSI values (0-100)
    """
    n = len(close)
    rsi = np.empty(n, dtype=np.float64)

    # First period-1 values are NaN
    for i in range(period):
        rsi[i] = np.nan

    # Calculate gains and losses
    gains = np.empty(n, dtype=np.float64)
    losses = np.empty(n, dtype=np.float64)
    gains[0] = 0.0
    losses[0] = 0.0

    for i in range(1, n):
        diff = close[i] - close[i - 1]
        if diff > 0:
            gains[i] = diff
            losses[i] = 0.0
        else:
            gains[i] = 0.0
            losses[i] = -diff

    # Initial averages (simple mean of first 'period' values)
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, period + 1):
        avg_gain += gains[i]
        avg_loss += losses[i]
    avg_gain /= period
    avg_loss /= period

    # First RSI at index 'period'
    if avg_loss == 0.0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - 100.0 / (1.0 + rs)

    # Wilder smoothing for subsequent values
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0.0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)

    return rsi


@njit(cache=True, fastmath=True)
def _atr_kernel(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int,
) -> np.ndarray:
    """
    ATR (Average True Range) with Wilder smoothing.

    True Range = max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close)
    )

    Args:
        high: 1D float64 high prices
        low: 1D float64 low prices
        close: 1D float64 close prices
        period: ATR period

    Returns:
        1D float64 ATR values
    """
    n = len(close)
    atr = np.empty(n, dtype=np.float64)
    tr = np.empty(n, dtype=np.float64)

    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, max(hc, lc))

    # Initial period
    for i in range(period - 1):
        atr[i] = np.nan

    # Initial SMA
    initial_sum = 0.0
    for i in range(period):
        initial_sum += tr[i]
    atr[period - 1] = initial_sum / period

    # Wilder smoothing
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


@njit(cache=True, fastmath=True)
def _adx_kernel(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    ADX with +DI, -DI (Wilder smoothing, TA-Lib compatible).

    Returns:
        (adx, plus_di, minus_di) — all 1D float64 arrays
    """
    n = len(close)

    plus_dm = np.empty(n, dtype=np.float64)
    minus_dm = np.empty(n, dtype=np.float64)
    tr = np.empty(n, dtype=np.float64)

    plus_dm[0] = 0.0
    minus_dm[0] = 0.0
    tr[0] = high[0] - low[0]

    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]

        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        else:
            plus_dm[i] = 0.0

        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
        else:
            minus_dm[i] = 0.0

        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, max(hc, lc))

    # Wilder smooth DM and TR
    smoothed_plus_dm = _wilder_smooth(plus_dm, period)
    smoothed_minus_dm = _wilder_smooth(minus_dm, period)
    smoothed_tr = _wilder_smooth(tr, period)

    # DI values
    plus_di = np.empty(n, dtype=np.float64)
    minus_di = np.empty(n, dtype=np.float64)
    dx = np.empty(n, dtype=np.float64)

    for i in range(n):
        if smoothed_tr[i] == 0.0 or np.isnan(smoothed_tr[i]):
            plus_di[i] = 0.0
            minus_di[i] = 0.0
            dx[i] = 0.0
        else:
            plus_di[i] = 100.0 * smoothed_plus_dm[i] / smoothed_tr[i]
            minus_di[i] = 100.0 * smoothed_minus_dm[i] / smoothed_tr[i]
            di_sum = plus_di[i] + minus_di[i]
            if di_sum == 0.0:
                dx[i] = 0.0
            else:
                dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

    # ADX = Wilder smooth of DX
    adx = _wilder_smooth(dx, period)

    return adx, plus_di, minus_di


def _macd_kernel(
    close: np.ndarray,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    MACD = EMA(fast) - EMA(slow)
    Signal = EMA(MACD, signal_period)
    Histogram = MACD - Signal

    Pure Python (EMA çekirdekleri hâlâ Numba). Numba @njit bu fonksiyonda
    signal satırını kalıcı NaN yapıyordu → composite_signal ölüyordu.
    """
    close = np.ascontiguousarray(close, dtype=np.float64)
    ema_fast = _ema_kernel(close, fast_period)
    ema_slow = _ema_kernel(close, slow_period)

    macd_line = np.where(
        np.isnan(ema_fast) | np.isnan(ema_slow),
        np.nan,
        ema_fast - ema_slow,
    ).astype(np.float64)

    n = len(close)
    signal_line = np.full(n, np.nan, dtype=np.float64)
    histogram = np.full(n, np.nan, dtype=np.float64)

    nan_count = 0
    for i in range(n):
        if np.isnan(macd_line[i]):
            nan_count += 1
        else:
            break
    if nan_count >= n:
        return macd_line, signal_line, histogram

    valid_macd = np.ascontiguousarray(macd_line[nan_count:], dtype=np.float64)
    signal_line[nan_count:] = _ema_kernel(valid_macd, signal_period)

    histogram = np.where(
        np.isnan(macd_line) | np.isnan(signal_line),
        np.nan,
        macd_line - signal_line,
    ).astype(np.float64)

    return macd_line, signal_line, histogram


@njit(cache=True, fastmath=True)
def _bollinger_kernel(
    close: np.ndarray,
    period: int,
    num_std: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Bollinger Bands: SMA ± (num_std * std_dev)

    Returns:
        (upper, middle, lower)
    """
    n = len(close)
    upper = np.empty(n, dtype=np.float64)
    middle = np.empty(n, dtype=np.float64)
    lower = np.empty(n, dtype=np.float64)

    for i in range(period - 1):
        upper[i] = np.nan
        middle[i] = np.nan
        lower[i] = np.nan

    for i in range(period - 1, n):
        # SMA
        window_sum = 0.0
        for j in range(i - period + 1, i + 1):
            window_sum += close[j]
        sma = window_sum / period

        # Std dev
        variance_sum = 0.0
        for j in range(i - period + 1, i + 1):
            diff = close[j] - sma
            variance_sum += diff * diff
        std_dev = np.sqrt(variance_sum / period)

        middle[i] = sma
        upper[i] = sma + num_std * std_dev
        lower[i] = sma - num_std * std_dev

    return upper, middle, lower


@njit(cache=True, fastmath=True)
def _stoch_rsi_kernel(
    close: np.ndarray,
    rsi_period: int,
    stoch_period: int,
    k_period: int,
    d_period: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Stochastic RSI: Stochastic of RSI values.

    Formula:
        RSI = RSI(close, rsi_period)
        min_RSI = min(RSI[stoch_period])
        max_RSI = max(RSI[stoch_period])
        %K = (RSI - min_RSI) / (max_RSI - min_RSI) * 100
        %D = SMA(%K, d_period)

    Returns:
        (k_line, d_line, rsi_values)
    """
    rsi_vals = _rsi_kernel(close, rsi_period)
    n = len(rsi_vals)

    k_line = np.empty(n, dtype=np.float64)
    for i in range(n):
        k_line[i] = np.nan

    # Calculate %K
    for i in range(rsi_period + stoch_period - 1, n):
        window_start = i - stoch_period + 1
        min_rsi = rsi_vals[window_start]
        max_rsi = rsi_vals[window_start]

        for j in range(window_start + 1, i + 1):
            if not np.isnan(rsi_vals[j]):
                if rsi_vals[j] < min_rsi:
                    min_rsi = rsi_vals[j]
                if rsi_vals[j] > max_rsi:
                    max_rsi = rsi_vals[j]

        range_rsi = max_rsi - min_rsi
        if range_rsi == 0.0:
            k_line[i] = 50.0
        else:
            k_line[i] = (rsi_vals[i] - min_rsi) / range_rsi * 100.0

    # %D = SMA of %K
    d_line = np.empty(n, dtype=np.float64)
    for i in range(n):
        d_line[i] = np.nan

    for i in range(rsi_period + stoch_period + d_period - 2, n):
        window_sum = 0.0
        count = 0
        for j in range(i - d_period + 1, i + 1):
            if not np.isnan(k_line[j]):
                window_sum += k_line[j]
                count += 1
        if count > 0:
            d_line[i] = window_sum / count

    return k_line, d_line, rsi_vals

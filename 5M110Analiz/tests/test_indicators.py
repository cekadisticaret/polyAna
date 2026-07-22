"""
tests/test_indicators.py

Comprehensive unit tests for all indicators.
Tests against known values and TA-Lib where applicable.

Run: pytest tests/test_indicators.py -v
"""

import numpy as np
import pytest
from typing import List, Tuple

from core.base import OHLCV
from core.indicators import (
    EMA, SMA, WMA, VWMA,
    RSI, MACD, StochasticRSI, WilliamsR, CCI, ROC, Momentum,
    ATR, BollingerBands,
    VWAP, OBV, CMF,
    ADX,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def close_prices() -> np.ndarray:
    """Sample close prices (100 bars, trending up then down)."""
    np.random.seed(42)
    trend = np.linspace(100, 150, 50)
    reversal = np.linspace(150, 120, 50)
    noise = np.random.normal(0, 2, 100)
    return np.concatenate([trend, reversal]) + noise


@pytest.fixture
def ohlcv_data() -> OHLCV:
    """Sample OHLCV data for 100 bars."""
    np.random.seed(42)
    n = 100

    close = np.linspace(100, 150, 50)
    close = np.concatenate([close, np.linspace(150, 120, 50)])
    close += np.random.normal(0, 2, n)

    # Generate realistic OHLC from close
    high = close + np.abs(np.random.normal(2, 1, n))
    low = close - np.abs(np.random.normal(2, 1, n))
    open_ = close + np.random.normal(0, 1, n)
    volume = np.random.lognormal(10, 0.5, n)

    # Ensure OHLC consistency
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    return OHLCV(open_=open_, high=high, low=low, close=close, volume=volume)


# ── Trend Indicators ────────────────────────────────────────────────────────

class TestEMA:
    """Tests for Exponential Moving Average."""

    def test_basic_calculation(self, close_prices: np.ndarray) -> None:
        ema = EMA(period=14)
        result = ema.calculate(close_prices)

        assert result.is_valid
        assert len(result.values) == len(close_prices)
        assert np.all(np.isnan(result.values[:13]))  # First 13 are NaN
        assert np.all(~np.isnan(result.values[13:]))  # Rest are valid

    def test_ema_vs_manual(self) -> None:
        """Verify EMA against manual calculation."""
        prices = np.array([100.0, 102.0, 101.0, 103.0, 105.0, 104.0, 106.0], dtype=np.float64)
        ema = EMA(period=3)
        result = ema.calculate(prices)

        # Manual EMA(3): alpha = 2/(3+1) = 0.5
        # EMA[2] = SMA([100, 102, 101]) = 101.0
        # EMA[3] = 0.5*103 + 0.5*101 = 102.0
        assert result.values[2] == pytest.approx(101.0, abs=0.01)

    def test_ema_rising_prices(self) -> None:
        """EMA should follow rising prices."""
        prices = np.arange(100, 200, dtype=np.float64)
        ema = EMA(period=10)
        result = ema.calculate(prices)

        valid = result.values[~np.isnan(result.values)]
        assert len(valid) > 0
        assert valid[-1] > valid[0]  # EMA rises with prices

    def test_insufficient_data(self) -> None:
        """Should raise error with insufficient data."""
        ema = EMA(period=20)
        with pytest.raises(ValueError, match="requires"):
            ema.calculate(np.array([1.0, 2.0, 3.0], dtype=np.float64))

    def test_streaming_update(self) -> None:
        """Test incremental update capability."""
        ema = EMA(period=5)
        prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0], dtype=np.float64)

        # Batch calculation
        batch_result = ema.calculate(prices)

        # Streaming
        ema.reset()
        for p in prices:
            ema.update(p)

        # Last values should match
        assert ema._last_result is not None
        assert ema._last_result.last == pytest.approx(batch_result.last, abs=0.01)


class TestSMA:
    """Tests for Simple Moving Average."""

    def test_sma_values(self) -> None:
        prices = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], dtype=np.float64)
        sma = SMA(period=3)
        result = sma.calculate(prices)

        # SMA[2] = (1+2+3)/3 = 2.0
        assert result.values[2] == pytest.approx(2.0, abs=0.01)
        # SMA[3] = (2+3+4)/3 = 3.0
        assert result.values[3] == pytest.approx(3.0, abs=0.01)


class TestWMA:
    """Tests for Weighted Moving Average."""

    def test_wma_weights(self) -> None:
        prices = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        wma = WMA(period=3)
        result = wma.calculate(prices)

        # WMA(3) = (1*1 + 2*2 + 3*3) / (1+2+3) = 14/6 = 2.333
        assert result.values[2] == pytest.approx(14.0/6.0, abs=0.01)


class TestVWMA:
    """Tests for Volume-Weighted Moving Average."""

    def test_vwma_requires_volume(self, ohlcv_data: OHLCV) -> None:
        vwma = VWMA(period=10)
        result = vwma.calculate(ohlcv_data)

        assert result.is_valid
        assert len(result.values) == len(ohlcv_data.close)

    def test_vwma_vs_sma(self, ohlcv_data: OHLCV) -> None:
        """VWMA should differ from SMA when volume is uneven."""
        vwma = VWMA(period=14)
        sma = SMA(period=14)

        vwma_result = vwma.calculate(ohlcv_data)
        sma_result = sma.calculate(ohlcv_data.close)

        # They should not be identical with varying volume
        vwma_valid = vwma_result.values[~np.isnan(vwma_result.values)]
        sma_valid = sma_result.values[~np.isnan(sma_result.values)]

        assert not np.allclose(vwma_valid, sma_valid, atol=0.01)


# ── Momentum Indicators ─────────────────────────────────────────────────────

class TestRSI:
    """Tests for RSI with Wilder smoothing."""

    def test_rsi_range(self, close_prices: np.ndarray) -> None:
        """RSI should be between 0 and 100."""
        rsi = RSI(period=14)
        result = rsi.calculate(close_prices)

        valid = result.values[~np.isnan(result.values)]
        assert np.all(valid >= 0)
        assert np.all(valid <= 100)

    def test_rsi_overbought_oversold(self) -> None:
        """Strong uptrend = high RSI, strong downtrend = low RSI."""
        # Strong uptrend
        uptrend = np.arange(100, 200, dtype=np.float64)
        rsi = RSI(period=14)
        result = rsi.calculate(uptrend)
        assert result.last > 70  # Overbought

        # Strong downtrend
        rsi.reset()
        downtrend = np.arange(200, 100, -1, dtype=np.float64)
        result = rsi.calculate(downtrend)
        assert result.last < 30  # Oversold

    def test_rsi_vs_talib(self) -> None:
        """Compare with TA-Lib RSI (if available)."""
        try:
            import talib
            prices = np.random.randn(100).cumsum() + 100

            our_rsi = RSI(period=14).calculate(prices).values
            talib_rsi = talib.RSI(prices, timeperiod=14)

            # Compare valid values (allow small difference)
            valid_mask = ~np.isnan(our_rsi) & ~np.isnan(talib_rsi)
            diff = np.abs(our_rsi[valid_mask] - talib_rsi[valid_mask])
            assert np.max(diff) < 1.0  # Within 1 point
        except ImportError:
            pytest.skip("TA-Lib not installed")


class TestMACD:
    """Tests for MACD."""

    def test_macd_components(self, close_prices: np.ndarray) -> None:
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        result = macd.calculate(close_prices)

        assert result.values is not None  # MACD line
        assert result.signal is not None  # Signal line
        assert result.histogram is not None  # Histogram

        # Histogram = MACD - Signal
        valid_mask = ~np.isnan(result.values) & ~np.isnan(result.signal)
        expected_hist = result.values[valid_mask] - result.signal[valid_mask]
        actual_hist = result.histogram[valid_mask]
        assert np.allclose(expected_hist, actual_hist, atol=0.01)

    def test_macd_crossover(self) -> None:
        """MACD crossover detection."""
        # Create data with clear crossover
        prices = np.concatenate([
            np.linspace(100, 80, 30),   # Downtrend
            np.linspace(80, 120, 40),   # Uptrend
        ]).astype(np.float64)

        macd = MACD(fast_period=5, slow_period=10, signal_period=3)
        result = macd.calculate(prices)

        # Find where MACD crosses above signal
        macd_line = result.values
        signal_line = result.signal

        # At some point MACD should be above signal in uptrend
        valid = ~np.isnan(macd_line) & ~np.isnan(signal_line)
        assert np.any(macd_line[valid] > signal_line[valid])


class TestStochasticRSI:
    """Tests for Stochastic RSI."""

    def test_stoch_rsi_range(self, close_prices: np.ndarray) -> None:
        stoch = StochasticRSI(rsi_period=14, stoch_period=14, k_period=3, d_period=3)
        result = stoch.calculate(close_prices)

        valid_k = result.values[~np.isnan(result.values)]
        assert np.all(valid_k >= 0)
        assert np.all(valid_k <= 100)


class TestWilliamsR:
    """Tests for Williams %R."""

    def test_williams_range(self, ohlcv_data: OHLCV) -> None:
        wr = WilliamsR(period=14)
        result = wr.calculate(ohlcv_data)

        valid = result.values[~np.isnan(result.values)]
        assert np.all(valid >= -100)
        assert np.all(valid <= 0)


class TestCCI:
    """Tests for Commodity Channel Index."""

    def test_cci_calculation(self, ohlcv_data: OHLCV) -> None:
        cci = CCI(period=20)
        result = cci.calculate(ohlcv_data)

        assert result.is_valid
        assert len(result.values) == len(ohlcv_data.close)


# ── Volatility Indicators ───────────────────────────────────────────────────

class TestATR:
    """Tests for ATR with Wilder smoothing."""

    def test_atr_positive(self, ohlcv_data: OHLCV) -> None:
        atr = ATR(period=14)
        result = atr.calculate(ohlcv_data)

        valid = result.values[~np.isnan(result.values)]
        assert np.all(valid > 0)

    def test_atr_increases_with_volatility(self) -> None:
        """Higher volatility = higher ATR."""
        np.random.seed(42)

        # Low volatility
        low_vol = np.cumsum(np.random.normal(0, 0.5, 100)) + 100
        # High volatility
        high_vol = np.cumsum(np.random.normal(0, 3.0, 100)) + 100

        # Create OHLCV
        def make_ohlcv(close):
            n = len(close)
            high = close + np.abs(np.random.normal(1, 0.5, n))
            low = close - np.abs(np.random.normal(1, 0.5, n))
            open_ = close + np.random.normal(0, 0.3, n)
            high = np.maximum(high, np.maximum(open_, close))
            low = np.minimum(low, np.minimum(open_, close))
            return OHLCV(open_=open_, high=high, low=low, close=close, 
                        volume=np.ones(n))

        atr = ATR(period=14)
        low_atr = atr.calculate(make_ohlcv(low_vol.astype(np.float64)))
        high_atr = atr.calculate(make_ohlcv(high_vol.astype(np.float64)))

        assert high_atr.last > low_atr.last


class TestBollingerBands:
    """Tests for Bollinger Bands."""

    def test_band_relationship(self, close_prices: np.ndarray) -> None:
        bb = BollingerBands(period=20, num_std=2.0)
        result = bb.calculate(close_prices)

        valid_mask = ~np.isnan(result.upper)

        # Upper > Middle > Lower
        assert np.all(result.upper[valid_mask] > result.middle[valid_mask])
        assert np.all(result.middle[valid_mask] > result.lower[valid_mask])

    def test_percent_b(self, close_prices: np.ndarray) -> None:
        bb = BollingerBands(period=20, num_std=2.0)
        result = bb.calculate(close_prices)

        percent_b = result.metadata["percent_b"]
        valid = ~np.isnan(percent_b)

        # %B should be between 0 and 1 most of the time
        assert np.all((percent_b[valid] >= 0) & (percent_b[valid] <= 1))


# ── Volume Indicators ───────────────────────────────────────────────────────

class TestVWAP:
    """Tests for VWAP."""

    def test_vwap_between_high_low(self, ohlcv_data: OHLCV) -> None:
        vwap = VWAP()
        result = vwap.calculate(ohlcv_data)

        valid = ~np.isnan(result.values)
        assert np.all(result.values[valid] >= ohlcv_data.low[valid])
        assert np.all(result.values[valid] <= ohlcv_data.high[valid])


class TestOBV:
    """Tests for On-Balance Volume."""

    def test_obv_cumulative(self, ohlcv_data: OHLCV) -> None:
        obv = OBV()
        result = obv.calculate(ohlcv_data)

        assert result.is_valid
        # OBV should be monotonic in strong trends


class TestCMF:
    """Tests for Chaikin Money Flow."""

    def test_cmf_range(self, ohlcv_data: OHLCV) -> None:
        cmf = CMF(period=20)
        result = cmf.calculate(ohlcv_data)

        valid = result.values[~np.isnan(result.values)]
        assert np.all(valid >= -1)
        assert np.all(valid <= 1)


# ── Trend Strength ──────────────────────────────────────────────────────────

class TestADX:
    """Tests for ADX."""

    def test_adx_range(self, ohlcv_data: OHLCV) -> None:
        adx = ADX(period=14)
        result = adx.calculate(ohlcv_data)

        valid = result.values[~np.isnan(result.values)]
        assert np.all(valid >= 0)
        assert np.all(valid <= 100)

    def test_adx_components(self, ohlcv_data: OHLCV) -> None:
        adx = ADX(period=14)
        result = adx.calculate(ohlcv_data)

        assert "plus_di" in result.metadata
        assert "minus_di" in result.metadata

        plus_di = result.metadata["plus_di"]
        minus_di = result.metadata["minus_di"]

        # DI values should be 0-100
        valid = ~np.isnan(plus_di)
        assert np.all(plus_di[valid] >= 0) and np.all(plus_di[valid] <= 100)
        assert np.all(minus_di[valid] >= 0) and np.all(minus_di[valid] <= 100)


# ── Performance Tests ───────────────────────────────────────────────────────

class TestPerformance:
    """Performance benchmarks for indicators."""

    @pytest.mark.parametrize("size", [1000, 10000, 100000])
    def test_ema_performance(self, size: int, benchmark) -> None:
        """Benchmark EMA calculation."""
        prices = np.random.randn(size).cumsum() + 100
        ema = EMA(period=14)
        benchmark(ema.calculate, prices.astype(np.float64))

    @pytest.mark.parametrize("size", [1000, 10000])
    def test_rsi_performance(self, size: int, benchmark) -> None:
        """Benchmark RSI calculation."""
        prices = np.random.randn(size).cumsum() + 100
        rsi = RSI(period=14)
        benchmark(rsi.calculate, prices.astype(np.float64))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

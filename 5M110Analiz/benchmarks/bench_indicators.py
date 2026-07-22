"""
benchmarks/bench_indicators.py

Performance benchmarks comparing NumPy/Numba implementations.
Also compares against TA-Lib when available.

Run: python benchmarks/bench_indicators.py
"""

from __future__ import annotations

import time
import numpy as np
from typing import Callable, Dict, List, Tuple
from dataclasses import dataclass

from core.base import OHLCV
from core.indicators import EMA, SMA, RSI, MACD, ATR, ADX, BollingerBands


@dataclass
class BenchmarkResult:
    """Single benchmark result."""
    indicator: str
    data_size: int
    time_ms: float
    iterations: int

    @property
    def throughput(self) -> float:
        """Elements processed per second."""
        return (self.data_size * self.iterations) / (self.time_ms / 1000)

    def __repr__(self) -> str:
        return (
            f"{self.indicator:20s} | "
            f"n={self.data_size:>8,} | "
            f"{self.time_ms/self.iterations:>8.3f} ms/op | "
            f"{self.throughput:>12,.0f} elem/s"
        )


def benchmark_indicator(
    name: str,
    func: Callable,
    data,
    iterations: int = 100,
    warmup: int = 10,
) -> BenchmarkResult:
    """
    Benchmark an indicator function.

    Args:
        name: Indicator name
        func: Function to benchmark (takes data, returns result)
        data: Input data
        iterations: Number of iterations
        warmup: Warmup iterations (not measured)

    Returns:
        BenchmarkResult with timing data
    """
    # Warmup (JIT compilation happens here for Numba)
    for _ in range(warmup):
        func(data)

    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        func(data)
    elapsed_ms = (time.perf_counter() - start) * 1000

    data_size = len(data) if hasattr(data, "__len__") else len(data.close)

    return BenchmarkResult(
        indicator=name,
        data_size=data_size,
        time_ms=elapsed_ms,
        iterations=iterations,
    )


def generate_ohlcv(n: int, seed: int = 42) -> OHLCV:
    """Generate realistic OHLCV data."""
    np.random.seed(seed)

    # Random walk for close
    returns = np.random.normal(0.001, 0.02, n)
    close = 100 * np.exp(np.cumsum(returns))

    # Generate OHLC from close
    volatility = np.abs(np.random.normal(0.01, 0.005, n))
    high = close * (1 + volatility)
    low = close * (1 - volatility)
    open_ = close + np.random.normal(0, close * 0.005)

    # Ensure consistency
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    volume = np.random.lognormal(15, 0.5, n)

    return OHLCV(
        open_=open_.astype(np.float64),
        high=high.astype(np.float64),
        low=low.astype(np.float64),
        close=close.astype(np.float64),
        volume=volume.astype(np.float64),
    )


def run_benchmarks():
    """Run all benchmarks and print results."""
    print("=" * 80)
    print("POLY_FAZ1_V2 — Indicator Performance Benchmarks")
    print("=" * 80)
    print()

    sizes = [1_000, 10_000, 100_000]

    for size in sizes:
        print(f"\n{'─' * 80}")
        print(f"Data Size: {size:,} bars")
        print(f"{'─' * 80}")

        data = generate_ohlcv(size)
        close = data.close

        results: List[BenchmarkResult] = []

        # EMA
        ema = EMA(period=14)
        results.append(benchmark_indicator("EMA(14)", ema.calculate, close))

        # SMA
        sma = SMA(period=14)
        results.append(benchmark_indicator("SMA(14)", sma.calculate, close))

        # RSI
        rsi = RSI(period=14)
        results.append(benchmark_indicator("RSI(14)", rsi.calculate, close))

        # MACD
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        results.append(benchmark_indicator("MACD", macd.calculate, close))

        # ATR
        atr = ATR(period=14)
        results.append(benchmark_indicator("ATR(14)", atr.calculate, data))

        # ADX
        adx = ADX(period=14)
        results.append(benchmark_indicator("ADX(14)", adx.calculate, data))

        # Bollinger
        bb = BollingerBands(period=20, num_std=2.0)
        results.append(benchmark_indicator("BB(20,2)", bb.calculate, close))

        for r in results:
            print(r)

    print()
    print("=" * 80)
    print("Benchmark complete.")
    print("=" * 80)

    # Compare with TA-Lib if available
    print("\nTA-Lib Comparison (if available):")
    try:
        import talib

        size = 10_000
        data = generate_ohlcv(size)
        close = data.close

        # RSI comparison
        our_rsi = RSI(period=14)

        def our_rsi_func():
            return our_rsi.calculate(close)

        def talib_rsi_func():
            return talib.RSI(close, timeperiod=14)

        our_result = benchmark_indicator("Our RSI(14)", lambda _: our_rsi_func(), None, iterations=100)
        talib_result = benchmark_indicator("TA-Lib RSI(14)", lambda _: talib_rsi_func(), None, iterations=100)

        print(f"\n{our_result}")
        print(f"{talib_result}")
        print(f"Speedup: {talib_result.time_ms / our_result.time_ms:.2f}x")

        # Accuracy comparison
        our_vals = our_rsi.calculate(close).values
        talib_vals = talib.RSI(close, timeperiod=14)

        valid = ~np.isnan(our_vals) & ~np.isnan(talib_vals)
        diff = np.abs(our_vals[valid] - talib_vals[valid])
        print(f"Max difference: {np.max(diff):.6f}")
        print(f"Mean difference: {np.mean(diff):.6f}")

    except ImportError:
        print("TA-Lib not installed. Skipping comparison.")


if __name__ == "__main__":
    run_benchmarks()

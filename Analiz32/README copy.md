# Poly Faz1 v2.0.0 — Production Indicator Library

## Features
- 16 technical indicators (EMA, RSI, MACD, ADX, etc.)
- NumPy vectorized + Numba JIT optimized
- TA-Lib compatible Wilder smoothing
- Comprehensive feature engine (50+ features)
- LRU cache for indicator results
- Full unit test coverage
- Performance benchmarks

## Quick Start

```python
from core.indicators import RSI, EMA, MACD
from core.base import OHLCV
from features.engine import FeatureEngine
import numpy as np

# Sample data
close = np.random.randn(100).cumsum() + 100

# Single indicator
rsi = RSI(period=14)
result = rsi.calculate(close)
print(f"RSI: {result.last:.2f}")

# Full feature vector
ohlcv = OHLCV(open_=close, high=close+1, low=close-1, close=close, volume=np.ones(100))
engine = FeatureEngine()
features = engine.compute(ohlcv)
print(f"Features: {features.n_features}")
```

## Project Structure
```
poly_faz1_v2/
├── core/
│   ├── base.py              # Base classes
│   ├── indicators/
│   │   ├── _numba_kernels.py  # JIT kernels
│   │   ├── trend.py         # EMA, SMA, WMA, VWMA
│   │   ├── momentum.py      # RSI, MACD, StochRSI, etc.
│   │   ├── volatility.py    # ATR, Bollinger
│   │   ├── volume.py        # VWAP, OBV, CMF
│   │   └── trend_strength.py # ADX
│   └── cache.py             # LRU cache
├── features/
│   ├── engine.py            # Main feature engine
│   ├── trend.py             # Trend features
│   ├── momentum.py          # Momentum features
│   ├── volatility.py      # Volatility features
│   ├── volume.py            # Volume features
│   └── composite.py         # Composite scores
├── tests/
│   └── test_indicators.py   # Unit tests
├── benchmarks/
│   └── bench_indicators.py  # Performance tests
└── requirements.txt
```

## Run Tests
```bash
pytest tests/test_indicators.py -v
```

## Run Benchmarks
```bash
python benchmarks/bench_indicators.py
```

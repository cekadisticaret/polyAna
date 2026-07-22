"""
features/__init__.py

Feature Engine v2.0.0 — Comprehensive feature extraction pipeline.

Transforms raw OHLCV data into ML-ready feature vectors.
All features are NumPy-optimized and backtest-compatible.

Modules:
    engine      — Main FeatureEngine class
    trend       — Trend features (EMA slope, distance, alignment)
    momentum    — Momentum features (RSI, MACD, StochRSI)
    volatility  — Volatility features (ATR, BB width, expansion)
    volume      — Volume features (spike, z-score, delta)
    composite   — Composite scores (trend, momentum, volatility)
"""

__version__ = "2.0.0"

from features.engine import FeatureEngine
from features.trend import TrendFeatures
from features.momentum import MomentumFeatures
from features.volatility import VolatilityFeatures
from features.volume import VolumeFeatures
from features.composite import CompositeScores

__all__ = [
    "FeatureEngine",
    "TrendFeatures",
    "MomentumFeatures",
    "VolatilityFeatures",
    "VolumeFeatures",
    "CompositeScores",
]

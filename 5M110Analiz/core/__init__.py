"""
poly_faz1_v2.core — Production Technical Indicator Library
v2.0.0 | NumPy/Numba optimized | TA-Lib compatible

Modules:
    base        — Abstract base classes and protocols
    indicators  — Wilder-based technical indicators
    cache       — LRU cache for indicator results
"""

__version__ = "2.0.0"
__author__ = "Poly Team"

from core.base import (
    IndicatorProtocol,
    BaseIndicator,
    IndicatorResult,
    TimeSeries,
)

from core.indicators import (
    EMA,
    SMA,
    WMA,
    VWMA,
    RSI,
    ATR,
    ADX,
    MACD,
    BollingerBands,
    VWAP,
    StochasticRSI,
    WilliamsR,
    CCI,
    ROC,
    Momentum,
    OBV,
    CMF,
)

__all__ = [
    "IndicatorProtocol",
    "BaseIndicator",
    "IndicatorResult",
    "TimeSeries",
    "EMA",
    "SMA",
    "WMA",
    "VWMA",
    "RSI",
    "ATR",
    "ADX",
    "MACD",
    "BollingerBands",
    "VWAP",
    "StochasticRSI",
    "WilliamsR",
    "CCI",
    "ROC",
    "Momentum",
    "OBV",
    "CMF",
]

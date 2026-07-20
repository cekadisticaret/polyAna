"""
core.indicators — Production Technical Indicators

All indicators implement Wilder smoothing and match TA-Lib output.
Optimized with NumPy vectorization and Numba JIT compilation.
"""

from core.indicators.trend import EMA, SMA, WMA, VWMA
from core.indicators.momentum import RSI, MACD, StochasticRSI, WilliamsR, CCI, ROC, Momentum
from core.indicators.volatility import ATR, BollingerBands
from core.indicators.volume import VWAP, OBV, CMF
from core.indicators.trend_strength import ADX

__all__ = [
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

"""
features/engine.py

Main FeatureEngine class — orchestrates all feature extraction.

Produces a standardized feature vector for each bar, suitable for:
- Machine learning models (XGBoost, LSTM, etc.)
- Backtesting frameworks
- Real-time streaming

Feature categories:
    - Trend: EMA alignment, slope, distance
    - Momentum: RSI, MACD, StochRSI, WilliamsR
    - Volatility: ATR, Bollinger width, expansion
    - Volume: Spike, z-score, delta, profile
    - Composite: Trend score, momentum score, regime

Example:
    >>> engine = FeatureEngine()
    >>> features = engine.compute(ohlcv_data)
    >>> print(features.shape)  # (n_bars, n_features)
    >>> print(engine.feature_names)  # List of feature names
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from core.base import OHLCV, IndicatorResult
from core.indicators import (
    EMA, SMA, RSI, MACD, StochasticRSI, WilliamsR, CCI,
    ATR, BollingerBands,
    VWAP, OBV, CMF,
    ADX,
)
from features.trend import TrendFeatures
from features.momentum import MomentumFeatures
from features.volatility import VolatilityFeatures
from features.volume import VolumeFeatures
from features.composite import CompositeScores


@dataclass
class FeatureVector:
    """
    Container for computed features.

    Attributes:
        values: (n_bars, n_features) float64 array
        names: List of feature names (columns)
        metadata: Additional computation info
    """
    values: NDArray[np.float64]
    names: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_features(self) -> int:
        return len(self.names)

    @property
    def n_bars(self) -> int:
        return len(self.values)

    def get(self, name: str) -> Optional[NDArray[np.float64]]:
        """Get a single feature by name."""
        if name in self.names:
            idx = self.names.index(name)
            return self.values[:, idx]
        return None

    def slice(self, start: int, end: int) -> "FeatureVector":
        """Return a time slice."""
        return FeatureVector(
            values=self.values[start:end],
            names=self.names.copy(),
            metadata=self.metadata.copy(),
        )

    def to_dict(self) -> Dict[str, NDArray[np.float64]]:
        """Convert to dictionary of feature arrays."""
        return {name: self.values[:, i] for i, name in enumerate(self.names)}

    def __repr__(self) -> str:
        return f"FeatureVector(bars={self.n_bars}, features={self.n_features})"


class FeatureEngine:
    """
    Comprehensive feature extraction engine.

    Computes 50+ technical features from OHLCV data.
    All features are normalized where appropriate for ML use.

    Args:
        trend_periods: List of EMA periods (default [9, 21, 50])
        rsi_period: RSI period (default 14)
        macd_params: (fast, slow, signal) tuple (default (12, 26, 9))
        atr_period: ATR period (default 14)
        bb_period: Bollinger period (default 20)
        volume_lookback: Volume normalization lookback (default 20)

    Example:
        >>> engine = FeatureEngine()
        >>> features = engine.compute(ohlcv)
        >>> 
        >>> # Use specific features
        >>> rsi_feature = features.get("rsi_14")
        >>> trend_score = features.get("trend_score")
    """

    def __init__(
        self,
        trend_periods: Optional[List[int]] = None,
        rsi_period: int = 14,
        macd_params: Tuple[int, int, int] = (12, 26, 9),
        atr_period: int = 14,
        bb_period: int = 20,
        volume_lookback: int = 20,
    ) -> None:
        self.trend_periods = trend_periods or [9, 21, 50]
        self.rsi_period = rsi_period
        self.macd_params = macd_params
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.volume_lookback = volume_lookback

        # Initialize sub-engines
        self._trend = TrendFeatures(self.trend_periods)
        self._momentum = MomentumFeatures(rsi_period, macd_params)
        self._volatility = VolatilityFeatures(atr_period, bb_period)
        self._volume = VolumeFeatures(volume_lookback)
        self._composite = CompositeScores()

        self._feature_names: List[str] = []
        self._is_fitted = False

    @property
    def feature_names(self) -> List[str]:
        """List of all feature names."""
        return self._feature_names

    def compute(self, ohlcv: OHLCV) -> FeatureVector:
        """
        Compute all features from OHLCV data.

        Args:
            ohlcv: OHLCV data container

        Returns:
            FeatureVector with (n_bars, n_features) values
        """
        n = len(ohlcv)

        # Compute sub-feature groups
        trend_features = self._trend.compute(ohlcv)
        momentum_features = self._momentum.compute(ohlcv)
        volatility_features = self._volatility.compute(ohlcv)
        volume_features = self._volume.compute(ohlcv)
        composite_features = self._composite.compute(
            ohlcv, trend_features, momentum_features, volatility_features, volume_features
        )

        # Combine all features
        all_features = []
        all_names = []

        for feat_dict in [
            trend_features,
            momentum_features,
            volatility_features,
            volume_features,
            composite_features,
        ]:
            for name, values in feat_dict.items():
                all_features.append(values)
                all_names.append(name)

        # Stack into matrix
        feature_matrix = np.column_stack(all_features)

        # Replace inf with nan
        feature_matrix = np.where(
            np.isinf(feature_matrix), np.nan, feature_matrix
        )

        self._feature_names = all_names
        self._is_fitted = True

        return FeatureVector(
            values=feature_matrix.astype(np.float64),
            names=all_names,
            metadata={
                "n_bars": n,
                "n_features": len(all_names),
                "trend_periods": self.trend_periods,
                "rsi_period": self.rsi_period,
            }
        )

    def compute_for_bar(self, ohlcv: OHLCV, bar_idx: int) -> Dict[str, float]:
        """
        Compute features for a single bar (streaming).

        Args:
            ohlcv: Full OHLCV history
            bar_idx: Index of bar to compute

        Returns:
            Dictionary of feature name -> value
        """
        features = self.compute(ohlcv)
        if bar_idx >= features.n_bars:
            raise IndexError(f"bar_idx {bar_idx} >= n_bars {features.n_bars}")

        return {
            name: float(features.values[bar_idx, i])
            for i, name in enumerate(features.names)
        }

    def get_feature_groups(self) -> Dict[str, List[str]]:
        """
        Get feature names grouped by category.

        Returns:
            Dictionary of group_name -> [feature_names]
        """
        if not self._is_fitted:
            raise RuntimeError("Must call compute() first")

        groups = {
            "trend": [],
            "momentum": [],
            "volatility": [],
            "volume": [],
            "composite": [],
        }

        for name in self._feature_names:
            if name.startswith("ema") or name.startswith("trend"):
                groups["trend"].append(name)
            elif name.startswith("rsi") or name.startswith("macd") or name.startswith("stoch"):
                groups["momentum"].append(name)
            elif name.startswith("atr") or name.startswith("bb") or name.startswith("vol"):
                groups["volatility"].append(name)
            elif name.startswith("vol") or name.startswith("obv") or name.startswith("cmf"):
                groups["volume"].append(name)
            else:
                groups["composite"].append(name)

        return groups

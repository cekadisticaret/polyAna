"""
core/base.py

Abstract base classes and type definitions for the indicator library.
All indicators inherit from BaseIndicator and implement IndicatorProtocol.

Type Aliases:
    TimeSeries = np.ndarray — 1D float64 price data
    OHLCV = dict[str, np.ndarray] — Open, High, Low, Close, Volume arrays

Example:
    >>> from core.base import BaseIndicator, IndicatorResult
    >>> class MyIndicator(BaseIndicator):
    ...     def calculate(self, data: np.ndarray) -> IndicatorResult:
    ...         ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Protocol,
    runtime_checkable,
    Any,
    Optional,
    Union,
    Dict,
    Tuple,
    List,
)
from enum import Enum, auto
import numpy as np
from numpy.typing import NDArray


# ── Type Aliases ─────────────────────────────────────────────────────────────
FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]
TimeSeries = FloatArray  # 1D price data


class OHLCV:
    """Container for OHLCV data with validation."""

    def __init__(
        self,
        open_: FloatArray,
        high: FloatArray,
        low: FloatArray,
        close: FloatArray,
        volume: Optional[FloatArray] = None,
    ) -> None:
        self.open = self._validate(open_, "open")
        self.high = self._validate(high, "high")
        self.low = self._validate(low, "low")
        self.close = self._validate(close, "close")
        self.volume = self._validate(volume, "volume") if volume is not None else None

        self._validate_ohlc()
        self._length = len(self.close)

    def _validate(self, arr: FloatArray, name: str) -> FloatArray:
        if not isinstance(arr, np.ndarray):
            raise TypeError(f"{name} must be np.ndarray, got {type(arr).__name__}")
        if arr.dtype != np.float64:
            arr = arr.astype(np.float64)
        if arr.ndim != 1:
            raise ValueError(f"{name} must be 1D, got shape {arr.shape}")
        return arr

    def _validate_ohlc(self) -> None:
        if not (len(self.open) == len(self.high) == len(self.low) == len(self.close)):
            raise ValueError("OHLC arrays must have same length")
        if np.any(self.high < self.low):
            raise ValueError("high must be >= low")
        if np.any(self.high < self.open) or np.any(self.high < self.close):
            raise ValueError("high must be >= open and close")
        if np.any(self.low > self.open) or np.any(self.low > self.close):
            raise ValueError("low must be <= open and close")

    def __len__(self) -> int:
        return self._length

    @property
    def hl2(self) -> FloatArray:
        """(High + Low) / 2"""
        return (self.high + self.low) * 0.5

    @property
    def hlc3(self) -> FloatArray:
        """(High + Low + Close) / 3"""
        return (self.high + self.low + self.close) / 3.0

    @property
    def ohlc4(self) -> FloatArray:
        """(Open + High + Low + Close) / 4"""
        return (self.open + self.high + self.low + self.close) * 0.25

    @property
    def typical(self) -> FloatArray:
        """(High + Low + Close) / 3 — alias for hlc3"""
        return self.hlc3

    def slice(self, start: int, end: int) -> "OHLCV":
        """Return a slice of the data."""
        kwargs = {
            "open_": self.open[start:end],
            "high": self.high[start:end],
            "low": self.low[start:end],
            "close": self.close[start:end],
        }
        if self.volume is not None:
            kwargs["volume"] = self.volume[start:end]
        return OHLCV(**kwargs)


class IndicatorState(Enum):
    """State of an indicator calculation."""
    UNINITIALIZED = auto()
    READY = auto()
    CALCULATING = auto()
    ERROR = auto()


@dataclass(frozen=True)
class IndicatorResult:
    """
    Immutable result container for indicator calculations.

    Attributes:
        values: Primary indicator output (e.g., RSI line)
        upper: Upper band/channel (e.g., Bollinger upper)
        lower: Lower band/channel (e.g., Bollinger lower)
        middle: Middle line (e.g., SMA or EMA line)
        signal: Signal line (e.g., MACD signal)
        histogram: Histogram/bar values (e.g., MACD histogram)
        metadata: Additional computed values (e.g., ADX components)
    """
    values: FloatArray = field(default_factory=lambda: np.array([], dtype=np.float64))
    upper: Optional[FloatArray] = None
    lower: Optional[FloatArray] = None
    middle: Optional[FloatArray] = None
    signal: Optional[FloatArray] = None
    histogram: Optional[FloatArray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Ensure all arrays are float64
        for attr in ["values", "upper", "lower", "middle", "signal", "histogram"]:
            val = getattr(self, attr)
            if val is not None and val.dtype != np.float64:
                object.__setattr__(self, attr, val.astype(np.float64))

    @property
    def last(self) -> float:
        """Last non-NaN value."""
        valid = self.values[~np.isnan(self.values)]
        return float(valid[-1]) if len(valid) > 0 else float("nan")

    @property
    def is_valid(self) -> bool:
        """Check if result has valid data."""
        return len(self.values) > 0 and not np.all(np.isnan(self.values))


@runtime_checkable
class IndicatorProtocol(Protocol):
    """Protocol that all indicators must satisfy."""

    name: str
    period: int

    def calculate(self, data: Union[TimeSeries, OHLCV]) -> IndicatorResult:
        ...

    def update(self, new_value: float) -> IndicatorResult:
        ...


class BaseIndicator(ABC):
    """
    Abstract base class for all technical indicators.

    Provides:
    - Input validation
    - Result caching (optional)
    - Streaming update capability
    - Metadata tracking

    Subclasses must implement:
        _calculate_impl(data) -> IndicatorResult
    """

    name: str = "BaseIndicator"
    period: int = 14

    def __init__(
        self,
        period: int = 14,
        cache_size: int = 0,
    ) -> None:
        self.period = max(1, period)
        self._cache_size = cache_size
        self._state = IndicatorState.UNINITIALIZED
        self._history: List[float] = []
        self._last_result: Optional[IndicatorResult] = None
        self._lookback: int = period

    @property
    def lookback(self) -> int:
        """Minimum data points required for valid calculation."""
        return self._lookback

    @property
    def state(self) -> IndicatorState:
        return self._state

    def calculate(self, data: Union[TimeSeries, OHLCV]) -> IndicatorResult:
        """
        Calculate indicator for given data.

        Args:
            data: 1D numpy array (close prices) or OHLCV object

        Returns:
            IndicatorResult with computed values

        Raises:
            ValueError: If insufficient data
        """
        self._state = IndicatorState.CALCULATING

        try:
            if isinstance(data, OHLCV):
                close = data.close
            elif isinstance(data, np.ndarray):
                close = data.astype(np.float64)
            else:
                raise TypeError(f"Expected np.ndarray or OHLCV, got {type(data).__name__}")

            if len(close) < self.lookback:
                raise ValueError(
                    f"{self.name} requires {self.lookback} data points, got {len(close)}"
                )

            result = self._calculate_impl(data)
            self._last_result = result
            self._state = IndicatorState.READY
            return result

        except Exception as e:
            self._state = IndicatorState.ERROR
            raise RuntimeError(f"{self.name} calculation failed: {e}") from e

    @abstractmethod
    def _calculate_impl(self, data: Union[TimeSeries, OHLCV]) -> IndicatorResult:
        """Implementation-specific calculation. Must be overridden."""
        ...

    def update(self, new_value: float) -> IndicatorResult:
        """
        Streaming update with new price value.
        Maintains internal history buffer.
        """
        self._history.append(float(new_value))

        # Keep enough history for lookback
        if len(self._history) > self.lookback * 2:
            self._history = self._history[-self.lookback * 2:]

        if len(self._history) >= self.lookback:
            arr = np.array(self._history, dtype=np.float64)
            return self.calculate(arr)

        # Return empty result if insufficient history
        return IndicatorResult(
            values=np.full(len(self._history), np.nan, dtype=np.float64),
            metadata={"insufficient_data": True}
        )

    def reset(self) -> None:
        """Reset indicator state."""
        self._state = IndicatorState.UNINITIALIZED
        self._history.clear()
        self._last_result = None

    def __repr__(self) -> str:
        return f"<{self.name}(period={self.period}) state={self._state.name}>"

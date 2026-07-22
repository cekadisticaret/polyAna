"""
utils/cache.py

LRU cache for indicator calculations.
Uses hash of input data + parameters for cache keys.

Features:
    - Memory-bounded LRU eviction
    - NumPy array hashing (fast)
    - Thread-safe (optional lock)
    - Cache hit/miss statistics

Example:
    >>> cache = IndicatorCache(max_size=1000)
    >>> key = cache.make_key("RSI", close_prices, {"period": 14})
    >>> result = cache.get(key)
    >>> if result is None:
    ...     result = calculate_rsi(close_prices, 14)
    ...     cache.set(key, result)
"""

from __future__ import annotations

import hashlib
import numpy as np
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class CacheStats:
    """Cache performance statistics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def total_requests(self) -> int:
        return self.hits + self.misses

    def __repr__(self) -> str:
        return f"CacheStats(hits={self.hits}, misses={self.misses}, hit_rate={self.hit_rate:.1%})"


class IndicatorCache:
    """
    LRU cache for indicator calculation results.

    Args:
        max_size: Maximum number of cached entries (default 1000)
        enable_stats: Track hit/miss statistics (default True)

    Thread Safety:
        Not thread-safe by default. Wrap with threading.Lock if needed.
    """

    def __init__(self, max_size: int = 1000, enable_stats: bool = True) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._enable_stats = enable_stats
        self._stats = CacheStats()

    @property
    def stats(self) -> CacheStats:
        """Return cache statistics."""
        return self._stats

    def make_key(
        self,
        indicator_name: str,
        data: np.ndarray,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a cache key from indicator name, data hash, and parameters.

        Uses SHA-256 of data bytes + sorted parameter string.
        """
        # Hash data (first 8 bytes of SHA-256 for speed)
        data_hash = hashlib.sha256(data.tobytes()).hexdigest()[:16]

        # Hash parameters (sorted for consistency)
        param_str = ""
        if params:
            sorted_params = sorted(params.items())
            param_str = "|".join(f"{k}={v}" for k, v in sorted_params)

        key = f"{indicator_name}:{data_hash}:{param_str}"
        return key

    def get(self, key: str) -> Optional[Any]:
        """Get cached result. Returns None if not found."""
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            if self._enable_stats:
                self._stats.hits += 1
            return self._cache[key]

        if self._enable_stats:
            self._stats.misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        """Cache a result. Evicts oldest if at capacity."""
        if key in self._cache:
            # Update existing
            self._cache.move_to_end(key)
            self._cache[key] = value
            return

        # Evict if necessary
        if len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            if self._enable_stats:
                self._stats.evictions += 1

        self._cache[key] = value

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)

    def __repr__(self) -> str:
        return f"IndicatorCache(size={len(self)}/{self._max_size}, stats={self.stats})"


# Global singleton cache (use with caution in multi-threaded environments)
_global_cache = IndicatorCache()


def get_global_cache() -> IndicatorCache:
    """Get the global indicator cache instance."""
    return _global_cache

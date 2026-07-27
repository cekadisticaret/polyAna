"""15m A8 (112) ve A3 (113) sinyal adaptörü — sanal PM trader'lar için."""
from __future__ import annotations

from typing import Callable, Optional

from analiz32_15m_adapter import Signal15m
from btc_5m_105_algo import fetch_klines_15m
from chart_hourly_signals import _a3_direction, _jesse_direction

KLINES_LIMIT = 120


def _analyze(symbol: str, direction_fn: Callable, engine: str) -> Optional[Signal15m]:
    try:
        klines = fetch_klines_15m(symbol, KLINES_LIMIT)
    except Exception as e:
        print(f"[{engine}] kline hata {symbol}: {e}")
        return None

    if not klines or len(klines) < 35:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=0.0,
            confidence=0.0, up_score=0, down_score=0,
            factors=[], htf_bias="", skip_reason="yetersiz 15m veri",
        )

    closed = klines[:-1] if len(klines) > 1 else klines
    predicted = direction_fn(closed)
    entry = float(closed[-1]["close"]) if closed else 0.0

    if predicted not in ("UP", "DOWN"):
        return Signal15m(
            symbol=symbol, direction=None, entry_price=entry,
            confidence=0.0, up_score=0, down_score=0,
            factors=[engine], htf_bias="", skip_reason="nötr",
        )

    return Signal15m(
        symbol=symbol,
        direction=predicted,
        entry_price=entry,
        confidence=0.55,
        up_score=1 if predicted == "UP" else 0,
        down_score=1 if predicted == "DOWN" else 0,
        factors=[engine],
        htf_bias=predicted,
    )


def analyze_15m_a8(symbol: str = "SOLUSDT") -> Optional[Signal15m]:
    """15M 112 — Jesse GoldenCross (A8) @ 15m."""
    return _analyze(symbol, _jesse_direction, "15M 112 A8")


def analyze_15m_a3(symbol: str = "SOLUSDT") -> Optional[Signal15m]:
    """15M 113 — Freqtrade SampleStrategy (A3) @ 15m."""
    return _analyze(symbol, _a3_direction, "15M 113 A3")

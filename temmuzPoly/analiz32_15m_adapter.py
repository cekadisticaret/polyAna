"""
15M sinyal adaptörü — 5M110Analiz FeatureEngine'i bozmadan 15m mumlara uygular.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

_DIR = os.path.dirname(os.path.abspath(__file__))
_A32 = os.path.join(os.path.dirname(_DIR), "5M110Analiz")
sys.path.insert(0, _DIR)
sys.path.insert(0, _A32)

from btc_5m_105_algo import fetch_klines_15m
from predictor import predict_from_klines

SYMBOL_DEFAULT = "SOLUSDT"
KLINES_LIMIT = 150


@dataclass
class Signal15m:
    symbol: str
    direction: Optional[str]
    entry_price: float
    confidence: float
    up_score: int
    down_score: int
    factors: list
    htf_bias: str
    skip_reason: str = ""


def analyze_15m(symbol: str = SYMBOL_DEFAULT) -> Optional[Signal15m]:
    try:
        klines = fetch_klines_15m(symbol, KLINES_LIMIT)
    except Exception as e:
        print(f"[A32-15M] kline hata {symbol}: {e}")
        return None
    if not klines or len(klines) < 80:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=0.0,
            confidence=0.0, up_score=0, down_score=0,
            factors=[], htf_bias="", skip_reason="yetersiz 15m veri",
        )

    pred = predict_from_klines(symbol, klines)
    if pred is None:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=float(klines[-2]["close"]),
            confidence=0.0, up_score=0, down_score=0,
            factors=[], htf_bias="", skip_reason="predict yok",
        )

    if not pred.predicted_dir:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=pred.current_price,
            confidence=0.0, up_score=pred.up_score, down_score=pred.down_score,
            factors=pred.factors, htf_bias=pred.htf_bias,
            skip_reason=f"gate (UP={pred.up_score} DOWN={pred.down_score})",
        )

    return Signal15m(
        symbol=symbol,
        direction=pred.predicted_dir,
        entry_price=pred.current_price,
        confidence=pred.confidence,
        up_score=pred.up_score,
        down_score=pred.down_score,
        factors=pred.factors,
        htf_bias=pred.htf_bias,
    )

"""
5M sinyal adaptörü — Analiz32 FeatureEngine'i bozmadan 5m mumlara uygular.

Analiz32/core ve features DOKUNULMAZ.
Yalnızca predictor.predict_from_klines + Binance 5m kline.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

_DIR = os.path.dirname(os.path.abspath(__file__))
_A32 = os.path.join(os.path.dirname(_DIR), "Analiz32")
sys.path.insert(0, _DIR)
sys.path.insert(0, _A32)

from btc_5m_105_algo import fetch_klines_5m
from predictor import predict_from_klines

SYMBOL_DEFAULT = "SOLUSDT"
KLINES_LIMIT = 150


@dataclass
class Signal5m:
    symbol: str
    direction: Optional[str]
    entry_price: float
    confidence: float
    up_score: int
    down_score: int
    factors: list
    htf_bias: str
    skip_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "confidence": self.confidence,
            "up_score": self.up_score,
            "down_score": self.down_score,
            "factors": self.factors,
            "htf_bias": self.htf_bias,
            "skip_reason": self.skip_reason,
        }


def analyze_5m(symbol: str = SYMBOL_DEFAULT) -> Optional[Signal5m]:
    """SOL (veya verilen sembol) için 5m FeatureEngine sinyali."""
    try:
        klines = fetch_klines_5m(symbol, KLINES_LIMIT)
    except Exception as e:
        print(f"[A32-5M] kline hata {symbol}: {e}")
        return None
    if not klines or len(klines) < 80:
        return Signal5m(
            symbol=symbol, direction=None, entry_price=0.0,
            confidence=0.0, up_score=0, down_score=0,
            factors=[], htf_bias="", skip_reason="yetersiz 5m veri",
        )

    pred = predict_from_klines(symbol, klines)
    if pred is None:
        return Signal5m(
            symbol=symbol, direction=None, entry_price=float(klines[-2]["close"]),
            confidence=0.0, up_score=0, down_score=0,
            factors=[], htf_bias="", skip_reason="predict yok",
        )

    if not pred.predicted_dir:
        return Signal5m(
            symbol=symbol, direction=None, entry_price=pred.current_price,
            confidence=0.0, up_score=pred.up_score, down_score=pred.down_score,
            factors=pred.factors, htf_bias=pred.htf_bias,
            skip_reason=f"gate (UP={pred.up_score} DOWN={pred.down_score})",
        )

    return Signal5m(
        symbol=symbol,
        direction=pred.predicted_dir,
        entry_price=pred.current_price,
        confidence=pred.confidence,
        up_score=pred.up_score,
        down_score=pred.down_score,
        factors=pred.factors,
        htf_bias=pred.htf_bias,
    )

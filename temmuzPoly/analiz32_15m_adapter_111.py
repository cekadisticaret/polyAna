# path: temmuzPoly/analiz32_15m_adapter_111.py
"""
15M sinyal adaptörü — 111 (güçlendirilmiş sürüm)
==================================================
110'un kaydettiği sinyal snapshot'ını okur; kendi kline çekmez.
5M110Analiz/predictor.py ve 5M110Analiz/features/*'a DOKUNULMAZ.
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

SCORE_GATE_111 = 15
TREND_AGREEMENT_REQUIRED = True


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
    raw_direction: Optional[str] = None


def _parse_factor(factors: list, key: str) -> float:
    prefix = key + ":"
    for f in factors or []:
        if f.startswith(prefix):
            try:
                return float(f[len(prefix):])
            except ValueError:
                return 0.0
    return 0.0


def _apply_111_filters(
    symbol: str,
    direction: Optional[str],
    entry_price: float,
    confidence: float,
    up_score: int,
    down_score: int,
    factors: list,
    htf_bias: str,
    skip_reason: str = "",
) -> Signal15m:
    if direction is None:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=entry_price,
            confidence=confidence, up_score=up_score, down_score=down_score,
            factors=factors, htf_bias=htf_bias, skip_reason=skip_reason,
        )

    composite_mag = max(up_score, down_score)
    trend = _parse_factor(factors, "trend")
    momentum = _parse_factor(factors, "momentum")

    if composite_mag < SCORE_GATE_111:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=entry_price,
            confidence=0.0, up_score=up_score, down_score=down_score,
            factors=factors, htf_bias=htf_bias,
            skip_reason=(
                f"111: skor zayıf ({composite_mag}<{SCORE_GATE_111:.0f}) "
                f"[trend:{trend:+.1f} mom:{momentum:+.1f}]"
            ),
            raw_direction=direction,
        )

    if TREND_AGREEMENT_REQUIRED:
        if direction == "UP" and trend <= 0:
            return Signal15m(
                symbol=symbol, direction=None, entry_price=entry_price,
                confidence=0.0, up_score=up_score, down_score=down_score,
                factors=factors, htf_bias=htf_bias,
                skip_reason=(
                    f"111: trend/momentum çelişkisi — UP ama trend={trend:+.1f} "
                    f"(mom:{momentum:+.1f})"
                ),
                raw_direction=direction,
            )
        if direction == "DOWN" and trend >= 0:
            return Signal15m(
                symbol=symbol, direction=None, entry_price=entry_price,
                confidence=0.0, up_score=up_score, down_score=down_score,
                factors=factors, htf_bias=htf_bias,
                skip_reason=(
                    f"111: trend/momentum çelişkisi — DOWN ama trend={trend:+.1f} "
                    f"(mom:{momentum:+.1f})"
                ),
                raw_direction=direction,
            )

    return Signal15m(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        confidence=confidence,
        up_score=up_score,
        down_score=down_score,
        factors=factors,
        htf_bias=htf_bias,
    )


def analyze_15m_from_110(symbol: str, ts_period: int) -> Optional[Signal15m]:
    """110 snapshot varsa aynı sinyal; yoksa (110 duraklamada) kendi kline + 111 filtre."""
    from analiz32_15m_signal_snapshot import load_snapshot

    base = load_snapshot(ts_period, symbol)
    if base is None:
        return analyze_15m(symbol)
    return _apply_111_filters(
        symbol=base.symbol,
        direction=base.direction,
        entry_price=base.entry_price,
        confidence=base.confidence,
        up_score=base.up_score,
        down_score=base.down_score,
        factors=base.factors,
        htf_bias=base.htf_bias,
        skip_reason=base.skip_reason,
    )


def analyze_15m(symbol: str = SYMBOL_DEFAULT) -> Optional[Signal15m]:
    """Bağımsız test / stats için; canlı 111 run() snapshot kullanır."""
    try:
        klines = fetch_klines_15m(symbol, KLINES_LIMIT)
    except Exception as e:
        print(f"[A32-15M-111] kline hata {symbol}: {e}")
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

    direction = pred.predicted_dir
    skip_reason = ""
    if not direction:
        skip_reason = f"gate (UP={pred.up_score} DOWN={pred.down_score})"

    return _apply_111_filters(
        symbol=symbol,
        direction=direction,
        entry_price=pred.current_price,
        confidence=pred.confidence if direction else 0.0,
        up_score=pred.up_score,
        down_score=pred.down_score,
        factors=pred.factors,
        htf_bias=pred.htf_bias,
        skip_reason=skip_reason,
    )

"""
Analiz31 Tahmin Motoru
"""

from dataclasses import dataclass
from typing import Optional, Dict
import time
from scorer import (
    mr_confluence_up, mr_confluence_down,
    apply_crash_gate, get_kill_zone_adjustment,
)


@dataclass
class Prediction:
    symbol: str
    current_price: float
    predicted_dir: Optional[str]
    prob_up: float
    prob_down: float
    confidence: float
    up_score: int
    down_score: int
    up_gate: int
    down_gate: int
    factors: list
    htf_bias: str
    timestamp: float


def predict(symbol: str, data: Dict) -> Optional[Prediction]:
    features = data.get("features", {})
    f1h = features.get("1h", {})

    if not f1h.get("valid"):
        return None

    up_gate, down_gate = get_kill_zone_adjustment()

    up_score, up_factors = mr_confluence_up(features)
    down_score, down_factors = mr_confluence_down(features)

    up_score, up_factors = apply_crash_gate(features, up_score, up_factors)

    predicted_dir = None
    total_score = 0

    if up_score >= up_gate or down_score >= down_gate:
        if up_score >= down_score:
            predicted_dir = "UP"
            total_score = up_score
            factors = up_factors
        else:
            predicted_dir = "DOWN"
            total_score = down_score
            factors = down_factors

    if predicted_dir:
        prob = max(0.50, min(0.90, 0.50 + total_score / 200))
        prob_up = prob if predicted_dir == "UP" else 1 - prob
        prob_down = prob if predicted_dir == "DOWN" else 1 - prob
        confidence = prob
    else:
        prob_up = prob_down = 0.0
        confidence = 0.0
        factors = up_factors + down_factors

    htf = features.get("htf_bias", {})
    htf_str = f"4h:{htf.get('4h', '?')} 1d:{htf.get('1d', '?')}"

    return Prediction(
        symbol=symbol,
        current_price=f1h.get("current", 0),
        predicted_dir=predicted_dir,
        prob_up=prob_up,
        prob_down=prob_down,
        confidence=confidence,
        up_score=up_score,
        down_score=down_score,
        up_gate=up_gate,
        down_gate=down_gate,
        factors=factors,
        htf_bias=htf_str,
        timestamp=time.time(),
    )


async def analyze(symbol: str) -> Optional[Prediction]:
    """Trader entegrasyonu — Binance verisi çekip tahmin üret."""
    from data_fetcher import fetch_all_data
    from features import extract_all_features

    raw_data = await fetch_all_data(symbol)
    if not raw_data.get("timeframes", {}).get("1h"):
        return None
    features = extract_all_features(raw_data)
    return predict(symbol, {"features": features})

"""
poly_predictor_analysis tahmin motorunu pipeline'a bağlar.

Akış:
  pipeline.py
    → run_poly_hourly_predictions()          (senkron giriş)
      → asyncio.run(_fetch_all())
        → asyncio.gather(predict(ETH), predict(SOL))   (paralel REST)
          → PolyPrediction × 2
      → _to_prediction()                     (PolyPrediction → Prediction dönüşümü)
    → dict[str, Optional[Prediction]]

Confidence eşikleri (prob_up veya prob_down):
  >= 0.65  → YÜKSEK  (pipeline'da CLOB emri açılır)
  >= 0.57  → ORTA
  else     → DÜŞÜK
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from src.analyzer.poly_predictor_analysis import PolyPrediction, predict


@dataclass
class Prediction:
    """Pipeline genelinde kullanılan tahmin nesnesi."""
    symbol:        str
    ts:            float
    current_price: float
    target_time:   str
    direction:     str       # "YUKARI" / "AŞAĞI"
    probability:   float     # 0.0 – 1.0
    confidence:    str       # "YÜKSEK" / "ORTA" / "DÜŞÜK"
    signals:       dict
    reasoning:     str
    bull_pct:      float = 0.0
    bear_pct:      float = 0.0
    h1_high:       float = 0.0
    h1_low:        float = 0.0
    key_level:     float = 0.0

logger = logging.getLogger(__name__)

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

_CONF_HIGH = 0.65
_CONF_MED  = 0.57

_IST = ZoneInfo("Europe/Istanbul")


def _to_prediction(poly: PolyPrediction) -> Prediction:
    """PolyPrediction → Prediction (pipeline uyumlu)."""
    direction = "YUKARI" if poly.predicted_dir == "UP" else "AŞAĞI"
    prob      = poly.prob_up if poly.predicted_dir == "UP" else poly.prob_down

    if prob >= _CONF_HIGH:
        confidence = "YÜKSEK"
    elif prob >= _CONF_MED:
        confidence = "ORTA"
    else:
        confidence = "DÜŞÜK"

    reasoning  = " | ".join(poly.factors[:6]) if poly.factors else ""
    target_ist = (datetime.now(_IST).hour + 1) % 24
    target_time = f"{target_ist:02d}:00 İST"

    return Prediction(
        symbol        = poly.symbol,
        ts            = poly.timestamp or time.time(),
        current_price = poly.current_price,
        target_time   = target_time,
        direction     = direction,
        probability   = prob,
        confidence    = confidence,
        signals       = {},
        reasoning     = reasoning,
        bull_pct      = round(poly.prob_up * 100),
        bear_pct      = round(poly.prob_down * 100),
        h1_high       = poly.current_price + poly.atr_1h,
        h1_low        = poly.current_price - poly.atr_1h,
        key_level     = poly.nearest_round,
    )


async def _fetch_all() -> dict[str, Optional[Prediction]]:
    results = await asyncio.gather(
        *[predict(sym) for sym in SYMBOLS],
        return_exceptions=True,
    )
    out: dict[str, Optional[Prediction]] = {}
    for sym, res in zip(SYMBOLS, results):
        if isinstance(res, BaseException):
            logger.exception("predict() hatası sym=%s: %s", sym, res)
            out[sym] = None
        elif res is None:
            logger.warning("predict() None döndü: %s", sym)
            out[sym] = None
        else:
            try:
                out[sym] = _to_prediction(res)
            except Exception:
                logger.exception("_to_prediction hatası sym=%s", sym)
                out[sym] = None
    return out


def run_poly_hourly_predictions() -> dict[str, Optional[Prediction]]:
    """Senkron giriş — pipeline / cron için."""
    return asyncio.run(_fetch_all())

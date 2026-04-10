"""
poly_predictor tahmin motoruna veri besler; `generate_prediction` burada çağrılır.
Motor kodu poly_predictor.py içinde değiştirilmez.
"""
import asyncio
import logging
from typing import Optional

from src.analyzer.poly_predictor import (
    SYMBOLS,
    Prediction,
    fetch_funding,
    fetch_klines,
    fetch_orderbook_rest,
    fetch_recent_trades_rest,
    generate_prediction,
    states,
)

logger = logging.getLogger(__name__)


async def _prepare_and_predict() -> dict[str, Optional[Prediction]]:
    """_do_prediction ile aynı veri adımları (Telegram/kayıt/emir yok)."""
    for sym in SYMBOLS:
        kl = await fetch_klines(sym)
        if kl:
            states[sym].klines_1h = kl
        states[sym].funding_rate = await fetch_funding(sym)
        if not states[sym].ob_bids:
            await fetch_orderbook_rest(sym)
        if not states[sym].ticks:
            await fetch_recent_trades_rest(sym)

    out: dict[str, Optional[Prediction]] = {}
    for sym in SYMBOLS:
        try:
            out[sym] = generate_prediction(states[sym])
        except Exception:
            logger.exception("generate_prediction hatası: %s", sym)
            out[sym] = None
    return out


def run_poly_hourly_predictions() -> dict[str, Optional[Prediction]]:
    """Senkron giriş — pipeline / cron için."""
    return asyncio.run(_prepare_and_predict())

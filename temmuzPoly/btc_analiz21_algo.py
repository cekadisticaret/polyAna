"""
21. Analiz — sembol bazlı en iyi algo sinyalleri (1H)
  BTC → Hull MA (HMA)         # algo 29
  SOL → MACD Hist. Div        # algo 26
"""
import asyncio
from dataclasses import dataclass
from typing import Optional

from algo_signals import (
    fetch_klines,
    hull_ma,
    macd_histogram_div,
)

SYMBOL_ALGOS = {
    "BTCUSDT": (hull_ma, "Hull MA (HMA)"),
    "SOLUSDT": (macd_histogram_div, "MACD Hist. Div"),
}


@dataclass
class Prediction:
    symbol: str
    predicted_dir: Optional[str]
    current_price: float
    algo_name: str
    confidence: float


async def analyze(symbol: str) -> Optional[Prediction]:
    cfg = SYMBOL_ALGOS.get(symbol)
    if not cfg:
        return None

    fn, algo_name = cfg
    try:
        kl = await asyncio.to_thread(fetch_klines, symbol, "1h", 200)
    except Exception as e:
        print(f"[analiz21] {symbol} fetch hata: {e}")
        return None

    if not kl:
        return None

    signal = fn(kl)
    if signal not in ("UP", "DOWN"):
        return Prediction(
            symbol=symbol,
            predicted_dir=None,
            current_price=kl[-1]["c"],
            algo_name=algo_name,
            confidence=0.0,
        )

    return Prediction(
        symbol=symbol,
        predicted_dir=signal,
        current_price=kl[-1]["c"],
        algo_name=algo_name,
        confidence=0.65,
    )

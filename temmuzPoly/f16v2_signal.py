"""F16V2 — BTC/SOL F16 predict() · ETH A2#03 Stochastic RSI."""
from __future__ import annotations

import asyncio

from algo_signals import fetch_klines as _algo_fetch_klines, stoch_rsi
from poly_predictor_analysis import predict

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

SYMBOL_ENGINE: dict[str, str] = {
    "BTCUSDT": "F16 predict",
    "ETHUSDT": "A2#03 Stoch RSI",
    "SOLUSDT": "F16 predict",
}


def engine_label(symbol: str) -> str:
    return SYMBOL_ENGINE.get(symbol, "?")


async def resolve_live_signal(
    symbol: str,
    hour_tr: int | None = None,
) -> tuple[str | None, float | None, str]:
    engine = engine_label(symbol)

    if symbol in ("BTCUSDT", "SOLUSDT"):
        try:
            pred = await predict(symbol)
        except Exception:
            return None, None, engine
        if pred is None:
            return None, None, engine
        price = float(getattr(pred, "current_price", 0) or 0) or None
        d = getattr(pred, "predicted_dir", None)
        if d not in ("UP", "DOWN"):
            return None, price, engine
        return d, price, engine

    if symbol != "ETHUSDT":
        return None, None, engine
    try:
        kl = await asyncio.to_thread(_algo_fetch_klines, symbol, "1h", 80)
    except Exception:
        return None, None, engine
    if len(kl) < 30:
        return None, None, engine
    price = float(kl[-1]["c"])
    sig = stoch_rsi(kl)
    if sig not in ("UP", "DOWN"):
        return None, price, engine
    return sig, price, engine

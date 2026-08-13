"""6. Analiz V3 — BTC+ETH A6 motorları, SOL A2 predictor."""
from __future__ import annotations

import asyncio

from algo_signals import fetch_klines as _algo_fetch_klines, macd_histogram_div, rsi_divergence_strict
from analiz15_signal import direction_a2

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

_SYMBOL_ENGINE = {
    "BTCUSDT": ("a6_macd", "MACD Hist. Div"),
    "ETHUSDT": ("a6_rsi", "RSI Divergence"),
    "SOLUSDT": ("a2", "Poly Predictor"),
}


def engine_label(symbol: str) -> str:
    return _SYMBOL_ENGINE.get(symbol, ("?", "?"))[1]


def _algo_klines_to_predict(kl_raw: list[dict]) -> list[dict]:
    """algo_signals {o,h,l,c,v} → A2 predictor formatı (A15 ile aynı)."""
    return [
        {
            "open_time": 0,
            "open": x["o"],
            "high": x["h"],
            "low": x["l"],
            "close": x["c"],
            "volume": x.get("v", 0),
            "taker_buy": 0,
        }
        for x in kl_raw
    ]


async def resolve_live_signal(symbol: str) -> tuple[str | None, float | None, str]:
    kind, algo_name = _SYMBOL_ENGINE.get(symbol, ("?", "?"))
    try:
        kl = await asyncio.to_thread(_algo_fetch_klines, symbol, "1h", 80)
    except Exception as e:
        print(f"[A6V3] {symbol} kline hatası: {e}")
        return None, None, algo_name
    if len(kl) < 30:
        return None, None, algo_name
    price = float(kl[-1]["c"])
    if kind == "a6_macd":
        sig = macd_histogram_div(kl)
    elif kind == "a6_rsi":
        sig = rsi_divergence_strict(kl)
    elif kind == "a2":
        sig = await direction_a2(_algo_klines_to_predict(kl), symbol)
    else:
        return None, price, algo_name
    if sig not in ("UP", "DOWN"):
        return None, price, algo_name
    return sig, price, algo_name

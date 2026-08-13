"""A2#05 X A6V3 MELEZ — sembol başına uzun dönem isabeti en yüksek motor.

Motor seçimi `algo_accuracy*.json` kayıtlarından (5 günlük defter değil, binlerce sinyal):
  BTC → MACD Hist. Div #26      %55,0 (n=487)  · mean reversion %52,5
  ETH → Mean Reversion Z-Score  %54,2 (n=201)  · RSI Div #38    %53,2
  SOL → Mean Reversion Z-Score  %53,2 (n=203)

A6V3'ün "sembol başına uzmanlaşma" yapısı korunur, ETH/SOL motorları A2#05'in
mean reversion'ı ile değiştirilir.
"""
from __future__ import annotations

import asyncio

from algo_signals import fetch_klines as _algo_fetch_klines, macd_histogram_div, mean_reversion

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

_SYMBOL_ENGINE = {
    "BTCUSDT": (macd_histogram_div, "MACD Hist. Div"),
    "ETHUSDT": (mean_reversion, "Mean Reversion Z"),
    "SOLUSDT": (mean_reversion, "Mean Reversion Z"),
}

# A6V3 ile aynı bar sayısı — MACD EMA tohumlaması birebir eşleşsin
_KLINE_LIMIT = 80


def engine_label(symbol: str) -> str:
    return _SYMBOL_ENGINE.get(symbol, (None, "?"))[1]


async def resolve_live_signal(symbol: str) -> tuple[str | None, float | None, str]:
    fn, algo_name = _SYMBOL_ENGINE.get(symbol, (None, "?"))
    if fn is None:
        return None, None, algo_name
    try:
        kl = await asyncio.to_thread(_algo_fetch_klines, symbol, "1h", _KLINE_LIMIT)
    except Exception as e:
        print(f"[MELEZ] {symbol} kline hatası: {e}")
        return None, None, algo_name
    if len(kl) < 30:
        return None, None, algo_name
    price = float(kl[-1]["c"])
    try:
        sig = fn(kl)
    except Exception as e:
        print(f"[MELEZ] {symbol} {algo_name}: {e}")
        return None, price, algo_name
    if sig not in ("UP", "DOWN"):
        return None, price, algo_name
    return sig, price, algo_name

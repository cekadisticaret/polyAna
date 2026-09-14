"""Binance Futures kline fetch — async, stdlib (+ optional aiohttp)."""
from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request


async def fetch_klines(symbol: str, tf: str = "1h", limit: int = 60) -> list[dict]:
    """Return candles with open/high/low/close keys (A2 trader uyumu)."""
    url = "https://fapi.binance.com/fapi/v1/klines?" + urllib.parse.urlencode(
        {"symbol": symbol, "interval": tf, "limit": limit}
    )

    def _sync() -> list[dict]:
        req = urllib.request.Request(url, headers={"User-Agent": "2.Poly/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        if not isinstance(data, list):
            return []
        return [
            {
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            }
            for k in data
        ]

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        print(f"[2.Poly] {symbol} kline hata: {e}")
        return []


# geriye uyum alias
_fetch_klines = fetch_klines

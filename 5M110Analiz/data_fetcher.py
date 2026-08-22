"""
Binance Futures kline çekici — trader / predictor entegrasyonu.
Mevcut indikatör/feature kütüphanesine dokunmaz.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import List

BINANCE_FAPI = "https://fapi.binance.com"


async def fetch_klines(symbol: str, interval: str, limit: int) -> List[dict]:
    """aiohttp yoksa da çalışsın diye sync urllib; async imza A31 uyumu."""
    try:
        import os
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import public_klines
        data = public_klines(symbol, interval, int(limit))
        if not isinstance(data, list):
            return []
        return [
            {
                "open_time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "taker_buy": float(k[9]),
                "close_time": int(k[6]),
            }
            for k in data
        ]
    except Exception as e:
        print(f"[FETCH32] {symbol} {interval} hata: {e}")
        return []

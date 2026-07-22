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
    params = urllib.parse.urlencode({
        "symbol": symbol, "interval": interval, "limit": limit,
    })
    url = f"{BINANCE_FAPI}/fapi/v1/klines?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "5M110Analiz/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
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

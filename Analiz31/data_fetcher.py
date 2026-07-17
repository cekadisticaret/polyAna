"""
Multi-timeframe veri çekme
"""

import asyncio
import aiohttp
from typing import Dict, List
from config import BINANCE_FAPI, TIMEFRAMES


async def fetch_klines(symbol: str, interval: str, limit: int) -> List[dict]:
    url = f"{BINANCE_FAPI}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()

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
        print(f"[FETCH] {symbol} {interval} hata: {e}")
        return []


async def fetch_all_timeframes(symbol: str) -> Dict[str, List[dict]]:
    tasks = {
        tf: fetch_klines(symbol, tf, cfg["limit"])
        for tf, cfg in TIMEFRAMES.items()
    }
    results = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results))


async def fetch_cvd(symbol: str, tf: str = "5m", limit: int = 6) -> float:
    klines = await fetch_klines(symbol, tf, limit)
    if not klines:
        return 0.0

    total_vol = sum(k["volume"] for k in klines)
    taker_buy = sum(k["taker_buy"] for k in klines)

    if total_vol == 0:
        return 0.0

    return (2 * taker_buy - total_vol) / total_vol


async def fetch_orderbook_imbalance(symbol: str) -> float:
    url = f"{BINANCE_FAPI}/fapi/v1/depth"
    params = {"symbol": symbol, "limit": 20}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json()

        bid_vol = sum(float(b[1]) for b in data["bids"])
        ask_vol = sum(float(a[1]) for a in data["asks"])
        total = bid_vol + ask_vol

        return bid_vol / total if total > 0 else 0.5
    except Exception:
        return 0.5


async def fetch_all_data(symbol: str) -> Dict:
    tf_data = await fetch_all_timeframes(symbol)
    cvd_5m, cvd_30m, ob = await asyncio.gather(
        fetch_cvd(symbol, "5m", 6),
        fetch_cvd(symbol, "30m", 2),
        fetch_orderbook_imbalance(symbol),
    )

    return {
        "timeframes": tf_data,
        "cvd_5m": cvd_5m,
        "cvd_30m": cvd_30m,
        "orderbook": ob,
    }

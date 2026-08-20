"""Bybit TradFi altın — public V5 market data. Anahtar yok. CEM01'e dokunmaz.

Sembol: XAUUSDT (linear · commodity). UI'daki XAUUSD+ bu kontrat.
https://bybit-exchange.github.io/docs/v5/market/tickers
https://bybit-exchange.github.io/docs/v5/market/kline
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

_BASE = "https://api.bybit.com"
_SYMBOL = "XAUUSDT"
_UA = {"User-Agent": "Mozilla/5.0"}
_IV = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}

_kline_cache: dict[tuple, tuple[float, list]] = {}
_ticker_cache: tuple[float, dict] | None = None
_KLINE_TTL = 6.0
_TICKER_TTL = 2.0


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def ticker(force: bool = False) -> dict:
    """last / bid / ask / 24s H-L. 2 sn önbellek; force=True anlık doldurma."""
    global _ticker_cache
    now = time.time()
    if not force and _ticker_cache and now - _ticker_cache[0] < _TICKER_TTL:
        return dict(_ticker_cache[1])
    data = _get_json(
        f"{_BASE}/v5/market/tickers?category=linear&symbol={_SYMBOL}"
    )
    if int(data.get("retCode", 1)) != 0:
        raise RuntimeError(str(data.get("retMsg") or "bybit_ticker")[:160])
    row = ((data.get("result") or {}).get("list") or [None])[0]
    if not row:
        raise RuntimeError("bybit_ticker_empty")
    last = float(row["lastPrice"])
    bid = float(row.get("bid1Price") or last)
    ask = float(row.get("ask1Price") or last)
    if ask < bid:
        bid, ask = ask, bid
    out = {
        "symbol": _SYMBOL,
        "last": last,
        "bid": bid,
        "ask": ask,
        "mark": float(row.get("markPrice") or last),
        "day_high": float(row["highPrice24h"]) if row.get("highPrice24h") else None,
        "day_low": float(row["lowPrice24h"]) if row.get("lowPrice24h") else None,
        "src": "bybit",
    }
    _ticker_cache = (now, out)
    return dict(out)


def klines(tf: str = "1m", limit: int = 240) -> list[dict]:
    """OHLCV, eski→yeni, time saniye. Yahoo'ya düşmez."""
    if tf not in _IV:
        tf = "1m"
    n = max(20, min(1000, int(limit)))
    key = (tf, n)
    now = time.time()
    hit = _kline_cache.get(key)
    if hit and now - hit[0] < _KLINE_TTL:
        return list(hit[1])
    data = _get_json(
        f"{_BASE}/v5/market/kline?category=linear&symbol={_SYMBOL}"
        f"&interval={_IV[tf]}&limit={n}"
    )
    if int(data.get("retCode", 1)) != 0:
        raise RuntimeError(str(data.get("retMsg") or "bybit_kline")[:160])
    raw = list((data.get("result") or {}).get("list") or [])
    raw.reverse()
    rows = []
    for k in raw:
        try:
            rows.append({
                "time": int(k[0]) // 1000,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5] or 0),
            })
        except (TypeError, ValueError, IndexError):
            continue
    if rows:
        _kline_cache[key] = (now, rows)
    return list(rows)

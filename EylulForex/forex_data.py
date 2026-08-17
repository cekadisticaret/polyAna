"""XAUUSD — Yahoo GC=F mum + bid/ask kotasyonu (forex terminal)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0"}
_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
_BINANCE_SPOT = "https://api.binance.com"
_PAXG = "PAXGUSDT"
_DEFAULT_SPREAD = 0.30  # tipik XAUUSD spread ($)

# Yahoo interval + range
_YF = {
    "1m": ("1m", "1d", 240),
    "5m": ("5m", "5d", 200),
    "15m": ("15m", "5d", 180),
    "30m": ("30m", "1mo", 160),
    "1h": ("1h", "1mo", 180),
    "4h": ("1h", "3mo", 180),  # 1h çekilip 4h'ye toplanır
    "1d": ("1d", "1y", 220),
}
_BAR_SEC = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}

_cache: dict[tuple, tuple[float, list]] = {}
_CACHE_TTL = 6.0
_quote_cache: tuple[float, dict] | None = None


def _get_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _yahoo_raw(interval: str, range_: str) -> tuple[list[dict], dict]:
    data = _get_json(f"{_YAHOO}?interval={interval}&range={range_}")
    res = (data.get("chart") or {}).get("result") or []
    if not res:
        return [], {}
    row = res[0]
    meta = row.get("meta") or {}
    ts = row.get("timestamp") or []
    q = ((row.get("indicators") or {}).get("quote") or [{}])[0]
    out = []
    for t, o, h, l, c, v in zip(
        ts, q.get("open") or [], q.get("high") or [],
        q.get("low") or [], q.get("close") or [], q.get("volume") or [],
    ):
        if o is None or h is None or l is None or c is None:
            continue
        out.append({
            "time": int(t),
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": float(v or 0),
        })
    return out, meta


def _paxg_klines(interval: str, limit: int) -> list[dict]:
    bn_iv = {"4h": "4h", "1d": "1d"}.get(interval, interval)
    if bn_iv not in ("1m", "5m", "15m", "30m", "1h", "4h", "1d"):
        bn_iv = "1m"
    data = _get_json(
        f"{_BINANCE_SPOT}/api/v3/klines?symbol={_PAXG}&interval={bn_iv}&limit={limit}"
    )
    return [
        {
            "time": int(k[0]) // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in data
    ]


def _resample_4h(rows: list[dict]) -> list[dict]:
    buckets: dict[int, dict] = {}
    for c in rows:
        t0 = c["time"] - (c["time"] % 14400)
        b = buckets.get(t0)
        if not b:
            buckets[t0] = {
                "time": t0, "open": c["open"], "high": c["high"],
                "low": c["low"], "close": c["close"], "volume": c["volume"],
            }
        else:
            b["high"] = max(b["high"], c["high"])
            b["low"] = min(b["low"], c["low"])
            b["close"] = c["close"]
            b["volume"] += c["volume"]
    return [buckets[k] for k in sorted(buckets)]


def get_xau_klines(tf: str = "1m", limit: int = 200) -> tuple[list[dict], str]:
    if tf not in _YF:
        tf = "1m"
    n = max(20, min(500, int(limit)))
    key = (tf, n)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1], "cache"
    iv, rg, default_n = _YF[tf]
    try:
        rows, _meta = _yahoo_raw(iv, rg)
        if tf == "4h":
            rows = _resample_4h(rows)
        rows = rows[-n:]
        if rows:
            _cache[key] = (now, rows)
            return rows, "yahoo_gc"
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    rows = _paxg_klines(tf, n)
    _cache[key] = (now, rows)
    return rows, "paxg"


def _paxg_spread() -> float | None:
    try:
        data = _get_json(f"{_BINANCE_SPOT}/api/v3/ticker/bookTicker?symbol={_PAXG}")
        bid, ask = float(data["bidPrice"]), float(data["askPrice"])
        if ask > bid > 0:
            return ask - bid
    except Exception:
        return None
    return None


def forex_quote() -> dict:
    """Bid / ask / mid + günlük H/L."""
    global _quote_cache
    now = time.time()
    if _quote_cache and now - _quote_cache[0] < 2.0:
        return dict(_quote_cache[1])
    mid = day_hi = day_lo = None
    try:
        rows, meta = _yahoo_raw("1m", "1d")
        px = meta.get("regularMarketPrice")
        mid = float(px) if px is not None else None
        day_hi = meta.get("regularMarketDayHigh")
        day_lo = meta.get("regularMarketDayLow")
        if mid is None and rows:
            mid = rows[-1]["close"]
    except Exception:
        pass
    if mid is None:
        try:
            data = _get_json(f"{_BINANCE_SPOT}/api/v3/ticker/price?symbol={_PAXG}")
            mid = float(data["price"])
        except Exception:
            mid = None
    raw = _paxg_spread()
    spr = float(raw) if raw and raw >= 0.20 else _DEFAULT_SPREAD
    spr = max(0.20, min(2.0, spr))
    dec = 2
    bid = ask = None
    if mid is not None:
        bid = round(mid - spr / 2, dec)
        ask = round(mid + spr / 2, dec)
        mid = round(mid, dec)
    out = {
        "symbol": "XAUUSD",
        "name": "Altın / Dolar",
        "dec": dec,
        "mid": mid,
        "bid": bid,
        "ask": ask,
        "spread": round(spr, 2),
        "day_high": round(float(day_hi), dec) if day_hi is not None else None,
        "day_low": round(float(day_lo), dec) if day_lo is not None else None,
        "live_price": mid,
    }
    _quote_cache = (now, out)
    return dict(out)


def bar_remaining(tf: str) -> int:
    sec = _BAR_SEC.get(tf, 60)
    now = int(time.time())
    return sec - (now % sec)


def forex_spot(timeframe: str = "1m") -> dict:
    """Eski imza — kotasyon + mum kalan süre."""
    tf = timeframe if timeframe in _YF else "1m"
    q = forex_quote()
    q["timeframe"] = tf
    q["bar_sec"] = _BAR_SEC[tf]
    q["bar_left"] = bar_remaining(tf)
    return q


def forex_chart(timeframe: str = "1m", price_tf: str | None = None, limit: int | None = None) -> dict:
    tf = (price_tf or timeframe or "1m").lower()
    if tf not in _YF:
        tf = "1m"
    n = _YF[tf][2]
    if limit is not None:
        n = max(20, min(500, int(limit)))
    rows, src = get_xau_klines(tf, n)
    q = forex_quote()
    dec = 2
    candles = [
        {
            "time": c["time"],
            "open": round(c["open"], dec),
            "high": round(c["high"], dec),
            "low": round(c["low"], dec),
            "close": round(c["close"], dec),
            "volume": round(c["volume"], 2),
        }
        for c in rows
    ]
    out = {
        "symbol": "XAUUSD",
        "name": "XAUUSD",
        "timeframe": tf,
        "price_tf": tf,
        "dec": dec,
        "candles": candles,
        "source": src,
        "bar_sec": _BAR_SEC[tf],
        "bar_left": bar_remaining(tf),
        **{k: q[k] for k in ("mid", "bid", "ask", "spread", "day_high", "day_low", "live_price")},
    }
    try:
        from forex_signal import overlay_signals
        sig, marks = overlay_signals(tf, candles)
        out["signal"] = sig
        out["signal_markers"] = marks
    except Exception as e:
        out["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "error": str(e)[:160],
        }
        out["signal_markers"] = []
    return out

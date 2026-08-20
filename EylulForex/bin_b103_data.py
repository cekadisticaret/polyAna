"""BIN_B1#03 — Binance XAUUSDT mum/kotasyon. GPSUSDT / CEM01 dokunulmaz.

Sinyal mumu `forex_data.get_xau_klines` (algoritma-islemler/b1_mum ile aynı).
Grafik ve dolum kotasyonu XAUUSDT fapi.
"""
from __future__ import annotations

import json
import time
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0"}
_SPOT = "https://api.binance.com"
_FAPI = "https://fapi.binance.com"
SYMBOL = "XAUUSDT"
_BAR_SEC = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}
_cache: dict[tuple, tuple[float, object]] = {}
_TTL = 8.0


def _get_json(url: str):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def bar_remaining(tf: str) -> int:
    sec = _BAR_SEC.get(tf, 60)
    now = int(time.time())
    return max(0, sec - (now % sec))


def _klines_raw(tf: str, limit: int) -> tuple[list[dict], str]:
    iv = tf if tf in _BAR_SEC else "1m"
    lim = max(20, min(int(limit or 240), 500))
    last_err = "yok"
    for src, url in (
        ("fapi", f"{_FAPI}/fapi/v1/klines?symbol={SYMBOL}&interval={iv}&limit={lim}"),
        ("spot", f"{_SPOT}/api/v3/klines?symbol={SYMBOL}&interval={iv}&limit={lim}"),
    ):
        try:
            rows = _get_json(url)
            if not isinstance(rows, list) or not rows:
                continue
            out = []
            for r in rows:
                out.append({
                    "time": int(r[0]) // 1000,
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5] or 0),
                })
            return out, src
        except Exception as e:
            last_err = str(e)[:160]
    raise RuntimeError(last_err)


def xau_klines(tf: str, n: int = 120) -> list[dict]:
    key = ("kl", tf, int(n))
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL:
        return list(hit[1])
    rows, _ = _klines_raw(tf, n)
    _cache[key] = (now, rows)
    return list(rows)


def signal_klines(tf: str, n: int = 180) -> list[dict]:
    """Algoritma-islemler/b1_mum ile aynı XAU beslemesi."""
    from forex_data import get_xau_klines
    rows, _src = get_xau_klines(tf, n)
    return rows or []


def _ticker() -> tuple[dict, str]:
    last_err = "yok"
    for src, url in (
        ("fapi", f"{_FAPI}/fapi/v1/ticker/bookTicker?symbol={SYMBOL}"),
        ("spot", f"{_SPOT}/api/v3/ticker/bookTicker?symbol={SYMBOL}"),
    ):
        try:
            d = _get_json(url)
            if isinstance(d, dict) and (d.get("bidPrice") or d.get("askPrice")):
                return d, src
        except Exception as e:
            last_err = str(e)[:160]
    raise RuntimeError(last_err)


def live_quote() -> dict:
    d, src = _ticker()
    bid = float(d.get("bidPrice") or 0)
    ask = float(d.get("askPrice") or 0)
    mid = (bid + ask) / 2.0 if bid and ask else (bid or ask)
    dec = 2
    mark = None
    funding = None
    try:
        from bin_b103_binance import premium
        pr = premium()
        mark = pr.get("mark")
        funding = pr.get("last_funding_rate")
    except Exception:
        pass
    return {
        "ok": True,
        "symbol": SYMBOL,
        "name": "XAU / USDT",
        "bid": round(bid, dec) if bid else None,
        "ask": round(ask, dec) if ask else None,
        "mid": round(mid, dec) if mid else None,
        "dec": dec,
        "mark": round(mark, dec) if mark else None,
        "funding_rate": funding,
        "spread": round(ask - bid, dec) if bid and ask else None,
        "live_price": round(mid, dec) if mid else None,
        "src": src,
        "venue": "binance_usdm",
        "stale_sec": 0,
    }


def live_signal_now() -> dict:
    kl1 = signal_klines("1h", 180)
    kl4 = signal_klines("4h", 120)
    from bin_b103_signal import resolve
    return resolve(kl1, kl4)


def live_spot(timeframe: str = "1m") -> dict:
    tf = timeframe if timeframe in _BAR_SEC else "1m"
    q = live_quote()
    q["timeframe"] = tf
    q["bar_sec"] = _BAR_SEC[tf]
    q["bar_left"] = bar_remaining(tf)
    q["signal_tf"] = "1h"
    q["level_tf"] = "1h"
    try:
        q["signal"] = live_signal_now()
    except Exception as e:
        q["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "engine": "b1_mum", "error": str(e)[:160],
        }
    q["rail"] = {}
    try:
        from bin_b103_book import snapshot
        q["book"] = snapshot(q.get("bid"), q.get("ask"))
    except Exception as e:
        q["book"] = {"ok": False, "error": str(e)[:160]}
    return q


def live_chart(timeframe: str = "1m", limit: int = 240) -> dict:
    tf = timeframe if timeframe in _BAR_SEC else "1m"
    n = max(20, min(int(limit or 240), 500))
    try:
        rows = xau_klines(tf, n)
        q = live_quote()
    except Exception as e:
        return {
            "ok": False, "symbol": SYMBOL, "name": "XAU / USDT",
            "timeframe": tf, "algo": "binb103", "error": str(e)[:200],
            "candles": [], "bid": None, "ask": None, "mid": None,
        }
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
    day = [c for c in candles if time.time() - c["time"] <= 86400] or candles
    hi = max(c["high"] for c in day) if day else None
    lo = min(c["low"] for c in day) if day else None
    out = {
        "ok": True,
        "symbol": SYMBOL,
        "name": "XAU / USDT",
        "timeframe": tf,
        "price_tf": tf,
        "dec": dec,
        "candles": candles,
        "source": q.get("src") or "binance",
        "bar_sec": _BAR_SEC[tf],
        "bar_left": bar_remaining(tf),
        "algo": "binb103",
        "day_high": round(hi, dec) if hi else None,
        "day_low": round(lo, dec) if lo else None,
        **{k: q[k] for k in ("mid", "bid", "ask", "spread", "live_price")},
    }
    try:
        out["signal"] = live_signal_now()
    except Exception as e:
        out["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "engine": "b1_mum", "error": str(e)[:160],
        }
    out["signal_markers"] = []
    out["rail"] = {}
    out["levels"] = {}
    try:
        from bin_b103_book import snapshot
        out["book"] = snapshot(out.get("bid"), out.get("ask"))
    except Exception:
        out["book"] = None
    return out

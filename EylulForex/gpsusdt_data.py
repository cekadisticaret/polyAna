"""GPSUSDT — Binance USDT-M mum + kotasyon. Spot yedek.

CEM01 dosyalarına dokunmaz.
"""
from __future__ import annotations

import json
import time
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0"}
_SPOT = "https://api.binance.com"
_FAPI = "https://fapi.binance.com"
SYMBOL = "GPSUSDT"
BOOK_SIGNAL_TF = "1m"
BOOK_LEVEL_TF = "5m"
_BAR_SEC = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}
_cache: dict[tuple, tuple[float, object]] = {}
_TTL = 8.0
_TICK_TTL = 2.0
_tick_cache: tuple[float, dict] | None = None


def _get_json(url: str):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _dec(px: float) -> int:
    if px >= 1:
        return 4
    if px >= 0.1:
        return 5
    return 6


def _fapi_ok() -> bool:
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import fapi_ok
        return bool(fapi_ok())
    except Exception:
        return True


def _klines_raw(tf: str, limit: int) -> tuple[list[dict], str]:
    iv = tf if tf in _BAR_SEC else "1m"
    lim = max(20, min(int(limit or 240), 500))
    last_err = "yok"
    sources = []
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import public_klines
        raw = public_klines(SYMBOL, iv, lim)
        if isinstance(raw, list) and raw:
            out = []
            for r in raw:
                out.append({
                    "time": int(r[0]) // 1000,
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5] or 0),
                })
            return out, "public"
    except Exception as e:
        last_err = str(e)[:160]
    sources.append(("spot", f"{_SPOT}/api/v3/klines?symbol={SYMBOL}&interval={iv}&limit={lim}"))
    for src, url in sources:
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


def gps_klines(tf: str, n: int = 120) -> list[dict]:
    key = ("kl", tf, int(n))
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL:
        return list(hit[1])
    rows, _ = _klines_raw(tf, n)
    _cache[key] = (now, rows)
    return list(rows)


def _ticker() -> tuple[dict, str]:
    last_err = "yok"
    sources = []
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import get_book
        hit = get_book(SYMBOL)
        if hit and (hit.get("bid") or hit.get("ask")):
            return {
                "bidPrice": hit.get("bid"),
                "askPrice": hit.get("ask"),
                "bidQty": hit.get("bid_qty"),
                "askQty": hit.get("ask_qty"),
            }, "ws"
    except Exception:
        pass
    sources.append(("spot", f"{_SPOT}/api/v3/ticker/bookTicker?symbol={SYMBOL}"))
    for src, url in sources:
        try:
            d = _get_json(url)
            if isinstance(d, dict) and (d.get("bidPrice") or d.get("askPrice")):
                return d, src
        except Exception as e:
            last_err = str(e)[:160]
    raise RuntimeError(last_err)


def gps_tick_score(window_sec: int = 90, limit: int = 500) -> dict:
    """Binance aggTrade dengesizliği — CEM01 PAXG tick'in GPS karşılığı."""
    global _tick_cache
    now = time.time()
    if _tick_cache and now - _tick_cache[0] < _TICK_TTL:
        return dict(_tick_cache[1])
    start = int((now - window_sec) * 1000)
    data = []
    try:
        data = _get_json(
            f"{_SPOT}/api/v3/aggTrades?symbol={SYMBOL}&startTime={start}&limit={limit}"
        )
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    buy = sell = 0.0
    for t in data:
        qty = float(t.get("q") or 0)
        if t.get("m"):
            sell += qty
        else:
            buy += qty
    tot = buy + sell
    score = 0.0 if tot <= 0 else (buy - sell) / tot * 100.0
    out = {"score": round(score, 2), "n": len(data), "buy": buy, "sell": sell}
    _tick_cache = (now, out)
    return dict(out)


def bar_remaining(tf: str) -> int:
    sec = _BAR_SEC.get(tf, 60)
    now = int(time.time())
    return sec - (now % sec)


def _spot_book() -> dict:
    d = _get_json(f"{_SPOT}/api/v3/ticker/bookTicker?symbol={SYMBOL}")
    bid = float(d.get("bidPrice") or 0)
    ask = float(d.get("askPrice") or 0)
    last = float(d.get("lastPrice") or 0)
    if not last:
        try:
            p = _get_json(f"{_SPOT}/api/v3/ticker/price?symbol={SYMBOL}")
            last = float(p.get("price") or 0)
        except Exception:
            last = (bid + ask) / 2 if bid and ask else (bid or ask)
    return {"bid": bid, "ask": ask, "last": last}


def gps_quote() -> dict:
    tick, src = _ticker()
    bid = float(tick.get("bidPrice") or 0)
    ask = float(tick.get("askPrice") or 0)
    mid = (bid + ask) / 2 if bid and ask else (bid or ask)
    dec = _dec(mid or 1)
    mark = funding = last = None
    try:
        from gpsusdt_binance import premium
        p = premium()
        mark = p.get("mark")
        funding = p.get("last_funding_rate")
    except Exception:
        pass
    try:
        import sys
        from pathlib import Path
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import get_last, get_mark
        last = get_last(SYMBOL) or get_mark(SYMBOL)
    except Exception:
        last = None
    if not last:
        last = mark or mid
    spot = {}
    try:
        spot = _spot_book()
    except Exception:
        spot = {}
    live = last or mark or mid
    return {
        "symbol": SYMBOL,
        "name": "GPS / USDT",
        "algo": "gps",
        "dec": dec,
        "mid": round(mid, dec) if mid else None,
        "bid": round(bid, dec) if bid else None,
        "ask": round(ask, dec) if ask else None,
        "mark": round(mark, dec) if mark else None,
        "last": round(last, dec) if last else None,
        "funding_rate": funding,
        "spread": round(ask - bid, dec) if bid and ask else None,
        "live_price": round(live, dec) if live else None,
        "src": src,
        "venue": "binance_usdm",
        "market": "usdm_perp",
        "spot_bid": round(spot["bid"], dec) if spot.get("bid") else None,
        "spot_ask": round(spot["ask"], dec) if spot.get("ask") else None,
        "spot_last": round(spot["last"], dec) if spot.get("last") else None,
        "stale_sec": 0,
    }


def gps_spot(timeframe: str = "1m") -> dict:
    tf = timeframe if timeframe in _BAR_SEC else "1m"
    q = gps_quote()
    q["timeframe"] = tf
    q["bar_sec"] = _BAR_SEC[tf]
    q["bar_left"] = bar_remaining(tf)
    q["signal_tf"] = BOOK_SIGNAL_TF
    q["level_tf"] = BOOK_LEVEL_TF
    try:
        q["tick"] = gps_tick_score()
    except Exception:
        q["tick"] = {"score": 0.0, "n": 0}
    try:
        from gpsusdt_signal import live_signal, rail_signals, sr_levels
        q["rail"] = rail_signals(klines_fn=gps_klines)
        q["signal"] = live_signal(
            BOOK_SIGNAL_TF,
            candles=gps_klines(BOOK_SIGNAL_TF, 120),
            klines_fn=gps_klines,
            tick=q.get("tick"),
        )
        levels = sr_levels(gps_klines(BOOK_LEVEL_TF, 120))
    except Exception as e:
        q["rail"] = {}
        q["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "engine": "kalman_vwap", "error": str(e)[:160],
        }
        levels = {}
    q["book_levels"] = {
        "support": (levels or {}).get("nearest_support"),
        "resistance": (levels or {}).get("nearest_resistance"),
        "tf": BOOK_LEVEL_TF,
    }
    try:
        from gpsusdt_book import apply_signal
        q["book"] = apply_signal(
            q.get("signal"), q.get("bid"), q.get("ask"),
            rail=q.get("rail"), levels=levels,
        )
    except Exception as e:
        q["book"] = {"ok": False, "error": str(e)[:160]}
    return q


def gps_chart(timeframe: str = "1m", limit: int = 240) -> dict:
    tf = timeframe if timeframe in _BAR_SEC else "1m"
    n = max(20, min(int(limit or 240), 500))
    try:
        rows = gps_klines(tf, n)
        q = gps_quote()
    except Exception as e:
        return {
            "ok": False, "symbol": SYMBOL, "name": "GPS / USDT",
            "timeframe": tf, "algo": "gps", "error": str(e)[:200],
            "candles": [], "bid": None, "ask": None, "mid": None,
        }
    dec = int(q.get("dec") or 6)
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
        "name": "GPS / USDT",
        "timeframe": tf,
        "price_tf": tf,
        "dec": dec,
        "candles": candles,
        "source": q.get("src") or "binance",
        "bar_sec": _BAR_SEC[tf],
        "bar_left": bar_remaining(tf),
        "algo": "gps",
        "day_high": round(hi, dec) if hi else None,
        "day_low": round(lo, dec) if lo else None,
        **{k: q[k] for k in ("mid", "bid", "ask", "spread", "live_price")},
    }
    try:
        out["tick"] = gps_tick_score()
    except Exception:
        out["tick"] = {"score": 0.0, "n": 0}
    try:
        from gpsusdt_signal import overlay_signals, rail_signals, sr_levels
        sig, marks = overlay_signals(tf, candles, klines_fn=gps_klines, tick=out.get("tick"))
        out["signal"] = sig
        out["signal_markers"] = marks
        out["rail"] = sig.get("rail") or rail_signals(klines_fn=gps_klines)
        out["levels"] = sr_levels(candles)
    except Exception as e:
        out["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "engine": "kalman_vwap", "error": str(e)[:160],
        }
        out["signal_markers"] = []
        out["rail"] = {}
        out["levels"] = {"ok": False, "error": str(e)[:160]}
    try:
        from gpsusdt_book import snapshot
        out["book"] = snapshot(out.get("bid"), out.get("ask"))
    except Exception:
        out["book"] = None
    return out

"""CEM02 veri — CEM01 kopyası. forex_data import etmez."""
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
_rail_cache: tuple[float, dict] | None = None
# Defter grafiğin zaman diliminden bağımsız — hangi TF açıksa açık olsun,
# AL/SAT kararı ve Destek/Direnç hep aynı kaynaktan gelir.
BOOK_SIGNAL_TF = "1m"
BOOK_LEVEL_TF = "5m"
_tick_cache: tuple[float, dict] | None = None
_RAIL_TTL = 4.0
_TICK_TTL = 2.0
_STALE_SEC = 25  # Yahoo GC=F COMEX molasında (00:00–01:00 İST) donar
_basis: float | None = None  # GC - PAXG, son taze Yahoo anında


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


def _paxg_price() -> float | None:
    try:
        data = _get_json(f"{_BINANCE_SPOT}/api/v3/ticker/price?symbol={_PAXG}")
        return float(data["price"])
    except Exception:
        return None


def _shift(c: dict, basis: float) -> dict:
    return {
        "time": c["time"],
        "open": c["open"] + basis,
        "high": c["high"] + basis,
        "low": c["low"] + basis,
        "close": c["close"] + basis,
        "volume": c["volume"],
    }


def _fill_stale(rows: list[dict], tf: str) -> tuple[list[dict], str]:
    """Yahoo son mumu bayatsa PAXG hareketini GC seviyesine kaydırıp ekle."""
    global _basis
    if not rows:
        return rows, "yahoo_gc"
    now = int(time.time())
    last_t = int(rows[-1]["time"])
    if now - last_t < _STALE_SEC:
        return rows, "yahoo_gc"
    try:
        paxg = _paxg_klines(tf, 80)
    except Exception:
        return rows, "yahoo_stale"
    if not paxg:
        return rows, "yahoo_stale"
    anchor = next((p for p in reversed(paxg) if p["time"] <= last_t), paxg[0])
    _basis = float(rows[-1]["close"]) - float(anchor["close"])
    extra = [_shift(p, _basis) for p in paxg if p["time"] > last_t]
    if not extra:
        return rows, "yahoo_stale"
    return rows + extra, "yahoo+paxg"


def get_xau_klines(tf: str = "1m", limit: int = 200) -> tuple[list[dict], str]:
    if tf not in _YF:
        tf = "1m"
    n = max(20, min(500, int(limit)))
    key = (tf, n)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1], "cache"
    try:
        from capital_api import configured, prices as capital_prices
        if configured():
            rows = capital_prices(tf, n)
            if rows:
                _cache[key] = (now, rows)
                return rows, "capital"
    except Exception:
        pass
    iv, rg, default_n = _YF[tf]
    try:
        rows, _meta = _yahoo_raw(iv, rg)
        if tf == "4h":
            rows = _resample_4h(rows)
        rows = rows[-n:]
        if rows:
            rows, src = _fill_stale(rows, tf)
            rows = rows[-n:]
            _cache[key] = (now, rows)
            return rows, src
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
    """Bid / ask / mid + günlük H/L. Capital demo varsa oradan."""
    global _quote_cache, _basis
    now = time.time()
    if _quote_cache and now - _quote_cache[0] < 2.0:
        return dict(_quote_cache[1])
    try:
        from capital_api import configured, quote as capital_quote
        if configured():
            q = capital_quote()
            if q.get("bid") is not None or q.get("mid") is not None:
                _quote_cache = (now, q)
                return dict(q)
    except Exception:
        pass
    mid = day_hi = day_lo = None
    src = "yahoo"
    yahoo_ts = 0
    try:
        rows, meta = _yahoo_raw("1m", "1d")
        px = meta.get("regularMarketPrice")
        mid = float(px) if px is not None else None
        day_hi = meta.get("regularMarketDayHigh")
        day_lo = meta.get("regularMarketDayLow")
        if mid is None and rows:
            mid = rows[-1]["close"]
        yahoo_ts = int(meta.get("regularMarketTime") or (rows[-1]["time"] if rows else 0) or 0)
    except Exception:
        pass
    paxg = _paxg_price()
    age = (now - yahoo_ts) if yahoo_ts else 9999
    if mid is not None and paxg and age < _STALE_SEC:
        _basis = mid - paxg
    elif paxg is not None and age >= _STALE_SEC:
        # COMEX mola: Yahoo donar. Farkı donduğu andaki PAXG mumundan al,
        # şu anki PAXG'den değil — yoksa mid = stale Yahoo'da kalır.
        if _basis is None and mid is not None and yahoo_ts:
            try:
                pk = _paxg_klines("1m", 80)
                anchor = next((p for p in reversed(pk) if p["time"] <= yahoo_ts), None)
                if anchor:
                    _basis = mid - float(anchor["close"])
            except Exception:
                _basis = None
        if _basis is not None:
            mid = paxg + _basis
            src = "paxg_basis"
    if mid is None:
        mid = paxg
        src = "paxg"
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
        "src": src,
        "stale_sec": int(age) if yahoo_ts else None,
    }
    _quote_cache = (now, out)
    return dict(out)


def paxg_tick_score(window_sec: int = 90, limit: int = 500) -> dict:
    """PAXGUSDT aggTrade dengesizliği — taker alış vs satış, -100..100."""
    global _tick_cache
    now = time.time()
    if _tick_cache and now - _tick_cache[0] < _TICK_TTL:
        return dict(_tick_cache[1])
    start = int((now - window_sec) * 1000)
    try:
        data = _get_json(
            f"{_BINANCE_SPOT}/api/v3/aggTrades?symbol={_PAXG}"
            f"&startTime={start}&limit={limit}"
        )
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    buy = sell = 0.0
    for t in data:
        try:
            q = float(t.get("q") or 0)
        except (TypeError, ValueError):
            continue
        if t.get("m"):
            sell += q
        else:
            buy += q
    tot = buy + sell
    n = len(data)
    imb = ((buy - sell) / tot * 100.0) if tot > 0 else 0.0
    if n < 8:
        imb *= n / 8.0
    imb = max(-100.0, min(100.0, imb))
    out = {
        "score": round(imb, 1),
        "buy": round(buy, 4),
        "sell": round(sell, 4),
        "n": n,
        "window_sec": window_sec,
    }
    _tick_cache = (now, out)
    return dict(out)


def bar_remaining(tf: str) -> int:
    sec = _BAR_SEC.get(tf, 60)
    now = int(time.time())
    return sec - (now % sec)


def forex_rail() -> dict:
    """M5/M15 şerit sinyali — 4 sn önbellek."""
    global _rail_cache
    now = time.time()
    if _rail_cache and now - _rail_cache[0] < _RAIL_TTL:
        return dict(_rail_cache[1])
    from cem02_signal import rail_signals
    data = rail_signals()
    _rail_cache = (now, data)
    return dict(data)


def forex_spot(timeframe: str = "1m", algo: str = "g1") -> dict:
    """Kotasyon + mum kalan süre + canlı sinyal (tick, 2 sn)."""
    tf = timeframe if timeframe in _YF else "1m"
    q = forex_quote()
    q["timeframe"] = tf
    q["bar_sec"] = _BAR_SEC[tf]
    q["bar_left"] = bar_remaining(tf)
    try:
        q["rail"] = forex_rail()
    except Exception:
        q["rail"] = {}
    try:
        q["tick"] = paxg_tick_score()
    except Exception:
        q["tick"] = {"score": 0.0, "n": 0}
    q["signal_tf"] = BOOK_SIGNAL_TF
    q["level_tf"] = BOOK_LEVEL_TF
    try:
        from cem02_signal import live_signal
        q["signal"] = live_signal(BOOK_SIGNAL_TF)
    except Exception as e:
        q["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "error": str(e)[:160],
        }
    try:
        from cem02_signal import sr_levels
        rows, _ = get_xau_klines(BOOK_LEVEL_TF, 120)
        levels = sr_levels(rows)
    except Exception:
        levels = {}
    q["book_levels"] = {
        "support": (levels or {}).get("nearest_support"),
        "resistance": (levels or {}).get("nearest_resistance"),
        "tf": BOOK_LEVEL_TF,
    }
    try:
        from capital_api import configured, snapshot_book
        if configured():
            q["book"] = snapshot_book()
        else:
            from cem02_book import apply_signal
            q["book"] = apply_signal(
                q.get("signal"), q.get("bid"), q.get("ask"),
                rail=q.get("rail"), levels=levels,
            )
    except Exception as e:
        q["book"] = {"ok": False, "error": str(e)[:160]}
    return q


def forex_chart(timeframe: str = "1m", price_tf: str | None = None, limit: int | None = None, plain: bool = False, algo: str = "g1") -> dict:
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
    if plain:
        out["tick"] = {"score": 0.0, "n": 0}
        out["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "engine": "plain",
        }
        out["signal_markers"] = []
        out["rail"] = {}
        out["levels"] = {}
        out["algo"] = algo
        return out
    try:
        out["tick"] = paxg_tick_score()
    except Exception:
        out["tick"] = {"score": 0.0, "n": 0}
    try:
        from cem02_signal import overlay_signals
        sig, marks = overlay_signals(tf, candles)
        out["signal"] = sig
        out["signal_markers"] = marks
    except Exception as e:
        out["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "error": str(e)[:160],
        }
        out["signal_markers"] = []
    try:
        out["rail"] = forex_rail()
    except Exception:
        out["rail"] = {}
    try:
        from cem02_signal import sr_levels
        out["levels"] = sr_levels(candles)
    except Exception as e:
        out["levels"] = {"ok": False, "error": str(e)[:160]}
    return out

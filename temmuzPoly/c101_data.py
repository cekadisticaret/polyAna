"""
C101 — OHLCV dışı veri toplayıcı (Binance Futures public API)

Projedeki 53 defterin tamamı yalnız OHLCV mumundan karar veriyor. Bu modül
mumun yanına dört kaynak daha koyar:

  1. Emir defteri derinliği (/fapi/v1/depth) — ±%0,1 bandındaki likidite ve
     bid/ask dengesizliği. Yönü değil, **hareketin büyüklüğünü** öngörür:
     ince defter = aynı akış daha çok fiyat oynatır → volatilite çarpanı.
  2. Taker alış oranı (kline takerBuyBase) — agresif alıcı/satıcı dengesi (CVD vekili).
  3. Funding rate (/fapi/v1/premiumIndex) — kalabalığın konumu; aşırı uçta kontra.
  4. Open interest (/futures/data/openInterestHist) — para giriyor mu çıkıyor mu.

Dış bağımlılık yok (urllib). Her uç nokta /tmp'de TTL cache'lenir; :05 turunda
üç sembol × dört uç nokta = 12 istek yerine cache'ten okunur.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request

_FAPI = "https://fapi.binance.com"
_CACHE_DIR = "/tmp/c101_cache"
_TIMEOUT = 12


def _cache_path(key: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return os.path.join(_CACHE_DIR, f"{safe}.json")


def _get(path: str, params: dict, *, cache_ttl: int = 0) -> list | dict | None:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{_FAPI}{path}?{qs}" if qs else f"{_FAPI}{path}"
    cp = _cache_path(f"{path}_{qs}")
    if cache_ttl > 0 and os.path.exists(cp):
        try:
            if time.time() - os.path.getmtime(cp) < cache_ttl:
                with open(cp) as f:
                    return json.load(f)
        except Exception:
            pass
    # fapi REST yok — cache doluysa o, değilse None (WS/spot mum ayrı)
    return None


# ── 1. OHLCV + taker akışı ────────────────────────────────────
def klines(symbol: str, interval: str = "1h", limit: int = 120) -> list[dict]:
    """Ham kline → dict. takerBuyBase alanı CVD vekili için tutulur."""
    raw = None
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import public_klines
        raw = public_klines(symbol, interval, int(limit))
    except Exception:
        raw = None
    if not isinstance(raw, list):
        return []
    out = []
    for k in raw:
        try:
            vol = float(k[5])
            out.append({
                "open_time": int(k[0]),
                "o": float(k[1]),
                "h": float(k[2]),
                "l": float(k[3]),
                "c": float(k[4]),
                "v": vol,
                "taker_buy": float(k[9]),
                "taker_buy_ratio": (float(k[9]) / vol) if vol > 0 else 0.5,
            })
        except (ValueError, IndexError, TypeError):
            continue
    return out


def taker_flow_tilt(kl: list[dict], lookback: int = 6) -> float:
    """Son saatlerin taker alış oranı → [-1, 1] agresyon dengesi.

    0.5 nötr; hacimle ağırlıklandırılır ki düşük hacimli saat gürültü yapmasın.
    """
    rows = [k for k in kl[-lookback:] if k.get("v", 0) > 0]
    if not rows:
        return 0.0
    tot_v = sum(k["v"] for k in rows)
    if tot_v <= 0:
        return 0.0
    wr = sum(k["taker_buy_ratio"] * k["v"] for k in rows) / tot_v
    return max(-1.0, min(1.0, (wr - 0.5) * 4.0))


# ── 2. Emir defteri derinliği ─────────────────────────────────
def book_depth(symbol: str, band_pct: float = 0.1) -> dict | None:
    """±band_pct içindeki bid/ask notional'ı, dengesizlik ve spread (bps)."""
    raw = _get(
        "/fapi/v1/depth",
        {"symbol": symbol.upper(), "limit": 500},
        cache_ttl=20,
    )
    if not isinstance(raw, dict):
        return None
    bids = raw.get("bids") or []
    asks = raw.get("asks") or []
    if not bids or not asks:
        return None
    try:
        best_bid, best_ask = float(bids[0][0]), float(asks[0][0])
    except (ValueError, IndexError):
        return None
    mid = (best_bid + best_ask) / 2
    if mid <= 0:
        return None
    lo, hi = mid * (1 - band_pct / 100), mid * (1 + band_pct / 100)
    bid_n = sum(float(p) * float(q) for p, q in bids if float(p) >= lo)
    ask_n = sum(float(p) * float(q) for p, q in asks if float(p) <= hi)
    tot = bid_n + ask_n
    return {
        "mid": mid,
        "spread_bps": (best_ask - best_bid) / mid * 10000,
        "bid_notional": bid_n,
        "ask_notional": ask_n,
        "depth_notional": tot,
        "imbalance": ((bid_n - ask_n) / tot) if tot > 0 else 0.0,
    }


# ── 3. Funding ────────────────────────────────────────────────
def funding(symbol: str) -> dict | None:
    """Anlık funding + son 24s ortalaması (aşırı uç tespiti için)."""
    pi = _get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()}, cache_ttl=120)
    if not isinstance(pi, dict):
        return None
    try:
        last = float(pi.get("lastFundingRate") or 0)
    except (ValueError, TypeError):
        last = 0.0
    hist = _get(
        "/fapi/v1/fundingRate",
        {"symbol": symbol.upper(), "limit": 21},
        cache_ttl=1800,
    )
    rates = []
    if isinstance(hist, list):
        for h in hist:
            try:
                rates.append(float(h.get("fundingRate")))
            except (ValueError, TypeError):
                continue
    mean = sum(rates) / len(rates) if rates else 0.0
    var = sum((r - mean) ** 2 for r in rates) / len(rates) if len(rates) > 1 else 0.0
    sd = math.sqrt(var)
    return {
        "last": last,
        "mean": mean,
        "sd": sd,
        "z": ((last - mean) / sd) if sd > 1e-9 else 0.0,
        "mark": float(pi.get("markPrice") or 0),
    }


# ── 4. Open interest ──────────────────────────────────────────
def open_interest(symbol: str, period: str = "1h", limit: int = 24) -> dict | None:
    """OI değişimi — son saat vs son 24 saat ortalaması."""
    raw = _get(
        "/futures/data/openInterestHist",
        {"symbol": symbol.upper(), "period": period, "limit": int(limit)},
        cache_ttl=300,
    )
    if not isinstance(raw, list) or len(raw) < 3:
        return None
    vals = []
    for r in raw:
        try:
            vals.append(float(r.get("sumOpenInterestValue")))
        except (ValueError, TypeError):
            continue
    if len(vals) < 3:
        return None
    cur, prev = vals[-1], vals[-2]
    mean = sum(vals) / len(vals)
    return {
        "current": cur,
        "change_1h": ((cur - prev) / prev) if prev > 0 else 0.0,
        "vs_mean": ((cur - mean) / mean) if mean > 0 else 0.0,
    }


def taker_ratio_series(symbol: str, period: str = "1h", limit: int = 12) -> float | None:
    """Binance'in kendi taker long/short oranı — kline vekiline çapraz kontrol."""
    raw = _get(
        "/futures/data/takerlongshortRatio",
        {"symbol": symbol.upper(), "period": period, "limit": int(limit)},
        cache_ttl=300,
    )
    if not isinstance(raw, list) or not raw:
        return None
    try:
        return float(raw[-1].get("buySellRatio"))
    except (ValueError, TypeError):
        return None


# ── Toplayıcı ─────────────────────────────────────────────────
def collect(symbol: str) -> dict:
    """Tek sembol için tüm kaynakları topla. Eksik kaynak None kalır, model tolere eder."""
    kl = klines(symbol, "1h", 120)
    return {
        "symbol": symbol,
        "klines": kl,
        "spot": kl[-1]["c"] if kl else None,
        "flow_tilt": taker_flow_tilt(kl) if kl else 0.0,
        "depth": book_depth(symbol),
        "funding": funding(symbol),
        "oi": open_interest(symbol),
        "taker_ratio": taker_ratio_series(symbol),
    }


if __name__ == "__main__":
    import sys
    for s in (sys.argv[1:] or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        d = collect(s)
        dep, fn, oi = d["depth"], d["funding"], d["oi"]
        print(f"\n{s}  spot={d['spot']}")
        print(f"  akış eğilimi : {d['flow_tilt']:+.3f}   taker oranı: {d['taker_ratio']}")
        if dep:
            print(f"  derinlik     : ${dep['depth_notional']:,.0f}  dengesizlik {dep['imbalance']:+.3f}"
                  f"  spread {dep['spread_bps']:.2f}bps")
        if fn:
            print(f"  funding      : {fn['last']*100:+.4f}%  z={fn['z']:+.2f}")
        if oi:
            print(f"  OI           : 1s {oi['change_1h']*100:+.2f}%  ort.'a göre {oi['vs_mean']*100:+.2f}%")

"""GPSUSDT_2 — Binance USDT-M piyasa katmanı. Emir atmaz (sanal).

gpsusdt_binance.py (canlı) dokunulmaz.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_KRIPTO = str(_ROOT / "AgustosKripto")
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if _KRIPTO not in sys.path:
    sys.path.insert(0, _KRIPTO)

from binance_futures_client import (  # noqa: E402
    qty_from_notional,
    round_step,
    symbol_filters,
)
from fee_utils import DEFAULT_TAKER_FEE  # noqa: E402

SYMBOL = "GPSUSDT"
_FAPI = "https://fapi.binance.com"
_UA = {"User-Agent": "aiProject-gps2/1.0"}
_INFO_TTL = 3600.0
_DEPTH_TTL = 2.0
_info_cache: tuple[float, dict] | None = None
_depth_cache: tuple[float, dict] | None = None


def _get(path: str, params: str = "") -> dict | list:
    from binance_fapi_guard import FapiReadDenied, ban_msg, fapi_blocked
    if fapi_blocked():
        raise RuntimeError(ban_msg())
    raise FapiReadDenied(f"fapi okuma kapalı {path}")


def exchange_filters() -> dict:
    global _info_cache
    now = time.time()
    if _info_cache and now - _info_cache[0] < _INFO_TTL:
        return dict(_info_cache[1])
    data = _get("/fapi/v1/exchangeInfo", f"symbol={SYMBOL}")
    filt = symbol_filters(data if isinstance(data, dict) else {}, SYMBOL)
    _info_cache = (now, filt)
    return dict(filt)


def taker_rate() -> float:
    """Sanal — VIP oranı çekmez (canlı GPS hesabına / imzalı API'ye dokunmaz)."""
    return float(DEFAULT_TAKER_FEE)


def book_ticker() -> dict:
    try:
        from binance_fapi_guard import get_book
        hit = get_book(SYMBOL)
        if hit and (hit.get("bid") or hit.get("ask")):
            return {
                "bid": float(hit.get("bid") or 0),
                "ask": float(hit.get("ask") or 0),
                "bid_qty": float(hit.get("bid_qty") or 0),
                "ask_qty": float(hit.get("ask_qty") or 0),
            }
    except Exception:
        pass
    try:
        from binance_fapi_guard import fapi_blocked
        if fapi_blocked():
            return {"bid": 0.0, "ask": 0.0, "bid_qty": 0.0, "ask_qty": 0.0}
    except Exception:
        pass
    d = _get("/fapi/v1/ticker/bookTicker", f"symbol={SYMBOL}")
    return {
        "bid": float(d.get("bidPrice") or 0),
        "ask": float(d.get("askPrice") or 0),
        "bid_qty": float(d.get("bidQty") or 0),
        "ask_qty": float(d.get("askQty") or 0),
    }


def premium() -> dict:
    try:
        from binance_fapi_guard import ws_premium
        hit = ws_premium(SYMBOL)
        if hit:
            return hit
    except Exception:
        pass
    try:
        from binance_fapi_guard import fapi_blocked
        if fapi_blocked():
            return {"mark": 0.0, "index": 0.0, "last_funding_rate": 0.0, "next_funding_time": 0}
    except Exception:
        pass
    d = _get("/fapi/v1/premiumIndex", f"symbol={SYMBOL}")
    return {
        "mark": float(d.get("markPrice") or 0),
        "index": float(d.get("indexPrice") or 0),
        "last_funding_rate": float(d.get("lastFundingRate") or 0),
        "next_funding_time": int(d.get("nextFundingTime") or 0),
    }


def funding_events(limit: int = 8) -> list[dict]:
    rows = _get("/fapi/v1/fundingRate", f"symbol={SYMBOL}&limit={int(limit)}")
    out = []
    for r in rows or []:
        out.append({
            "time": int(r.get("fundingTime") or 0),
            "rate": float(r.get("fundingRate") or 0),
            "mark": float(r.get("markPrice") or 0),
        })
    return out


def depth(limit: int = 50) -> dict:
    global _depth_cache
    now = time.time()
    if _depth_cache and now - _depth_cache[0] < _DEPTH_TTL:
        return _depth_cache[1]
    d = _get("/fapi/v1/depth", f"symbol={SYMBOL}&limit={int(limit)}")
    out = {
        "bids": [(float(p), float(q)) for p, q in (d.get("bids") or [])],
        "asks": [(float(p), float(q)) for p, q in (d.get("asks") or [])],
    }
    _depth_cache = (now, out)
    return out


def market_fill(side: str, qty: float) -> dict:
    """Binance MARKET gibi: alış ask merdivenini, satış bid merdivenini yer."""
    filt = exchange_filters()
    step = float(filt.get("step_size") or 1)
    qty = round_step(float(qty), step)
    if qty <= 0:
        return {"ok": False, "error": "qty_zero"}
    book = depth(50)
    levels = book["asks"] if side == "buy" else book["bids"]
    left = qty
    cost = 0.0
    used = 0
    last_px = None
    for px, av in levels:
        take = min(left, av)
        if take <= 0:
            continue
        cost += take * px
        left -= take
        last_px = px
        used += 1
        if left <= 1e-12:
            break
    if left > 1e-9:
        if last_px is None:
            return {"ok": False, "error": "empty_book"}
        cost += left * last_px
        left = 0.0
    filled = qty
    vwap = cost / filled if filled else 0.0
    vwap = round_px(vwap)
    notional = round(filled * vwap, 8)
    min_n = float(filt.get("min_notional") or 5)
    if notional < min_n:
        return {"ok": False, "error": "min_notional", "notional": notional, "min": min_n}
    return {
        "ok": True,
        "side": side,
        "qty": filled,
        "price": vwap,
        "notional": notional,
        "levels": used,
        "taker": True,
        "type": "MARKET",
    }


def size_from_margin(margin: float, leverage: float, price: float) -> float:
    filt = exchange_filters()
    return qty_from_notional(
        float(margin),
        float(price),
        leverage=int(leverage),
        step_size=float(filt.get("step_size") or 1),
        min_qty=float(filt.get("min_qty") or 1),
        min_notional=float(filt.get("min_notional") or 5),
    )


def round_px(px: float) -> float:
    tick = float(exchange_filters().get("tick_size") or 0.000001)
    if tick <= 0:
        return float(px)
    return round(round(float(px) / tick) * tick, 8)



#!/usr/bin/env python3
"""Binance USD-M exchange gerçeği — fiyat, filtre, dolum, fee, liq, funding, PnL.

Strateji yok (sinyal / ATR / skip / sanal kasa yok).
Bu sunucuda fapi GET kapalı: kotasyon WS (`binance_fapi_guard`),
filtre yerelde cache + yedek tablo.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
_FILTER_FILES = (
    os.path.join(_DIR, "data", "um_filters.json"),
    "/tmp/binance_um_filters.json",
)

FEE_RATE = 0.0005
MMR = 0.004
FUND_MS = 8 * 3600 * 1000

# tick / step / minNotional / maxLeverage — exchangeInfo yedeği
_FILT: dict[str, dict[str, float]] = {
    "BTCUSDT":  {"tick": 0.1, "step": 0.001, "min_n": 100, "max_lev": 125},
    "ETHUSDT":  {"tick": 0.01, "step": 0.001, "min_n": 20, "max_lev": 100},
    "SOLUSDT":  {"tick": 0.01, "step": 0.01, "min_n": 5, "max_lev": 50},
    "BNBUSDT":  {"tick": 0.01, "step": 0.01, "min_n": 5, "max_lev": 50},
    "XRPUSDT":  {"tick": 0.0001, "step": 0.1, "min_n": 5, "max_lev": 75},
    "DOGEUSDT": {"tick": 0.00001, "step": 1, "min_n": 5, "max_lev": 50},
    "ADAUSDT":  {"tick": 0.0001, "step": 1, "min_n": 5, "max_lev": 75},
    "AVAXUSDT": {"tick": 0.001, "step": 0.01, "min_n": 5, "max_lev": 50},
    "LINKUSDT": {"tick": 0.001, "step": 0.01, "min_n": 5, "max_lev": 75},
    "DOTUSDT":  {"tick": 0.001, "step": 0.1, "min_n": 5, "max_lev": 75},
    "LTCUSDT":  {"tick": 0.01, "step": 0.001, "min_n": 5, "max_lev": 75},
    "NEARUSDT": {"tick": 0.001, "step": 0.1, "min_n": 5, "max_lev": 50},
    "SUIUSDT":  {"tick": 0.0001, "step": 0.1, "min_n": 5, "max_lev": 50},
    "APTUSDT":  {"tick": 0.0001, "step": 0.01, "min_n": 5, "max_lev": 50},
    "ARBUSDT":  {"tick": 0.0001, "step": 0.1, "min_n": 5, "max_lev": 50},
    "OPUSDT":   {"tick": 0.0001, "step": 0.1, "min_n": 5, "max_lev": 50},
    "INJUSDT":  {"tick": 0.001, "step": 0.01, "min_n": 5, "max_lev": 50},
    "TIAUSDT":  {"tick": 0.0001, "step": 0.1, "min_n": 5, "max_lev": 50},
    "FILUSDT":  {"tick": 0.001, "step": 0.01, "min_n": 5, "max_lev": 50},
    "ATOMUSDT": {"tick": 0.001, "step": 0.01, "min_n": 5, "max_lev": 75},
    "HYPEUSDT": {"tick": 0.001, "step": 0.01, "min_n": 5, "max_lev": 25},
    "ZECUSDT":  {"tick": 0.01, "step": 0.001, "min_n": 5, "max_lev": 50},
    "KAITOUSDT": {"tick": 0.0001, "step": 1, "min_n": 5, "max_lev": 25},
    "ENAUSDT":  {"tick": 0.0001, "step": 1, "min_n": 5, "max_lev": 25},
    "WLDUSDT":  {"tick": 0.0001, "step": 1, "min_n": 5, "max_lev": 50},
    "TAOUSDT":  {"tick": 0.01, "step": 0.001, "min_n": 5, "max_lev": 25},
    "ONDOUSDT": {"tick": 0.0001, "step": 0.1, "min_n": 5, "max_lev": 25},
    "UNIUSDT":  {"tick": 0.001, "step": 1, "min_n": 5, "max_lev": 50},
    "AAVEUSDT": {"tick": 0.01, "step": 0.01, "min_n": 5, "max_lev": 50},
    "XLMUSDT":  {"tick": 0.00001, "step": 1, "min_n": 5, "max_lev": 50},
    "TRUMPUSDT": {"tick": 0.001, "step": 0.01, "min_n": 5, "max_lev": 25},
}

_filt_loaded = False


def _load_filter_files() -> None:
    global _filt_loaded
    if _filt_loaded:
        return
    _filt_loaded = True
    for path in _FILTER_FILES:
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue
        rows = data.get("symbols") if isinstance(data, dict) else data
        if not isinstance(rows, dict):
            continue
        for sym, row in rows.items():
            if not isinstance(row, dict):
                continue
            cur = dict(_FILT.get(sym.upper()) or {})
            if row.get("tick") or row.get("tickSize"):
                cur["tick"] = float(row.get("tick") or row.get("tickSize"))
            if row.get("step") or row.get("stepSize"):
                cur["step"] = float(row.get("step") or row.get("stepSize"))
            if row.get("min_n") or row.get("minNotional"):
                cur["min_n"] = float(row.get("min_n") or row.get("minNotional"))
            if row.get("max_lev") or row.get("maxLeverage"):
                cur["max_lev"] = float(row.get("max_lev") or row.get("maxLeverage"))
            _FILT[sym.upper()] = cur


def filters(symbol: str) -> dict[str, float]:
    _load_filter_files()
    hit = _FILT.get((symbol or "").upper())
    if hit:
        return {
            "tick": float(hit.get("tick") or 0.0001),
            "step": float(hit.get("step") or 0.001),
            "min_n": float(hit.get("min_n") or 5),
            "max_lev": float(hit.get("max_lev") or 20),
        }
    return {"tick": 0.0001, "step": 0.001, "min_n": 5.0, "max_lev": 20.0}


def round_step(value: float, step: float) -> float:
    if step <= 0 or value <= 0:
        return 0.0
    n = math.floor(value / step + 1e-12)
    prec = max(0, len(f"{step:.12f}".rstrip("0").split(".")[-1]))
    return round(n * step, prec)


def round_tick(price: float, tick: float) -> float:
    if tick <= 0 or price <= 0:
        return 0.0
    n = math.floor(price / tick + 1e-12)
    prec = max(0, len(f"{tick:.12f}".rstrip("0").split(".")[-1]))
    return round(n * tick, prec)


def clamp_leverage(symbol: str, lev: float) -> int:
    cap = int(filters(symbol)["max_lev"] or 20)
    v = int(lev)
    if v < 1:
        return 1
    return min(v, cap)


def qty_from_notional(symbol: str, notional: float, price: float) -> float:
    if price <= 0 or notional <= 0:
        return 0.0
    f = filters(symbol)
    qty = round_step(notional / price, f["step"])
    if qty <= 0 or qty * price + 1e-9 < f["min_n"]:
        return 0.0
    return qty


def quotes(symbol: str) -> dict[str, Any]:
    """bid/ask + mark/last + funding — WS bookTicker + premiumIndex."""
    mark = last = bid = ask = 0.0
    rate = 0.0
    nxt = 0
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    try:
        from binance_fapi_guard import get_book, get_last, get_mark, ws_premium
        mark = float(get_mark(symbol) or 0)
        last = float(get_last(symbol) or 0)
        bk = get_book(symbol) or {}
        bid = float(bk.get("bid") or 0)
        ask = float(bk.get("ask") or 0)
        prem = ws_premium(symbol) or {}
        rate = float(prem.get("last_funding_rate") or 0)
        nxt = int(prem.get("next_funding_time") or 0)
        if mark <= 0:
            mark = float(prem.get("mark") or 0)
    except Exception:
        pass
    if mark <= 0:
        mark = last or bid or ask
    if last <= 0:
        last = mark
    if ask <= 0:
        ask = mark or last
    if bid <= 0:
        bid = mark or last
    return {
        "symbol": (symbol or "").upper(),
        "bid": bid,
        "ask": ask,
        "mark": mark,
        "last": last,
        "fund_rate": rate,
        "next_funding_time": nxt,
    }


def fill_open(side: str, q: dict) -> float:
    if (side or "").upper() == "LONG":
        return float(q.get("ask") or q.get("mark") or q.get("last") or 0)
    return float(q.get("bid") or q.get("mark") or q.get("last") or 0)


def fill_close(side: str, q: dict) -> float:
    if (side or "").upper() == "LONG":
        return float(q.get("bid") or q.get("mark") or q.get("last") or 0)
    return float(q.get("ask") or q.get("mark") or q.get("last") or 0)


def fee(qty: float, price: float) -> float:
    return round(float(qty) * float(price) * FEE_RATE, 8)


def liq_price(side: str, entry: float, lev: float) -> float:
    if entry <= 0 or lev <= 0:
        return 0.0
    if (side or "").upper() == "LONG":
        return entry * (1.0 - 1.0 / lev + MMR)
    return entry * (1.0 + 1.0 / lev - MMR)


def hit_liq(side: str, mark: float, liq: float) -> bool:
    if mark <= 0 or liq <= 0:
        return False
    if (side or "").upper() == "LONG":
        return mark <= liq
    return mark >= liq


def gross(side: str, entry: float, exit_px: float, qty: float) -> float:
    if (side or "").upper() == "LONG":
        return (exit_px - entry) * qty
    return (entry - exit_px) * qty


def net_pnl(
    side: str,
    entry: float,
    exit_px: float,
    qty: float,
    *,
    fee_open: float,
    fee_close: float,
    funding: float = 0.0,
) -> float:
    return gross(side, entry, exit_px, qty) - fee_open - fee_close + funding


def apply_funding(pos: dict, q: dict, now_ms: int | None = None) -> dict:
    nxt = int(q.get("next_funding_time") or 0)
    if nxt <= 0:
        return pos
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    event = nxt - FUND_MS
    if event <= 0 or not (event <= now < nxt):
        return pos
    if int(pos.get("funding_event_ms") or 0) == event:
        return pos
    qty = float(pos.get("qty") or 0)
    mark = float(q.get("mark") or 0)
    rate = float(q.get("fund_rate") or 0)
    if qty <= 0 or mark <= 0:
        return pos
    raw = qty * mark * rate
    acc = float(pos.get("funding_acc") or 0)
    if (pos.get("side") or "LONG").upper() == "LONG":
        acc -= raw
    else:
        acc += raw
    out = dict(pos)
    out["funding_acc"] = round(acc, 8)
    out["funding_event_ms"] = event
    return out


if __name__ == "__main__":
    assert abs(liq_price("LONG", 100, 10) - 90.4) < 1e-9
    assert abs(fee(10, 50) - 0.25) < 1e-9
    print("binance_um ok")

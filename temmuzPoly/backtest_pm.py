"""Backtest PM kotasyonu — üretim `pm_sanal_fill` + `pm_taker_fee` ile uyumlu.

Geçmiş CLOB defteri yok; saat açılışı (PTB) vs spot + volatilite ile adil olasılık
tahmin edilir, tipik overround (~1.8 puan) eklenir, ardından tick yuvarlama /
min 5 adet / taker ücreti uygulanır.
"""
from __future__ import annotations

import math

from c101_signal import parkinson_sigma, _MIN_T_REMAIN, _phi
from pm_trader_helpers import pm_fit_buy, pm_taker_fee, PM_MIN_ORDER_SIZE

_OVERROUND = 0.018  # ölçülen gerçek spread (2026-08-14)
_MIN_ASK = 0.02
_MAX_ASK = 0.98


def _fair_p_up(kslice: list[dict], ptb: float, spot: float) -> float:
    kl = [{"o": k["open"], "h": k["high"], "l": k["low"], "c": k["close"]} for k in kslice]
    if len(kl) < 14 or ptb <= 0 or spot <= 0:
        return 0.5
    sig_s = parkinson_sigma(kl, 12)
    sig_l = parkinson_sigma(kl, 72)
    if sig_s is None and sig_l is None:
        return 0.5
    if sig_s is None:
        sigma = sig_l
    elif sig_l is None:
        sigma = sig_s
    else:
        sigma = 0.6 * sig_s + 0.4 * sig_l
    if not sigma or sigma <= 0:
        return 0.5
    t_remain = max(_MIN_T_REMAIN, 0.92)
    z = math.log(spot / ptb) / (sigma * math.sqrt(t_remain))
    return max(0.05, min(0.95, _phi(z)))


def estimate_asks(kslice: list[dict], next_bar: dict) -> tuple[float, float]:
    """(up_ask, down_ask) — normalize overround."""
    ptb = float(next_bar["open"])
    spot = float(kslice[-1]["close"])
    p_up = _fair_p_up(kslice, ptb, spot)
    p_down = 1.0 - p_up
    half = _OVERROUND / 2.0
    up = p_up + half
    down = p_down + half
    s = up + down
    if s <= 0:
        return 0.51, 0.51
    return round(up / s, 4), round(down / s, 4)


def fill_from_ask(amount_usd: float, ask: float) -> dict | None:
    """`pm_sanal_fill` ile aynı yuvarlama; defter yok → tahmini ask = vwap."""
    if amount_usd <= 0 or not (_MIN_ASK < ask < _MAX_ASK):
        return None
    price = max(_MIN_ASK, min(_MAX_ASK, round(ask, 2)))
    from decimal import Decimal, ROUND_DOWN
    raw_sz = float(Decimal(str(amount_usd / price)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    size, price = pm_fit_buy(max(PM_MIN_ORDER_SIZE, raw_sz), price)
    spent = round(size * price, 2)
    fee = pm_taker_fee(size, price)
    return {
        "pm_entry_price": price,
        "pm_spent": spent,
        "pm_size": size,
        "to_win": size,
        "pm_fee": fee,
        "pm_quote_src": "bt_model_ask",
        "pm_fill_vwap": round(ask, 4),
    }


def fill_position_quote(
    symbol: str,
    direction: str,
    amount_usd: float,
    kslice: list[dict],
    next_bar: dict,
) -> dict | None:
    up_ask, down_ask = estimate_asks(kslice, next_bar)
    ask = up_ask if direction == "UP" else down_ask
    fill = fill_from_ask(amount_usd, ask)
    if not fill:
        return None
    fill["pm_mid_price"] = round(up_ask if direction == "UP" else down_ask, 4)
    fill["symbol"] = symbol
    return fill

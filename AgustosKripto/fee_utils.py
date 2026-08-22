#!/usr/bin/env python3
"""Binance USD-M komisyon yardımcıları — brüt → net PnL.

Varsayılan taker %0.05 (MARKET, VIP0 regular). Canlıda commissionRate / userTrades ile gerçek değer.
"""
from __future__ import annotations

import time
from typing import Any

# Binance USDT-M VIP0 (regular) varsayılanları
DEFAULT_TAKER_FEE = 0.0005
DEFAULT_MAKER_FEE = 0.0002

_RATE_CACHE: dict[str, tuple[float, float, float]] = {}  # symbol -> (taker, maker, ts)
_RATE_TTL_SEC = 3600.0


def load_fee_rates_from_config(cfg: dict | None = None) -> tuple[float, float]:
    cfg = cfg or {}
    taker = float(cfg.get("taker_fee_rate") or DEFAULT_TAKER_FEE)
    maker = float(cfg.get("maker_fee_rate") or DEFAULT_MAKER_FEE)
    return taker, maker


def estimate_fee(notional: float, rate: float | None = None) -> float:
    """Tek yön (open veya close) komisyon tahmini."""
    r = DEFAULT_TAKER_FEE if rate is None else float(rate)
    return round(abs(float(notional or 0)) * r, 6)


def roundtrip_fee(
    entry_notional: float,
    exit_notional: float | None = None,
    rate: float | None = None,
) -> float:
    """Aç + kapat toplam komisyon."""
    ex = entry_notional if exit_notional is None else exit_notional
    return round(estimate_fee(entry_notional, rate) + estimate_fee(ex, rate), 6)


def net_pnl(gross: float, commission: float) -> float:
    return round(float(gross or 0) - abs(float(commission or 0)), 4)


def _fapi_blocked() -> bool:
    try:
        import os
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import fapi_blocked  # noqa: WPS433
        return bool(fapi_blocked())
    except Exception:
        return False


def get_taker_rate(
    client: Any | None = None,
    symbol: str = "BTCUSDT",
    *,
    cfg: dict | None = None,
) -> float:
    """API commissionRate (cache) → config → default."""
    taker_cfg, _maker = load_fee_rates_from_config(cfg)
    sym = (symbol or "BTCUSDT").upper()
    hit = _RATE_CACHE.get(sym)
    if hit and (time.time() - hit[2]) < _RATE_TTL_SEC:
        return hit[0]
    return taker_cfg


def get_maker_rate(
    client: Any | None = None,
    symbol: str = "BTCUSDT",
    *,
    cfg: dict | None = None,
) -> float:
    """Maker (post-only limit) oranı. API commissionRate (cache) → config → default."""
    _taker_cfg, maker_cfg = load_fee_rates_from_config(cfg)
    sym = (symbol or "BTCUSDT").upper()
    hit = _RATE_CACHE.get(sym)
    if hit and (time.time() - hit[2]) < _RATE_TTL_SEC:
        return hit[1]
    return maker_cfg


def sum_trade_commission(trades: list | None) -> float:
    """userTrades listesinden USDT komisyon toplamı (mutlak)."""
    total = 0.0
    for t in trades or []:
        try:
            c = abs(float(t.get("commission") or 0))
            asset = (t.get("commissionAsset") or "USDT").upper()
            if asset in ("USDT", "BUSD", "USD"):
                total += c
            # BNB fee → yaklaşık atla (nadir); USDT-M genelde USDT
        except Exception:
            continue
    return round(total, 6)


def commission_for_order(
    client: Any | None,
    symbol: str,
    order_id: Any,
    *,
    notional: float,
    rate: float | None = None,
    cfg: dict | None = None,
) -> tuple[float, str]:
    """(commission, source) — source: userTrades | estimate."""
    sym = symbol.upper()
    if client is not None and getattr(client, "configured", lambda: False)() and order_id:
        try:
            oid = int(order_id)
            trades = client.user_trades(sym, order_id=oid, limit=50)
            fee = sum_trade_commission(trades)
            if fee > 0:
                return fee, "userTrades"
        except Exception as e:
            print(f"[fee_utils] userTrades {sym}/{order_id}: {e}")
    r = rate if rate is not None else get_taker_rate(client, sym, cfg=cfg)
    return estimate_fee(notional, r), "estimate"

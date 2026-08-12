#!/usr/bin/env python3
"""Kripto Futures — Binance USD-M kaldıraçlı işlem üst katmanı.

Özellikler:
  - Leverage + margin tipi ayarı
  - MARKET LONG/SHORT açılış (margin USDT × leverage)
  - Pozisyon kapatma (reduce-only MARKET)
  - dry_run varsayılan (gerçek emir yok)
  - Yerel state/history

Env:
  BINANCE_FUTURES_API_KEY / BINANCE_FUTURES_API_SECRET
  BINANCE_FUTURES_TESTNET=true|false
  CRYPTO_FUTURES_LIVE=true  → config dry_run=false iken gerçek emir

CLI:
  python3 crypto_futures_trader.py status
  python3 crypto_futures_trader.py open BTCUSDT LONG --margin 20 --leverage 5
  python3 crypto_futures_trader.py close BTCUSDT
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from binance_futures_client import (
    BinanceFuturesClient,
    BinanceFuturesError,
    qty_from_notional,
    symbol_filters,
)
from fee_utils import (
    commission_for_order,
    estimate_fee,
    get_maker_rate,
    get_taker_rate,
    net_pnl,
    roundtrip_fee,
)

_ENV_FILE = os.path.join(_DIR, "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_TZ_TR = ZoneInfo("Europe/Istanbul")
CONFIG_FILE = os.path.join(_DIR, "crypto_futures_config.json")
STATE_FILE = os.path.join(_DIR, "crypto_futures_state.json")
HISTORY_FILE = os.path.join(_DIR, "crypto_futures_history.json")
LABEL = "KRIPTO FUTURE"

# Binance Live yeni açılış — bu majors kapalı (kapatma/trail etkilenmez)
LIVE_OPEN_EXCLUDE = frozenset({"BTCUSDT", "ETHUSDT", "BNBUSDT"})


def is_live_open_excluded(symbol: str) -> bool:
    return (symbol or "").upper() in LIVE_OPEN_EXCLUDE


def load_config() -> dict:
    defaults = {
        "dry_run": True,
        "testnet": False,
        "default_leverage": 5,
        "default_margin_type": "ISOLATED",
        "default_margin_usd": 20.0,
        "max_leverage": 20,
        "max_open_positions": 5,
        "taker_fee_rate": 0.0004,
        "maker_fee_rate": 0.0002,
        "dust_max_notional_usd": 2.0,  # |notional| ≤ bu → toz, süpür
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                defaults.update(data)
        except Exception:
            pass
    # env override
    if os.getenv("BINANCE_FUTURES_TESTNET", "").lower() in ("1", "true", "yes"):
        defaults["testnet"] = True
    live_env = os.getenv("CRYPTO_FUTURES_LIVE", "").lower() in ("1", "true", "yes")
    if not live_env:
        defaults["dry_run"] = True
    return defaults


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"open_positions": [], "updated_at_tr": ""}


def save_state(state: dict) -> None:
    state["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history: list) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _client(cfg: dict | None = None) -> BinanceFuturesClient:
    cfg = cfg or load_config()
    return BinanceFuturesClient(testnet=bool(cfg.get("testnet")))


def _is_dry(cfg: dict) -> bool:
    if os.getenv("CRYPTO_FUTURES_LIVE", "").lower() not in ("1", "true", "yes"):
        return True
    return bool(cfg.get("dry_run", True))


def usdt_balance(client: BinanceFuturesClient | None = None) -> dict:
    """USDT wallet / available bakiyesi."""
    c = client or _client()
    if not c.configured():
        return {"asset": "USDT", "balance": None, "available": None, "error": "api_key_missing"}
    rows = c.balance()
    for r in rows:
        if r.get("asset") == "USDT":
            return {
                "asset": "USDT",
                "balance": float(r.get("balance") or 0),
                "available": float(r.get("availableBalance") or 0),
                "cross_wallet": float(r.get("crossWalletBalance") or 0),
            }
    return {"asset": "USDT", "balance": 0.0, "available": 0.0}


def get_positions(client: BinanceFuturesClient | None = None, symbol: str | None = None) -> list[dict]:
    c = client or _client()
    if not c.configured():
        return []
    rows = c.position_risk(symbol)
    out = []
    for r in rows:
        amt = float(r.get("positionAmt") or 0)
        if abs(amt) < 1e-12:
            continue
        out.append({
            "symbol": r.get("symbol"),
            "position_amt": amt,
            "side": "LONG" if amt > 0 else "SHORT",
            "entry_price": float(r.get("entryPrice") or 0),
            "mark_price": float(r.get("markPrice") or 0),
            "unrealized_pnl": float(r.get("unRealizedProfit") or 0),
            "leverage": int(float(r.get("leverage") or 0)),
            "margin_type": r.get("marginType"),
            "liquidation_price": float(r.get("liquidationPrice") or 0),
            "notional": float(r.get("notional") or 0),
        })
    return out


def prepare_symbol(
    symbol: str,
    leverage: int,
    margin_type: str = "ISOLATED",
    *,
    client: BinanceFuturesClient | None = None,
    dry_run: bool = True,
) -> dict:
    """Leverage + margin tipi hazırla (dry_run'da sadece plan)."""
    symbol = symbol.upper()
    c = client or _client()
    info = c.exchange_info(symbol)
    filt = symbol_filters(info, symbol)
    if filt.get("status") and filt["status"] != "TRADING":
        raise BinanceFuturesError(f"{symbol} TRADING değil: {filt.get('status')}")

    plan = {
        "symbol": symbol,
        "leverage": int(leverage),
        "margin_type": margin_type.upper(),
        "filters": filt,
        "dry_run": dry_run,
    }
    if dry_run:
        plan["leverage_resp"] = "DRY_RUN"
        plan["margin_resp"] = "DRY_RUN"
        return plan

    plan["leverage_resp"] = c.set_leverage(symbol, leverage)
    try:
        plan["margin_resp"] = c.set_margin_type(symbol, margin_type)
    except BinanceFuturesError as e:
        # -4046: No need to change margin type
        body = e.body if isinstance(e.body, dict) else {}
        if body.get("code") in (-4046, 4046) or "No need to change" in str(e):
            plan["margin_resp"] = {"skipped": True, "reason": str(e)}
        else:
            raise
    return plan


def reconcile_shared_opens_with_binance(
    state: dict | None = None,
    client: BinanceFuturesClient | None = None,
) -> dict:
    """Paylaşılan state'teki hayalet pozisyonları Binance'e göre temizle."""
    state = state if state is not None else load_state()
    opens = list(state.get("open_positions") or [])
    if not opens:
        return state
    c = client or _client()
    if not c.configured():
        return state
    try:
        live = {p["symbol"] for p in get_positions(c)}
    except Exception as e:
        print(f"[{LABEL}] reconcile: {e}")
        return state
    kept = [p for p in opens if (p.get("symbol") or "").upper() in live]
    if len(kept) != len(opens):
        dropped = [
            (p.get("symbol") or "")
            for p in opens
            if (p.get("symbol") or "").upper() not in live
        ]
        print(f"[{LABEL}] reconcile: hayalet silindi {dropped}")
        state["open_positions"] = kept
        save_state(state)
    return state


def open_market(
    symbol: str,
    side: str,
    *,
    margin_usd: float | None = None,
    leverage: int | None = None,
    margin_type: str | None = None,
    reduce_only: bool = False,
    skip_max_positions: bool = False,
) -> dict:
    """MARKET ile LONG (BUY) veya SHORT (SELL) aç.

    margin_usd: teminat (USDT). Pozisyon notional ≈ margin_usd * leverage.
    skip_max_positions: CR6 gibi kendi kotasını yöneten stratejiler için.
    """
    cfg = load_config()
    symbol = symbol.upper()
    side_u = side.upper()
    if side_u in ("LONG", "BUY"):
        order_side = "BUY"
        pos_side = "LONG"
    elif side_u in ("SHORT", "SELL"):
        order_side = "SELL"
        pos_side = "SHORT"
    else:
        raise ValueError("side LONG/SHORT olmalı")

    if symbol not in [s.upper() for s in cfg.get("symbols") or []]:
        raise ValueError(f"{symbol} allowlist dışı — crypto_futures_config.json")

    if not reduce_only and is_live_open_excluded(symbol):
        raise ValueError(f"{symbol} Binance Live açılış dışı (BTC/ETH/BNB kapalı)")

    lev = int(leverage or cfg.get("default_leverage") or 5)
    max_lev = int(cfg.get("max_leverage") or 20)
    if lev < 1 or lev > max_lev:
        raise ValueError(f"leverage 1–{max_lev} olmalı")

    margin = float(margin_usd if margin_usd is not None else cfg.get("default_margin_usd") or 20)
    if margin <= 0:
        raise ValueError("margin_usd > 0 olmalı")

    mtype = (margin_type or cfg.get("default_margin_type") or "ISOLATED").upper()
    dry = _is_dry(cfg)
    c = _client(cfg)

    state = load_state()
    if c.configured() and not dry:
        state = reconcile_shared_opens_with_binance(state, c)
    opens = state.get("open_positions") or []
    max_pos = int(cfg.get("max_open_positions") or 5)
    if (
        not reduce_only
        and not skip_max_positions
        and len(opens) >= max_pos
    ):
        raise RuntimeError(f"max_open_positions={max_pos} doldu")
    price = c.mark_price(symbol)
    prep = prepare_symbol(symbol, lev, mtype, client=c, dry_run=dry)
    filt = prep["filters"]
    qty = qty_from_notional(
        margin,
        price,
        leverage=lev,
        step_size=filt["step_size"],
        min_qty=filt["min_qty"],
        min_notional=filt["min_notional"],
    )
    if qty <= 0:
        raise RuntimeError("qty hesaplanamadı (min lot / notional)")

    notional = round(qty * price, 4)
    now_tr = datetime.now(_TZ_TR)
    order_req = {
        "symbol": symbol,
        "side": order_side,
        "type": "MARKET",
        "quantity": qty,
    }
    if reduce_only:
        order_req["reduceOnly"] = "true"

    result: dict = {
        "ok": True,
        "dry_run": dry,
        "symbol": symbol,
        "side": pos_side,
        "order_side": order_side,
        "leverage": lev,
        "margin_usd": margin,
        "margin_type": mtype,
        "mark_price": price,
        "qty": qty,
        "notional": notional,
        "entry_time_tr": now_tr.isoformat(),
        "testnet": c.testnet,
    }

    if dry:
        result["order"] = {
            "orderId": f"DRY-{int(time.time())}",
            "status": "DRY_RUN",
            "avgPrice": str(price),
            "executedQty": str(qty),
        }
        print(
            f"[{LABEL}] DRY RUN {pos_side} {symbol} qty={qty} "
            f"@{price:.4f} margin=${margin:.2f} lev={lev}x notional≈${notional:.2f}"
        )
    else:
        if not c.configured():
            raise BinanceFuturesError("API key yok — canlı emir atılamaz")
        order = c.new_order(**order_req)
        result["order"] = order
        print(
            f"[{LABEL}] LIVE {pos_side} {symbol} qty={qty} "
            f"orderId={order.get('orderId')} lev={lev}x"
        )

    if not reduce_only:
        entry_px = float(result["order"].get("avgPrice") or price) or price
        fill_notional = round(qty * entry_px, 4)
        oid = result["order"].get("orderId")
        if dry:
            rate = get_taker_rate(None, symbol, cfg=cfg)
            entry_fee = estimate_fee(fill_notional, rate)
            fee_src = "estimate"
        else:
            entry_fee, fee_src = commission_for_order(
                c, symbol, oid, notional=fill_notional, cfg=cfg,
            )
        result["entry_fee"] = entry_fee
        result["fee_source"] = fee_src
        pos = {
            "symbol": symbol,
            "side": pos_side,
            "qty": qty,
            "leverage": lev,
            "margin_usd": margin,
            "margin_type": mtype,
            "entry_price": entry_px,
            "notional": fill_notional,
            "entry_fee": entry_fee,
            "entry_time_tr": now_tr.isoformat(),
            "order_id": oid,
            "dry_run": dry,
            "testnet": c.testnet,
        }
        # aynı sembol varsa değiştir
        opens = [p for p in opens if p.get("symbol") != symbol]
        opens.append(pos)
        state["open_positions"] = opens
        save_state(state)

    return result


def _round_to_tick(price: float, tick: float, *, mode: str = "down") -> float:
    """Fiyatı tick_size'a yuvarla — LIMIT emir PRICE_FILTER için.

    mode="down" alış (bid) tarafı, mode="up" satış (ask) tarafı içindir;
    böylece post-only emir karşı tarafa değmez.
    """
    if not tick or tick <= 0:
        return float(price)
    decs = max(0, -int(round(math.log10(tick)))) if tick < 1 else 0
    steps = float(price) / tick
    # float artığı yüzünden yanlış basamağa kaymayı önle
    steps = round(steps, 6)
    steps = math.ceil(steps) if mode == "up" else math.floor(steps)
    return round(steps * tick, decs)


def open_maker(
    symbol: str,
    side: str,
    *,
    margin_usd: float | None = None,
    leverage: int | None = None,
    margin_type: str | None = None,
    wait_sec: float | None = None,
    poll_sec: float = 3.0,
    skip_max_positions: bool = False,
) -> dict:
    """Post-only LIMIT ile pozisyon aç — maker komisyonu (%0.02 vs %0.05).

    Emir en iyi alış (LONG) / satış (SHORT) seviyesine `timeInForce=GTX`
    (post-only) ile konur. Karşı tarafa değecek olursa Binance emri
    reddeder, yani taker'a düşme riski yok.

    `wait_sec` içinde dolmazsa emir iptal edilir ve `ok=False,
    reason="unfilled"` döner — sinyal atlanır. Bu bilinçli bir filtre:
    momentum kovalayan agresif girişler kendiliğinden elenir.
    """
    cfg = load_config()
    symbol = symbol.upper()
    side_u = side.upper()
    if side_u in ("LONG", "BUY"):
        order_side, pos_side = "BUY", "LONG"
    elif side_u in ("SHORT", "SELL"):
        order_side, pos_side = "SELL", "SHORT"
    else:
        raise ValueError("side LONG/SHORT olmalı")

    if symbol not in [s.upper() for s in cfg.get("symbols") or []]:
        raise ValueError(f"{symbol} allowlist dışı — crypto_futures_config.json")
    if is_live_open_excluded(symbol):
        raise ValueError(f"{symbol} Binance Live açılış dışı (BTC/ETH/BNB kapalı)")

    lev = int(leverage or cfg.get("default_leverage") or 5)
    max_lev = int(cfg.get("max_leverage") or 20)
    if lev < 1 or lev > max_lev:
        raise ValueError(f"leverage 1–{max_lev} olmalı")
    margin = float(
        margin_usd if margin_usd is not None else cfg.get("default_margin_usd") or 20
    )
    if margin <= 0:
        raise ValueError("margin_usd > 0 olmalı")

    mtype = (margin_type or cfg.get("default_margin_type") or "ISOLATED").upper()
    timeout = float(
        wait_sec if wait_sec is not None else cfg.get("maker_wait_sec") or 90
    )
    dry = _is_dry(cfg)
    c = _client(cfg)

    state = load_state()
    if c.configured() and not dry:
        state = reconcile_shared_opens_with_binance(state, c)
    opens = state.get("open_positions") or []
    max_pos = int(cfg.get("max_open_positions") or 5)
    if not skip_max_positions and len(opens) >= max_pos:
        raise RuntimeError(f"max_open_positions={max_pos} doldu")

    prep = prepare_symbol(symbol, lev, mtype, client=c, dry_run=dry)
    filt = prep["filters"]
    tick = float(filt.get("tick_size") or 0.01)

    tick_mode = "down" if order_side == "BUY" else "up"
    if dry:
        px = c.mark_price(symbol)
        limit_px = _round_to_tick(px, tick, mode=tick_mode)
    else:
        book = c.book_ticker(symbol)
        limit_px = _round_to_tick(
            book["bid"] if order_side == "BUY" else book["ask"],
            tick,
            mode=tick_mode,
        )
    if limit_px <= 0:
        raise RuntimeError("limit fiyatı hesaplanamadı")

    qty = qty_from_notional(
        margin,
        limit_px,
        leverage=lev,
        step_size=filt["step_size"],
        min_qty=filt["min_qty"],
        min_notional=filt["min_notional"],
    )
    if qty <= 0:
        raise RuntimeError("qty hesaplanamadı (min lot / notional)")

    now_tr = datetime.now(_TZ_TR)
    maker_rate = get_maker_rate(c, symbol, cfg=cfg)
    result: dict = {
        "ok": True,
        "dry_run": dry,
        "entry_type": "maker",
        "symbol": symbol,
        "side": pos_side,
        "order_side": order_side,
        "leverage": lev,
        "margin_usd": margin,
        "margin_type": mtype,
        "limit_price": limit_px,
        "mark_price": limit_px,
        "qty": qty,
        "notional": round(qty * limit_px, 4),
        "entry_time_tr": now_tr.isoformat(),
        "testnet": c.testnet,
        "maker_rate": maker_rate,
    }

    if dry:
        result["order"] = {
            "orderId": f"DRYM-{int(time.time())}",
            "status": "DRY_RUN",
            "avgPrice": str(limit_px),
            "executedQty": str(qty),
        }
        print(
            f"[{LABEL}] DRY MAKER {pos_side} {symbol} qty={qty} "
            f"limit@{limit_px} margin=${margin:.2f} lev={lev}x"
        )
        filled_qty, avg_px, oid = qty, limit_px, result["order"]["orderId"]
    else:
        if not c.configured():
            raise BinanceFuturesError("API key yok — canlı emir atılamaz")
        order = c.new_order(
            symbol=symbol,
            side=order_side,
            type="LIMIT",
            timeInForce="GTX",  # post-only: karşı tarafa değerse reddedilir
            quantity=qty,
            price=limit_px,
        )
        oid = order.get("orderId")
        status = str(order.get("status") or "").upper()
        if status == "EXPIRED":
            # GTX reddi — fiyat karşı tarafa değecekti
            result.update({"ok": False, "reason": "post_only_rejected", "order": order})
            print(f"[{LABEL}] MAKER {symbol} post-only reddedildi (fiyat kaydı)")
            return result

        deadline = time.monotonic() + timeout
        filled_qty, avg_px = 0.0, limit_px
        while True:
            try:
                o = c.query_order(symbol, oid)
            except Exception as e:
                print(f"[{LABEL}] MAKER query {symbol}: {e}")
                o = {}
            status = str(o.get("status") or status).upper()
            filled_qty = float(o.get("executedQty") or 0)
            if float(o.get("avgPrice") or 0) > 0:
                avg_px = float(o["avgPrice"])
            if status == "FILLED":
                break
            if status in ("CANCELED", "EXPIRED", "REJECTED"):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(max(0.5, float(poll_sec)))

        if status != "FILLED":
            with contextlib.suppress(Exception):
                c.cancel_order(symbol, oid)
            if filled_qty <= 0:
                result.update({"ok": False, "reason": "unfilled", "order": o or order})
                print(
                    f"[{LABEL}] MAKER {symbol} {timeout:.0f}s içinde dolmadı — "
                    f"iptal, sinyal atlandı"
                )
                return result
            print(
                f"[{LABEL}] MAKER {symbol} kısmi dolum {filled_qty}/{qty} — "
                f"kalan iptal"
            )
        result["order"] = o or order
        print(
            f"[{LABEL}] LIVE MAKER {pos_side} {symbol} qty={filled_qty} "
            f"@{avg_px} orderId={oid} lev={lev}x"
        )

    qty = float(filled_qty or qty)
    fill_notional = round(qty * avg_px, 4)
    if dry:
        entry_fee, fee_src = estimate_fee(fill_notional, maker_rate), "estimate_maker"
    else:
        entry_fee, fee_src = commission_for_order(
            c, symbol, oid, notional=fill_notional, rate=maker_rate, cfg=cfg,
        )
    result.update({
        "qty": qty,
        "entry_price": avg_px,
        "notional": fill_notional,
        "entry_fee": entry_fee,
        "fee_source": fee_src,
        "filled": True,
    })

    pos = {
        "symbol": symbol,
        "side": pos_side,
        "qty": qty,
        "leverage": lev,
        "margin_usd": margin,
        "margin_type": mtype,
        "entry_price": avg_px,
        "notional": fill_notional,
        "entry_fee": entry_fee,
        "entry_type": "maker",
        "entry_time_tr": now_tr.isoformat(),
        "order_id": oid,
        "dry_run": dry,
        "testnet": c.testnet,
    }
    opens = [p for p in opens if p.get("symbol") != symbol]
    opens.append(pos)
    state["open_positions"] = opens
    save_state(state)
    return result


def dust_sweep(
    *,
    max_notional_usd: float | None = None,
    symbols: list[str] | None = None,
    client: BinanceFuturesClient | None = None,
) -> dict:
    """Binance'te kalan toz pozisyonları (|notional| ≤ eşik) MARKET reduceOnly kapat.

    Normal CR6 boyutu ~$150–225; varsayılan eşik $2.
    """
    cfg = load_config()
    dry = _is_dry(cfg)
    c = client or _client(cfg)
    max_n = float(
        max_notional_usd
        if max_notional_usd is not None
        else cfg.get("dust_max_notional_usd") or 2.0
    )
    allow = {s.upper() for s in (symbols or [])} if symbols else None
    closed: list[dict] = []
    errors: list[dict] = []
    skipped: list[dict] = []

    if dry or not c.configured():
        return {
            "ok": True,
            "dry_run": dry,
            "closed": [],
            "skipped": "dry_or_unconfigured",
            "max_notional_usd": max_n,
        }

    try:
        positions = get_positions(c)
    except Exception as e:
        return {"ok": False, "error": str(e), "closed": [], "max_notional_usd": max_n}

    for p in positions:
        sym = (p.get("symbol") or "").upper()
        if not sym:
            continue
        if allow is not None and sym not in allow:
            continue
        notion = abs(float(p.get("notional") or 0))
        amt = abs(float(p.get("position_amt") or 0))
        if amt <= 0 or notion <= 0:
            continue
        if notion > max_n:
            skipped.append({"symbol": sym, "notional": notion, "reason": "above_dust"})
            continue
        try:
            r = close_market(sym, sweep_dust=False)
            closed.append({
                "symbol": sym,
                "qty": r.get("qty"),
                "notional": notion,
                "pnl": r.get("pnl"),
                "order_id": (r.get("order") or {}).get("orderId"),
            })
            print(f"[{LABEL}] DUST SWEEP {sym} notional≈${notion:.4f} qty={r.get('qty')}")
        except Exception as e:
            errors.append({"symbol": sym, "notional": notion, "error": str(e)})
            print(f"[{LABEL}] DUST SWEEP hata {sym}: {e}")

    return {
        "ok": len(errors) == 0,
        "closed": closed,
        "errors": errors,
        "skipped_n": len(skipped),
        "max_notional_usd": max_n,
    }


def close_market(
    symbol: str,
    qty: float | None = None,
    *,
    sweep_dust: bool = True,
) -> dict:
    """Açık pozisyonu MARKET reduceOnly ile kapat.

    qty verilirse kısmi kapatma (CR6 vs manuel izolasyon).
    sweep_dust: kapanış sonrası aynı sembolde toz kaldıysa süpür.
    """
    cfg = load_config()
    symbol = symbol.upper()
    dry = _is_dry(cfg)
    c = _client(cfg)
    now_tr = datetime.now(_TZ_TR)

    # Önce borsadaki gerçek pozisyon
    chain_pos = None
    if c.configured() and not dry:
        for p in get_positions(c, symbol):
            if p["symbol"] == symbol:
                chain_pos = p
                break

    state = load_state()
    local = next(
        (p for p in (state.get("open_positions") or []) if p.get("symbol") == symbol),
        None,
    )

    if chain_pos:
        amt = abs(float(chain_pos["position_amt"]))
        close_side = "SELL" if chain_pos["side"] == "LONG" else "BUY"
        entry = float(chain_pos["entry_price"])
        mark = float(chain_pos["mark_price"])
        side = chain_pos["side"]
    elif local:
        amt = abs(float(local.get("qty") or 0))
        side = local.get("side") or "LONG"
        close_side = "SELL" if side == "LONG" else "BUY"
        entry = float(local.get("entry_price") or 0)
        mark = c.mark_price(symbol) if c.configured() else entry
    else:
        raise RuntimeError(f"{symbol} için açık pozisyon yok")

    if amt <= 0:
        raise RuntimeError(f"{symbol} qty=0")

    info = c.exchange_info(symbol) if c.configured() else {"symbols": []}
    filt = symbol_filters(info, symbol) if info.get("symbols") else {
        "step_size": 0.001, "min_qty": 0.0, "min_notional": 0.0,
    }
    from binance_futures_client import round_step
    close_amt = abs(float(qty)) if qty is not None else amt
    if close_amt > amt + 1e-12:
        close_amt = amt
    qty = round_step(close_amt, filt.get("step_size") or 0.001)

    result = {
        "ok": True,
        "dry_run": dry,
        "symbol": symbol,
        "side": side,
        "close_side": close_side,
        "qty": qty,
        "entry_price": entry,
        "mark_price": mark,
        "exit_time_tr": now_tr.isoformat(),
    }
    if side == "LONG":
        pnl_gross = (mark - entry) * qty
    else:
        pnl_gross = (entry - mark) * qty
    pnl_gross = round(pnl_gross, 4)
    exit_notional = round(qty * mark, 4)
    entry_fee_paid = float((local or {}).get("entry_fee") or 0)
    # Kısmi close: entry_fee oranla
    if local and amt > 1e-12 and qty + 1e-12 < amt:
        entry_fee_paid = round(entry_fee_paid * (qty / amt), 6)

    if dry:
        result["order"] = {"orderId": f"DRY-CLOSE-{int(time.time())}", "status": "DRY_RUN"}
        rate = get_taker_rate(c if c.configured() else None, symbol, cfg=cfg)
        exit_fee = estimate_fee(exit_notional, rate)
        fee_src = "estimate"
        print(f"[{LABEL}] DRY CLOSE {side} {symbol} qty={qty} gross≈{pnl_gross:+.4f}")
    else:
        order = c.new_order(
            symbol=symbol,
            side=close_side,
            type="MARKET",
            quantity=qty,
            reduceOnly="true",
        )
        result["order"] = order
        exit_fee, fee_src = commission_for_order(
            c, symbol, order.get("orderId"), notional=exit_notional, cfg=cfg,
        )
        print(f"[{LABEL}] LIVE CLOSE {side} {symbol} orderId={order.get('orderId')}")

    if entry_fee_paid <= 0:
        rate = get_taker_rate(c if c.configured() else None, symbol, cfg=cfg)
        entry_notional = round(qty * entry, 4)
        entry_fee_paid = estimate_fee(entry_notional, rate)
    commission = round(entry_fee_paid + exit_fee, 6)
    pnl_net = net_pnl(pnl_gross, commission)
    result["pnl_gross"] = pnl_gross
    result["commission"] = commission
    result["entry_fee"] = entry_fee_paid
    result["exit_fee"] = exit_fee
    result["fee_source"] = fee_src
    result["pnl_est"] = pnl_net  # geriye uyum: net
    result["pnl"] = pnl_net

    # state / history
    history = load_history()
    history.append({
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "entry_price": entry,
        "exit_price": mark,
        "pnl_gross": pnl_gross,
        "commission": commission,
        "entry_fee": entry_fee_paid,
        "exit_fee": exit_fee,
        "pnl": pnl_net,
        "leverage": (local or {}).get("leverage") or (chain_pos or {}).get("leverage"),
        "margin_usd": (local or {}).get("margin_usd"),
        "entry_time_tr": (local or {}).get("entry_time_tr"),
        "exit_time_tr": now_tr.isoformat(),
        "dry_run": dry,
        "order_id": result["order"].get("orderId"),
        "partial": qty + 1e-12 < amt,
    })
    save_history(history)
    # Kısmi kapatmada local qty düşür; tam kapatmada sil
    remains = amt - qty
    new_opens = []
    for p in (state.get("open_positions") or []):
        if p.get("symbol") != symbol:
            new_opens.append(p)
            continue
        if remains > 1e-12:
            p = dict(p)
            p["qty"] = remains
            old_fee = float(p.get("entry_fee") or 0)
            if amt > 1e-12 and old_fee > 0:
                p["entry_fee"] = round(old_fee * (remains / amt), 6)
            new_opens.append(p)
    state["open_positions"] = new_opens
    save_state(state)

    # Kısmi lot / yuvarlama tozu — aynı sembolde minik kalanı temizle
    if sweep_dust and not dry and c.configured():
        try:
            ds = dust_sweep(symbols=[symbol], client=c)
            if ds.get("closed"):
                result["dust_sweep"] = ds
        except Exception as e:
            print(f"[{LABEL}] dust_sweep {symbol}: {e}")
            result["dust_sweep_error"] = str(e)
    return result


def estimate_qty(symbol: str, margin_usd: float, leverage: int) -> dict:
    """Min lot / notional kontrolü — emir açmadan qty."""
    cfg = load_config()
    c = _client(cfg)
    symbol = symbol.upper()
    price = c.mark_price(symbol)
    info = c.exchange_info(symbol)
    filt = symbol_filters(info, symbol)
    qty = qty_from_notional(
        float(margin_usd),
        price,
        leverage=int(leverage),
        step_size=filt["step_size"],
        min_qty=filt["min_qty"],
        min_notional=filt["min_notional"],
    )
    return {
        "symbol": symbol,
        "price": price,
        "qty": qty,
        "notional": round(qty * price, 4) if qty else 0,
        "ok": qty > 0,
        "filters": filt,
    }


def status() -> dict:
    cfg = load_config()
    c = _client(cfg)
    dry = _is_dry(cfg)
    out = {
        "label": LABEL,
        "dry_run": dry,
        "testnet": c.testnet,
        "api_configured": c.configured(),
        "live_env": os.getenv("CRYPTO_FUTURES_LIVE", "false"),
        "symbols": cfg.get("symbols"),
        "default_leverage": cfg.get("default_leverage"),
        "default_margin_usd": cfg.get("default_margin_usd"),
        "local_state": load_state(),
    }
    try:
        c.ping()
        out["ping"] = "ok"
        out["server_time"] = c.server_time()
    except Exception as e:
        out["ping"] = f"err: {e}"
    if c.configured():
        try:
            out["usdt"] = usdt_balance(c)
            out["positions"] = get_positions(c)
        except Exception as e:
            out["account_error"] = str(e)
    # CR6 bloğu (ayrı state)
    try:
        from crypto_futures_cr6 import cr6_status_block
        out["cr6"] = cr6_status_block()
    except Exception as e:
        out["cr6"] = {"error": str(e)}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Binance Futures kaldıraçlı trader")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    po = sub.add_parser("open")
    po.add_argument("symbol")
    po.add_argument("side", choices=["LONG", "SHORT", "long", "short", "BUY", "SELL"])
    po.add_argument("--margin", type=float, default=None, help="Teminat USDT")
    po.add_argument("--leverage", type=int, default=None)
    po.add_argument("--margin-type", default=None, choices=["ISOLATED", "CROSSED"])

    pc = sub.add_parser("close")
    pc.add_argument("symbol")
    pc.add_argument("--qty", type=float, default=None, help="Kısmi kapatma miktarı")

    pd = sub.add_parser("dust", help="Toz pozisyonları süpür (|notional|≤eşik)")
    pd.add_argument("--max-notional", type=float, default=None, help="Varsayılan config/2 USDT")
    pd.add_argument("--symbol", action="append", dest="symbols", help="Sadece bu sembol(ler)")

    args = p.parse_args()
    try:
        if args.cmd == "status":
            print(json.dumps(status(), indent=2, ensure_ascii=False))
        elif args.cmd == "open":
            r = open_market(
                args.symbol,
                args.side,
                margin_usd=args.margin,
                leverage=args.leverage,
                margin_type=args.margin_type,
            )
            print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
        elif args.cmd == "close":
            r = close_market(args.symbol, qty=args.qty)
            print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
        elif args.cmd == "dust":
            r = dust_sweep(
                max_notional_usd=args.max_notional,
                symbols=args.symbols,
            )
            print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

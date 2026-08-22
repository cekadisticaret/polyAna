"""GPSUSDT — Binance USDT-M (fapi) piyasa + Isolated MARKET emir.

Sinyal `gpsusdt_signal.py`'de; bu katman yalnız kotasyon / dolum / emir.
CR6 / A139 allowlist'ine girmez — yalnız GPSUSDT.
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
    BinanceFuturesClient,
    BinanceFuturesError,
    qty_from_notional,
    round_step,
    symbol_filters,
)
from fee_utils import DEFAULT_TAKER_FEE, commission_for_order, get_taker_rate  # noqa: E402

SYMBOL = "GPSUSDT"
_FAPI = "https://fapi.binance.com"
_UA = {"User-Agent": "aiProject-gpsusdt/1.0"}
_INFO_TTL = 3600.0
_DEPTH_TTL = 2.0
_STATUS_TTL = 8.0
_info_cache: tuple[float, dict] | None = None
_depth_cache: tuple[float, dict] | None = None
_status_cache: tuple[float, dict] | None = None
_CONTROL = _DIR / "data" / "gpsusdt_live_control.json"


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
    try:
        c = BinanceFuturesClient()
        if c.configured():
            return float(get_taker_rate(c, SYMBOL))
    except Exception:
        pass
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


def load_control() -> dict:
    if not _CONTROL.exists():
        return {"live_paused": True}
    try:
        d = json.loads(_CONTROL.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"live_paused": True}
    except (json.JSONDecodeError, OSError):
        return {"live_paused": True}


def live_paused() -> bool:
    return bool(load_control().get("live_paused", True))


def configured() -> bool:
    try:
        return BinanceFuturesClient().configured()
    except Exception:
        return False


def live_enabled() -> bool:
    return configured() and not live_paused()


def _client() -> BinanceFuturesClient:
    return BinanceFuturesClient()


def _hedge(c: BinanceFuturesClient) -> bool:
    try:
        d = c.get("/fapi/v1/positionSide/dual", signed=True)
        return bool((d or {}).get("dualSidePosition"))
    except Exception:
        return False


def live_position_state(c: BinanceFuturesClient | None = None) -> tuple[str, dict | None]:
    """('open', row) | ('flat', None) | ('unknown', None)."""
    try:
        from binance_fapi_guard import fapi_blocked, position_state, write_position
        hit = position_state(SYMBOL)
        if hit:
            return hit
        return "unknown", None
    except Exception:
        return "unknown", None


def live_position(c: BinanceFuturesClient | None = None) -> dict | None:
    state, row = live_position_state(c)
    return row if state == "open" else None


def usdt_account(c: BinanceFuturesClient | None = None) -> dict | None:
    """Tüm USDT-M cüzdan — GPS / BIN aynı kaynak (`binance_um_wallet`)."""
    from binance_um_wallet import fetch
    return fetch()


def usdt_available(c: BinanceFuturesClient | None = None) -> float | None:
    acc = usdt_account(c)
    if acc is None:
        return None
    return acc["available"]


def live_status(*, force: bool = False) -> dict:
    global _status_cache
    now = time.time()
    if not force and _status_cache and now - _status_cache[0] < _STATUS_TTL:
        return dict(_status_cache[1])
    paused = live_paused()
    cfg = configured()
    out = {
        "enabled": bool(cfg and not paused),
        "paused": paused,
        "configured": cfg,
        "venue": "binance_usdm",
        "symbol": SYMBOL,
        "error": None if cfg else "keys_missing",
        "position": None,
        "usdt_available": None,
        "usdt_wallet": None,
        "usdt_equity": None,
        "usdt_unrealized": None,
        "wallet_at_live": None,
        "testnet": False,
    }
    ctrl = load_control()
    if cfg:
        try:
            c = _client()
            out["testnet"] = bool(c.testnet)
            acc = usdt_account(c)
            if acc:
                out["usdt_available"] = acc["available"]
                out["usdt_wallet"] = acc["wallet"]
                out["usdt_equity"] = acc["equity"]
                out["usdt_unrealized"] = acc["unrealized"]
                pinned = ctrl.get("wallet_at_live")
                if pinned is None and not paused:
                    pinned = acc["wallet"]
                    try:
                        ctrl["wallet_at_live"] = pinned
                        _CONTROL.parent.mkdir(parents=True, exist_ok=True)
                        _CONTROL.write_text(json.dumps(ctrl, ensure_ascii=False, indent=2), encoding="utf-8")
                    except OSError:
                        pass
                out["wallet_at_live"] = pinned
            pos = live_position(c)
            if pos:
                out["position"] = {
                    "amt": float(pos.get("positionAmt") or 0),
                    "entry": float(pos.get("entryPrice") or 0),
                    "unrealized": float(pos.get("unRealizedProfit") or 0),
                    "leverage": int(float(pos.get("leverage") or 0) or 0),
                    "margin_type": pos.get("marginType"),
                }
        except Exception as e:
            out["error"] = str(e)[:80]
    _status_cache = (now, out)
    return dict(out)


def prepare_live(c: BinanceFuturesClient, leverage: int) -> dict:
    plan = {"leverage": int(leverage), "margin_type": "ISOLATED"}
    plan["leverage_resp"] = c.set_leverage(SYMBOL, int(leverage))
    try:
        plan["margin_resp"] = c.set_margin_type(SYMBOL, "ISOLATED")
    except BinanceFuturesError as e:
        body = e.body if isinstance(e.body, dict) else {}
        if body.get("code") in (-4046, 4046) or "No need to change" in str(e):
            plan["margin_resp"] = {"skipped": True}
        else:
            raise
    return plan


def _fill_from_order(c: BinanceFuturesClient, order: dict, fallback_px: float, qty: float) -> tuple[float, float, dict]:
    """Gerçek dolum. avg/qty uydurulmaz — 0,0 = dolmadı."""
    avg = float(order.get("avgPrice") or 0)
    exe = float(order.get("executedQty") or 0)
    oid = order.get("orderId")
    status = str(order.get("status") or "")
    for _ in range(4):
        if exe > 0 and avg > 0:
            return avg, exe, order
        if status in ("CANCELED", "EXPIRED", "REJECTED"):
            break
        if not oid:
            break
        time.sleep(0.35)
        try:
            order = c.query_order(SYMBOL, int(oid))
            avg = float(order.get("avgPrice") or 0)
            exe = float(order.get("executedQty") or 0)
            status = str(order.get("status") or "")
        except Exception:
            break
    if exe > 0 and avg <= 0:
        try:
            trades = c.user_trades(SYMBOL, order_id=int(oid), limit=50) if oid else []
            cost = 0.0
            qsum = 0.0
            for t in trades or []:
                q = float(t.get("qty") or 0)
                p = float(t.get("price") or 0)
                cost += q * p
                qsum += q
            if qsum > 0 and cost > 0:
                return cost / qsum, qsum, order
        except Exception:
            pass
        if fallback_px > 0:
            return float(fallback_px), exe, order
    if exe <= 0:
        return 0.0, 0.0, order
    return avg, exe, order


def place_market(
    side: str,
    qty: float,
    *,
    reduce_only: bool = False,
    leverage: int = 10,
    fallback_px: float = 0.0,
) -> dict:
    """GPSUSDT Isolated MARKET — CR6 state'e yazmaz."""
    side_u = "BUY" if str(side).lower() in ("buy", "long") else "SELL"
    filt = exchange_filters()
    step = float(filt.get("step_size") or 1)
    qty = round_step(float(qty), step)
    if qty <= 0:
        return {"ok": False, "error": "qty_zero"}
    c = _client()
    if not c.configured():
        return {"ok": False, "error": "keys_missing"}
    if c.testnet:
        return {"ok": False, "error": "testnet_blocked"}
    try:
        if not reduce_only:
            prepare_live(c, leverage)
        req = {
            "symbol": SYMBOL,
            "side": side_u,
            "type": "MARKET",
            "quantity": qty,
        }
        if reduce_only:
            req["reduceOnly"] = "true"
        if _hedge(c):
            if reduce_only:
                req["positionSide"] = "LONG" if side_u == "SELL" else "SHORT"
            else:
                req["positionSide"] = "LONG" if side_u == "BUY" else "SHORT"
        order = c.new_order(**req)
        avg, exe, order = _fill_from_order(c, order, fallback_px, qty)
        if exe <= 0:
            return {"ok": False, "error": "fill_empty", "order_id": order.get("orderId")}
        if avg <= 0:
            avg = float(fallback_px or 0)
        if avg <= 0:
            return {"ok": False, "error": "fill_no_price", "order_id": order.get("orderId"), "qty": exe}
        notional = round(exe * avg, 8)
        fee, fee_src = commission_for_order(c, SYMBOL, order.get("orderId"), notional=notional)
        print(
            f"[GPSUSDT] LIVE {side_u} qty={exe} @{avg} "
            f"orderId={order.get('orderId')} reduceOnly={reduce_only} fee=${fee:.4f}",
            flush=True,
        )
        try:
            from binance_fapi_guard import write_position
            if not reduce_only:
                write_position(
                    SYMBOL,
                    amt=exe if side_u == "BUY" else -exe,
                    entry=avg,
                    mark=avg,
                    src="fill",
                )
        except Exception:
            pass
        return {
            "ok": True,
            "side": "buy" if side_u == "BUY" else "sell",
            "qty": exe,
            "price": round_px(avg),
            "notional": notional,
            "levels": None,
            "taker": True,
            "type": "MARKET",
            "order_id": order.get("orderId"),
            "status": order.get("status") or "FILLED",
            "fee": float(fee),
            "fee_src": fee_src,
            "reduce_only": reduce_only,
        }
    except BinanceFuturesError as e:
        return {"ok": False, "error": str(e)[:120]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _close_side_from_amt(amt: float) -> str:
    return "SELL" if amt > 0 else "BUY"


def close_live(*, fallback_px: float = 0.0, attempts: int = 4) -> dict:
    """Borsadaki GPSUSDT'yi MARKET reduceOnly ile bitene kadar kapat.

    Lot defterden değil positionAmt'ten. Kısmi kalırsa tekrar dener.
    Emir açmaz.
    """
    c = _client()
    if not c.configured():
        return {"ok": False, "error": "keys_missing"}
    if c.testnet:
        return {"ok": False, "error": "testnet_blocked"}
    filt = exchange_filters()
    step = float(filt.get("step_size") or 1)
    fees = 0.0
    closed_qty = 0.0
    last_oid = None
    last_px = float(fallback_px or 0)
    last_err = None

    for i in range(max(1, int(attempts))):
        state, row = live_position_state(c)
        if state == "unknown":
            return {"ok": False, "error": "bn_status_unknown"}
        if state == "flat" or row is None:
            return {
                "ok": True,
                "already_flat": i == 0,
                "price": round_px(last_px) if last_px else 0.0,
                "qty": closed_qty,
                "fee": round(fees, 6),
                "order_id": last_oid,
            }
        amt = float(row.get("positionAmt") or 0)
        raw = abs(amt)
        qty = round_step(raw, step)
        if abs(qty - raw) > 1e-9 and raw > 0:
            qty = raw
        if qty <= 0:
            return {
                "ok": True,
                "already_flat": True,
                "price": round_px(last_px) if last_px else 0.0,
                "qty": closed_qty,
                "fee": round(fees, 6),
            }
        if qty > raw + 1e-12:
            qty = raw
        side_u = _close_side_from_amt(amt)
        req = {
            "symbol": SYMBOL,
            "side": side_u,
            "type": "MARKET",
            "quantity": qty,
            "reduceOnly": "true",
        }
        ps = str(row.get("positionSide") or "BOTH").upper()
        if ps in ("LONG", "SHORT"):
            req["positionSide"] = ps
        try:
            order = c.new_order(**req)
        except BinanceFuturesError as e:
            last_err = str(e)[:120]
            time.sleep(0.35)
            state2, _ = live_position_state(c)
            if state2 == "flat":
                return {
                    "ok": True,
                    "already_flat": True,
                    "price": round_px(last_px) if last_px else 0.0,
                    "qty": closed_qty,
                    "fee": round(fees, 6),
                    "error": last_err,
                }
            continue
        except Exception as e:
            last_err = str(e)[:120]
            time.sleep(0.35)
            continue
        avg, exe, order = _fill_from_order(c, order, last_px or fallback_px, qty)
        if exe <= 0:
            last_err = "close_unfilled"
            time.sleep(0.35)
            continue
        if avg <= 0:
            avg = last_px or fallback_px
        last_px = avg
        closed_qty += exe
        last_oid = order.get("orderId")
        fee, _ = commission_for_order(c, SYMBOL, last_oid, notional=round(exe * avg, 8))
        fees += float(fee or 0)
        print(
            f"[GPSUSDT] LIVE CLOSE {side_u} qty={exe} @{avg} "
            f"orderId={last_oid} fee=${fee:.4f} try={i+1}",
            flush=True,
        )
        time.sleep(0.2)

    state, _ = live_position_state(c)
    if state == "flat":
        return {
            "ok": True,
            "price": round_px(last_px) if last_px else 0.0,
            "qty": closed_qty,
            "fee": round(fees, 6),
            "order_id": last_oid,
        }
    return {
        "ok": False,
        "error": last_err or ("still_open" if state == "open" else "bn_status_unknown"),
        "qty": closed_qty,
        "fee": round(fees, 6),
        "order_id": last_oid,
    }

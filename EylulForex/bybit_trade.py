"""Bybit XAUUSDT canlı emir — yalnız CEMBYBIT. CEM01'e dokunmaz.

Env: BYBIT_API_KEY + BYBIT_API_SECRET (Trade + Unified). Metals agreement şart.
Emir yalnız cron (`forex_paper.py`) içinden `sync_from_book` ile gider;
sayfa yenilemesi emir atmaz.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_ENV = _ROOT / ".env"
_CTRL = _DIR / "bybit_live_control.json"
_BASE = "https://api.bybit.com"
_SYMBOL = "XAUUSDT"
_RECV = "5000"

if _ENV.exists():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _k, _v = _k.strip(), _v.strip()
            if _v or not os.environ.get(_k):
                os.environ[_k] = _v


def _control() -> dict:
    try:
        return json.loads(_CTRL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def keys() -> tuple[str, str]:
    return (
        (os.environ.get("BYBIT_API_KEY") or "").strip(),
        (os.environ.get("BYBIT_API_SECRET") or "").strip(),
    )


def configured() -> bool:
    k, s = keys()
    return bool(k and s)


def live_enabled() -> bool:
    if not configured():
        return False
    return not bool(_control().get("live_paused", True))


def live_status() -> dict:
    return {
        "ok": True,
        "configured": configured(),
        "enabled": live_enabled(),
        "paused": bool(_control().get("live_paused", True)),
        "symbol": _control().get("symbol") or _SYMBOL,
        "leverage": int(_control().get("leverage") or 20),
        "margin_usdt": float(_control().get("margin_usdt") or 100),
    }


def _sign(secret: str, ts: str, key: str, payload: str) -> str:
    return hmac.new(
        secret.encode(), f"{ts}{key}{_RECV}{payload}".encode(), hashlib.sha256
    ).hexdigest()


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
    key, secret = keys()
    if not key or not secret:
        raise RuntimeError("bybit_keys_missing")
    ts = str(int(time.time() * 1000))
    query = ""
    data = None
    if method == "GET":
        if params:
            query = urllib.parse.urlencode(params)
        payload = query
    else:
        data = json.dumps(body or {}, separators=(",", ":")).encode()
        payload = data.decode()
    url = _BASE + path + (("?" + query) if query else "")
    headers = {
        "X-BAPI-API-KEY": key,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": _RECV,
        "X-BAPI-SIGN": _sign(secret, ts, key, payload),
        "X-BAPI-SIGN-TYPE": "2",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")[:400]
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(f"bybit_http_{e.code}:{raw[:160]}") from e
    if int(out.get("retCode", 1)) != 0:
        raise RuntimeError(str(out.get("retMsg") or "bybit_err")[:200])
    return out


def sign_metals_agreement() -> dict:
    try:
        return _request("POST", "/v5/user/agreement", body={"agree": True, "categoryV2": 1})
    except RuntimeError as e:
        msg = str(e).lower()
        if "already" in msg or "signed" in msg or "success" in msg:
            return {"ok": True, "already": True}
        raise


def set_hedge() -> None:
    try:
        _request("POST", "/v5/position/switch-mode", body={
            "category": "linear", "symbol": _SYMBOL, "mode": 3,
        })
    except RuntimeError as e:
        if "not modified" in str(e).lower() or "same" in str(e).lower():
            return
        raise


def set_leverage(lev: int) -> None:
    lv = str(int(lev))
    try:
        _request("POST", "/v5/position/set-leverage", body={
            "category": "linear", "symbol": _SYMBOL,
            "buyLeverage": lv, "sellLeverage": lv,
        })
    except RuntimeError as e:
        if "not modified" in str(e).lower() or "same" in str(e).lower():
            return
        raise


def positions() -> dict[str, float]:
    data = _request("GET", "/v5/position/list", params={
        "category": "linear", "symbol": _SYMBOL,
    })
    have = {"buy": 0.0, "sell": 0.0}
    for row in (data.get("result") or {}).get("list") or []:
        try:
            qty = float(row.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        side = str(row.get("side") or "").lower()
        if side == "buy":
            have["buy"] += qty
        elif side == "sell":
            have["sell"] += qty
    return have


def _qty(price: float) -> str:
    cfg = _control()
    lev = float(cfg.get("leverage") or 20)
    margin = float(cfg.get("margin_usdt") or 100)
    cap = float(cfg.get("max_qty") or 2)
    if price <= 0:
        raise RuntimeError("bybit_price")
    raw = margin * lev / price
    qty = max(0.001, min(cap, round(raw, 3)))
    return f"{qty:.3f}"


def _place(side: str, qty: str, *, reduce: bool, idx: int) -> dict:
    link = f"cembybit-{'c' if reduce else 'o'}-{side.lower()}-{int(time.time())}"
    return _request("POST", "/v5/order/create", body={
        "category": "linear",
        "symbol": _SYMBOL,
        "side": "Buy" if side == "buy" else "Sell",
        "orderType": "Market",
        "qty": qty,
        "timeInForce": "IOC",
        "positionIdx": idx,
        "reduceOnly": reduce,
        "orderLinkId": link[:36],
    })


_fee_cache: tuple[float, float] | None = None
_FEE_TTL = 3600.0
_FEE_FALLBACK = 0.00055  # Bybit VIP0 linear taker, API yoksa


def taker_fee_rate() -> float:
    """Hesaptaki XAUUSDT taker oranı. 1s cache."""
    global _fee_cache
    now = time.time()
    if _fee_cache and now - _fee_cache[0] < _FEE_TTL:
        return _fee_cache[1]
    if not configured():
        return _FEE_FALLBACK
    try:
        data = _request("GET", "/v5/account/fee-rate", params={
            "category": "linear", "symbol": _SYMBOL,
        })
        row = ((data.get("result") or {}).get("list") or [None])[0] or {}
        rate = float(row.get("takerFeeRate") or _FEE_FALLBACK)
        if rate <= 0:
            rate = _FEE_FALLBACK
        _fee_cache = (now, rate)
        return rate
    except Exception:
        return _FEE_FALLBACK


def ensure_ready() -> dict:
    sign_metals_agreement()
    set_hedge()
    set_leverage(int(_control().get("leverage") or 20))
    return {"ok": True}


def sync_from_book(book: dict | None, price: float | None = None) -> dict:
    """Sanal defterdeki AL/SAT'ı Bybit hedge pozisyonuna çevir. Cron only."""
    if not live_enabled():
        return {
            "ok": True,
            "skipped": "no_keys" if not configured() else "paused",
            **live_status(),
        }
    want = {str(p.get("side")) for p in (book or {}).get("positions") or []}
    if (book or {}).get("halted"):
        want = set()
    try:
        ensure_ready()
        have = positions()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], **live_status()}

    px = float(price or 0)
    if px <= 0:
        try:
            from bybit_xau import ticker
            px = float(ticker()["last"])
        except Exception:
            px = 0.0
    qty = _qty(px) if px else None
    actions: list[str] = []
    try:
        if "buy" in want and have["buy"] <= 0:
            if not qty:
                raise RuntimeError("bybit_qty")
            _place("buy", qty, reduce=False, idx=1)
            actions.append(f"open_buy {qty}")
        if "buy" not in want and have["buy"] > 0:
            _place("sell", f"{have['buy']:.3f}", reduce=True, idx=1)
            actions.append(f"close_buy {have['buy']:.3f}")
        if "sell" in want and have["sell"] <= 0:
            if not qty:
                raise RuntimeError("bybit_qty")
            _place("sell", qty, reduce=False, idx=2)
            actions.append(f"open_sell {qty}")
        if "sell" not in want and have["sell"] > 0:
            _place("buy", f"{have['sell']:.3f}", reduce=True, idx=2)
            actions.append(f"close_sell {have['sell']:.3f}")
    except Exception as e:
        return {
            "ok": False, "error": str(e)[:200], "did": actions,
            **live_status(),
        }
    return {"ok": True, "did": actions, "want": sorted(want), **live_status()}

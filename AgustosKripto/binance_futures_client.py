#!/usr/bin/env python3
"""Binance USD-M Futures (fapi) imzalı REST istemcisi.

Env:
  BINANCE_FUTURES_API_KEY
  BINANCE_FUTURES_API_SECRET
  BINANCE_FUTURES_TESTNET=true  → testnet endpoint

Gerçek emir atmaz; düşük seviye HTTP. Üst katman: crypto_futures_trader.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(os.path.dirname(_DIR), ".env")  # /root/aiProject/.env
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_MAINNET = "https://fapi.binance.com"
_TESTNET = "https://testnet.binancefuture.com"
# Ban sonrası okuma fırtınası olmasın: GET yalnız emir teyidi.
_GET_ALLOW = frozenset({"/fapi/v1/order"})


class BinanceFuturesError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class BinanceFuturesClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        testnet: bool | None = None,
        recv_window: int = 5000,
    ):
        self.api_key = (api_key or os.getenv("BINANCE_FUTURES_API_KEY") or "").strip()
        self.api_secret = (api_secret or os.getenv("BINANCE_FUTURES_API_SECRET") or "").strip()
        if testnet is None:
            testnet = os.getenv("BINANCE_FUTURES_TESTNET", "false").lower() in (
                "1", "true", "yes",
            )
        self.base = _TESTNET if testnet else _MAINNET
        self.testnet = bool(testnet)
        self.recv_window = int(recv_window)

    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    # ── low-level ─────────────────────────────────────────────
    def _sign(self, query: str) -> str:
        return hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        *,
        signed: bool = False,
        ignore_ban: bool = False,
        api_key: bool = False,
    ) -> Any:
        params = dict(params or {})
        if method.upper() == "GET" and path not in _GET_ALLOW:
            raise BinanceFuturesError(f"fapi GET kapalı: {path}", status=0)
        headers = {"User-Agent": "aiProject-futures/1.0", "Accept": "application/json"}
        if signed:
            if not self.configured():
                raise BinanceFuturesError(
                    "BINANCE_FUTURES_API_KEY / BINANCE_FUTURES_API_SECRET eksik"
                )
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = self.recv_window
            query = urllib.parse.urlencode(params, doseq=True)
            query = f"{query}&signature={self._sign(query)}"
            headers["X-MBX-APIKEY"] = self.api_key
        else:
            query = urllib.parse.urlencode(params, doseq=True) if params else ""
            if api_key and self.api_key:
                headers["X-MBX-APIKEY"] = self.api_key

        url = f"{self.base}{path}"
        if "fapi.binance.com" in str(self.base):
            try:
                import sys
                _root = os.path.dirname(_DIR)
                if _root not in sys.path:
                    sys.path.insert(0, _root)
                from binance_fapi_guard import ban_msg, fapi_blocked, note_418
                if fapi_blocked() and not ignore_ban:
                    raise BinanceFuturesError(ban_msg(), status=418)
            except BinanceFuturesError:
                raise
            except Exception:
                note_418 = None  # type: ignore
        else:
            note_418 = None  # type: ignore
        if query and method.upper() == "GET":
            url = f"{url}?{query}"
            data = None
        elif query and method.upper() != "GET":
            data = query.encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = None

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            from binance_fapi_guard import allow_fapi
            with allow_fapi():
                with urllib.request.urlopen(req, timeout=20) as r:
                    raw = r.read().decode()
                    return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = body
            if e.code == 418 and note_418:
                note_418(str(parsed))
            raise BinanceFuturesError(
                f"HTTP {e.code}: {parsed}", status=e.code, body=parsed
            ) from e

    def get(self, path: str, params: dict | None = None, *, signed: bool = False,
            ignore_ban: bool = False) -> Any:
        return self._request("GET", path, params, signed=signed, ignore_ban=ignore_ban)

    def post(self, path: str, params: dict | None = None, *, signed: bool = False,
             api_key: bool = False) -> Any:
        return self._request("POST", path, params, signed=signed, api_key=api_key)

    def put(self, path: str, params: dict | None = None, *, signed: bool = False,
            api_key: bool = False) -> Any:
        return self._request("PUT", path, params, signed=signed, api_key=api_key)

    def delete(self, path: str, params: dict | None = None, *, signed: bool = False) -> Any:
        return self._request("DELETE", path, params, signed=signed)

    def listen_key_create(self) -> str:
        d = self.post("/fapi/v1/listenKey", api_key=True) or {}
        key = str(d.get("listenKey") or "")
        if not key:
            raise BinanceFuturesError("listenKey yok", body=d)
        return key

    def listen_key_keepalive(self) -> dict:
        return self.put("/fapi/v1/listenKey", api_key=True) or {}

    # ── public market ─────────────────────────────────────────
    def ping(self) -> dict:
        return {}

    def server_time(self) -> int:
        return int(time.time() * 1000)

    def exchange_info(self, symbol: str | None = None) -> dict:
        return {"symbols": []}

    def mark_price(self, symbol: str) -> float:
        _root = os.path.dirname(_DIR)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import get_mark
        px = get_mark(symbol)
        if not px:
            raise BinanceFuturesError(f"mark WS yok: {symbol}", status=0)
        return float(px)

    def ticker_price(self, symbol: str) -> float:
        _root = os.path.dirname(_DIR)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import get_last, get_mark
        px = get_last(symbol) or get_mark(symbol)
        if not px:
            raise BinanceFuturesError(f"last WS yok: {symbol}", status=0)
        return float(px)

    def book_ticker(self, symbol: str) -> dict:
        _root = os.path.dirname(_DIR)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import get_book
        hit = get_book(symbol)
        if not hit or not (hit.get("bid") or hit.get("ask")):
            raise BinanceFuturesError(f"book WS yok: {symbol}", status=0)
        return {
            "symbol": (symbol or "").upper(),
            "bid": float(hit.get("bid") or 0),
            "ask": float(hit.get("ask") or 0),
            "bid_qty": float(hit.get("bid_qty") or 0),
            "ask_qty": float(hit.get("ask_qty") or 0),
        }

    def premium_index(self, symbol: str | None = None) -> Any:
        if not symbol:
            return {}
        _root = os.path.dirname(_DIR)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import ws_premium
        return ws_premium(symbol) or {}

    def funding_rate_history(self, symbol: str, limit: int = 100) -> list:
        return []

    def funding_info(self) -> list:
        return []

    def klines(self, symbol: str, interval: str = "15m", limit: int = 100) -> list:
        _root = os.path.dirname(_DIR)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import public_klines
        return public_klines(symbol, interval, int(limit)) or []

    # ── account / trade (signed) ──────────────────────────────
    def balance(self) -> list:
        return []

    def account(self, *, ignore_ban: bool = False) -> dict:
        if _DIR not in sys.path:
            sys.path.insert(0, _DIR)
        from binance_um_wallet import fetch
        w = fetch() or {}
        return {
            "totalWalletBalance": w.get("wallet") or 0,
            "availableBalance": w.get("available") or 0,
            "totalUnrealizedProfit": w.get("unrealized") or 0,
        }

    def position_risk(self, symbol: str | None = None) -> list:
        _root = os.path.dirname(_DIR)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import cached_positions
        return cached_positions(symbol)

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        return self.post(
            "/fapi/v1/leverage",
            {"symbol": symbol.upper(), "leverage": int(leverage)},
            signed=True,
        )

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> dict:
        """ISOLATED | CROSSED — zaten aynıysa Binance hata döner, üst katman yutar."""
        return self.post(
            "/fapi/v1/marginType",
            {"symbol": symbol.upper(), "marginType": margin_type.upper()},
            signed=True,
        )

    def new_order(self, **params) -> dict:
        if "symbol" in params:
            params["symbol"] = str(params["symbol"]).upper()
        return self.post("/fapi/v1/order", params, signed=True)

    def query_order(self, symbol: str, order_id: int | None = None, **extra) -> dict:
        """GET /fapi/v1/order — emir durumu (NEW / FILLED / EXPIRED …)."""
        params: dict = {"symbol": symbol.upper(), **extra}
        if order_id is not None:
            params["orderId"] = int(order_id)
        return self.get("/fapi/v1/order", params, signed=True)

    def cancel_order(self, symbol: str, order_id: int | None = None, **extra) -> dict:
        params = {"symbol": symbol.upper(), **extra}
        if order_id is not None:
            params["orderId"] = int(order_id)
        return self.delete("/fapi/v1/order", params, signed=True)

    def cancel_all(self, symbol: str) -> Any:
        return self.delete(
            "/fapi/v1/allOpenOrders", {"symbol": symbol.upper()}, signed=True
        )

    def open_orders(self, symbol: str | None = None) -> list:
        params = {"symbol": symbol.upper()} if symbol else None
        return self.get("/fapi/v1/openOrders", params, signed=True)

    def commission_rate(self, symbol: str) -> dict:
        """GET /fapi/v1/commissionRate — makerCommissionRate / takerCommissionRate."""
        return self.get(
            "/fapi/v1/commissionRate",
            {"symbol": symbol.upper()},
            signed=True,
        )

    def user_trades(
        self,
        symbol: str,
        *,
        order_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list:
        """GET /fapi/v1/userTrades — her satırda commission / realizedPnl."""
        params: dict = {"symbol": symbol.upper(), "limit": int(limit)}
        if order_id is not None:
            params["orderId"] = int(order_id)
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        return self.get("/fapi/v1/userTrades", params, signed=True)

    def income(
        self,
        *,
        symbol: str | None = None,
        income_type: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list:
        """GET /fapi/v1/income — COMMISSION / REALIZED_PNL vb."""
        params: dict = {"limit": int(limit)}
        if symbol:
            params["symbol"] = symbol.upper()
        if income_type:
            params["incomeType"] = income_type
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        return self.get("/fapi/v1/income", params, signed=True)


def symbol_filters(exchange_info: dict, symbol: str) -> dict:
    """LOT_SIZE / PRICE_FILTER / MIN_NOTIONAL özet."""
    sym = symbol.upper()
    out = {
        "symbol": sym,
        "status": None,
        "step_size": 0.001,
        "min_qty": 0.001,
        "tick_size": 0.01,
        "min_notional": 5.0,
    }
    for s in exchange_info.get("symbols") or []:
        if s.get("symbol") != sym:
            continue
        out["status"] = s.get("status")
        for f in s.get("filters") or []:
            ft = f.get("filterType")
            if ft == "LOT_SIZE":
                out["step_size"] = float(f.get("stepSize") or out["step_size"])
                out["min_qty"] = float(f.get("minQty") or out["min_qty"])
            elif ft == "PRICE_FILTER":
                out["tick_size"] = float(f.get("tickSize") or out["tick_size"])
            elif ft in ("MIN_NOTIONAL", "NOTIONAL"):
                out["min_notional"] = float(
                    f.get("notional") or f.get("minNotional") or out["min_notional"]
                )
        break
    return out


def round_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    # adım ondalığına göre aşağı yuvarla
    precision = max(0, len(f"{step:.10f}".rstrip("0").split(".")[-1]))
    n = int(value / step)
    return round(n * step, precision)


def qty_from_notional(
    notional_usd: float,
    price: float,
    *,
    leverage: int = 1,
    step_size: float = 0.001,
    min_qty: float = 0.001,
    min_notional: float = 5.0,
) -> float:
    """Margin (notional_usd) * leverage / price → lot step'e yuvarlanmış qty."""
    if price <= 0 or notional_usd <= 0:
        return 0.0
    qty = (notional_usd * max(1, int(leverage))) / price
    qty = round_step(qty, step_size)
    if qty < min_qty:
        return 0.0
    if qty * price < min_notional:
        # min notional için yukarı adım dene
        need = min_notional / price
        qty = round_step(need + step_size, step_size)
        if qty * price < min_notional:
            qty = round_step(need + step_size * 2, step_size)
    return qty

#!/usr/bin/env python3
"""
Binance USDT-M Futures API — HMAC imzalı istekler.
Sadece urllib + hmac kullanır, harici kütüphane yok.
"""

import hashlib
import hmac
import json
import time
import urllib.request
import urllib.parse

try:
    from binance_config import API_KEY, API_SECRET
except ImportError:
    API_KEY = API_SECRET = ""

BASE_URL = "https://fapi.binance.com"


def _sign(params):
    query = urllib.parse.urlencode(params)
    sig = hmac.new(
        API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    params["signature"] = sig
    return params


def _request(method, path, params=None, signed=True):
    if params is None:
        params = {}
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 10000

    if signed:
        params = _sign(params)

    query = urllib.parse.urlencode(params)
    if method == "GET":
        url = f"{BASE_URL}{path}?{query}"
        data = None
    else:
        url = f"{BASE_URL}{path}"
        data = query.encode()

    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "X-MBX-APIKEY": API_KEY,
            "Content-Type": "application/x-www-form-urlencoded",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            err = json.loads(body)
            raise Exception(err.get("msg", body))
        except json.JSONDecodeError:
            raise Exception(body[:200] if body else str(e))


def get_account():
    return _request("GET", "/fapi/v2/account")


def get_balance():
    acc = get_account()
    for a in acc.get("assets", []):
        if a["asset"] == "USDT":
            avail = float(a.get("availableBalance", 0) or 0)
            total = float(a.get("walletBalance", 0) or a.get("crossWalletBalance", 0) or avail)
            return avail, total
    return 0.0, 0.0


def get_positions():
    data = _request("GET", "/fapi/v2/positionRisk")
    return [p for p in data if float(p.get("positionAmt", 0)) != 0]


def set_leverage(symbol, leverage):
    return _request("POST", "/fapi/v1/leverage", {
        "symbol": symbol,
        "leverage": leverage,
    })


def place_market_order(symbol, side, quantity):
    return _request("POST", "/fapi/v1/order", {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": quantity,
    })


def place_stop_market(symbol, side, stop_price, close_position=True):
    """Algo Order API — STOP_MARKET (Binance 2025 değişikliği)."""
    return _request("POST", "/fapi/v1/algoOrder", {
        "algoType": "CONDITIONAL",
        "symbol": symbol,
        "side": side,
        "type": "STOP_MARKET",
        "triggerPrice": stop_price,
        "closePosition": "true" if close_position else "false",
    })


def place_take_profit_market(symbol, side, stop_price, close_position=True):
    """Algo Order API — TAKE_PROFIT_MARKET (Binance 2025 değişikliği)."""
    return _request("POST", "/fapi/v1/algoOrder", {
        "algoType": "CONDITIONAL",
        "symbol": symbol,
        "side": side,
        "type": "TAKE_PROFIT_MARKET",
        "triggerPrice": stop_price,
        "closePosition": "true" if close_position else "false",
    })


def get_open_algo_orders(symbol=None):
    params = {}
    if symbol:
        params["symbol"] = symbol
    return _request("GET", "/fapi/v1/openAlgoOrders", params)


def cancel_algo_order(algo_id=None, client_algo_id=None):
    params = {}
    if algo_id is not None:
        params["algoId"] = algo_id
    elif client_algo_id:
        params["clientAlgoId"] = client_algo_id
    else:
        raise ValueError("algoId or clientAlgoId required")
    return _request("DELETE", "/fapi/v1/algoOrder", params)


def get_user_trades(symbol, limit=10):
    """Son işlemleri getir (SL/TP kapanış fiyatı için)."""
    return _request("GET", "/fapi/v1/userTrades", {"symbol": symbol, "limit": limit})


def cancel_all_orders(symbol):
    _request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol})
    for algo in get_open_algo_orders(symbol):
        try:
            cancel_algo_order(algo_id=algo.get("algoId"))
        except Exception:
            pass


def get_exchange_info(symbol=None):
    params = {}
    if symbol:
        params["symbol"] = symbol
    return _request("GET", "/fapi/v1/exchangeInfo", params, signed=False)


def round_quantity(symbol, qty):
    """Binance lot size filtresine uygun yuvarla."""
    try:
        info = get_exchange_info()
        for s in info.get("symbols", []):
            if s["symbol"] == symbol:
                for f in s.get("filters", []):
                    if f["filterType"] == "LOT_SIZE":
                        step = float(f["stepSize"])
                        if step >= 1:
                            return int(qty)
                        return round(qty - (qty % step), 8)
    except Exception:
        pass
    return round(qty, 5)


def round_price(symbol, price, direction="nearest"):
    """
    Binance PRICE_FILTER tickSize'a uygun yuvarla.
    direction: "nearest" | "up" | "down"
    SL için: LONG → "down" (daha geniş), SHORT → "up" (daha geniş)
    """
    import math
    try:
        info = get_exchange_info()
        for s in info.get("symbols", []):
            if s["symbol"] == symbol:
                for f in s.get("filters", []):
                    if f["filterType"] == "PRICE_FILTER":
                        tick = float(f["tickSize"])
                        prec = len(str(tick).rstrip("0").split(".")[-1]) if "." in str(tick) else 0
                        if tick >= 1:
                            if direction == "up":
                                return int(math.ceil(price / tick) * tick)
                            elif direction == "down":
                                return int(math.floor(price / tick) * tick)
                            return int(price)
                        if direction == "up":
                            return round(math.ceil(price / tick) * tick, prec)
                        elif direction == "down":
                            return round(math.floor(price / tick) * tick, prec)
                        return round(round(price / tick) * tick, prec)
    except Exception:
        pass
    return round(price, 2)

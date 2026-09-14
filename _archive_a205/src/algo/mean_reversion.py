"""A2#05 — Mean Reversion (Z-Score) only."""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
FUTURES = "https://fapi.binance.com"


def _std(vals: list[float]) -> tuple[float, float]:
    n = len(vals)
    if n < 2:
        return 0.0, (sum(vals) / n if n else 0.0)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / n
    return math.sqrt(var), mean


def fetch_klines(pair: str, interval: str = "1h", limit: int = 200) -> list[dict]:
    url = f"{FUTURES}/fapi/v1/klines?" + urllib.parse.urlencode(
        {"symbol": pair, "interval": interval, "limit": limit}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "2.Poly/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
    if not isinstance(data, list):
        code = data.get("code") if isinstance(data, dict) else None
        msg = data.get("msg") if isinstance(data, dict) else data
        raise RuntimeError(f"binance klines hata {pair} {interval} code={code} msg={msg}")
    return [
        {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]), "v": float(x[5])}
        for x in data
    ]


def mean_reversion(kl: list[dict]) -> str:
    d = mean_reversion_detail(kl)
    return d["signal"]


def mean_reversion_detail(kl: list[dict]) -> dict:
    c = [k["c"] for k in kl]
    if len(c) < 20:
        return {"signal": "NEUTRAL", "z": 0.0, "mean": c[-1] if c else 0.0, "std": 0.0, "close": c[-1] if c else 0.0}
    std, mean = _std(c[-20:])
    close = c[-1]
    if not std:
        return {"signal": "NEUTRAL", "z": 0.0, "mean": mean, "std": 0.0, "close": close}
    z = (close - mean) / std
    if z < -1.5:
        sig = "UP"
    elif z > 1.5:
        sig = "DOWN"
    elif z < -0.5:
        sig = "UP"
    elif z > 0.5:
        sig = "DOWN"
    else:
        sig = "NEUTRAL"
    return {"signal": sig, "z": round(z, 3), "mean": round(mean, 2), "std": round(std, 4), "close": round(close, 2)}

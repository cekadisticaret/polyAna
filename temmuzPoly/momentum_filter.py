"""Momentum filtresi — 5m (102) ve 1h (Analiz 5/10)."""
import os
import urllib.parse
import urllib.request

MOMENTUM_BARS = 3
MOMENTUM_FILTER = os.getenv(
    "PM_MOMENTUM_FILTER",
    os.getenv("PM_5M_102_MOMENTUM_FILTER", "true"),
).lower() in ("1", "true", "yes")


def fetch_klines(symbol: str, interval: str, limit: int = 10) -> list[dict]:
    qs = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    req = urllib.request.Request(
        f"https://fapi.binance.com/fapi/v1/klines?{qs}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = __import__("json").loads(r.read())
    return [{"open": float(k[1]), "close": float(k[4])} for k in raw]


def fetch_klines_5m(symbol: str, limit: int = 10) -> list[dict]:
    return fetch_klines(symbol, "5m", limit)


def fetch_klines_1h(symbol: str, limit: int = 10) -> list[dict]:
    return fetch_klines(symbol, "1h", limit)


def recent_momentum(klines: list[dict], n: int = MOMENTUM_BARS) -> str:
    if len(klines) < n + 1:
        return "MIXED"
    closed = klines[-(n + 1):-1]
    ups = sum(1 for k in closed if k["close"] >= k["open"])
    if ups >= n - 1:
        return "UP"
    if ups <= 1:
        return "DOWN"
    return "MIXED"


def _skip_text(direction: str, momentum: str, interval_label: str) -> str | None:
    if direction == "DOWN" and momentum == "UP":
        return f"momentum filtresi: son {MOMENTUM_BARS} {interval_label} mum yükseliş, DOWN engellendi"
    if direction == "UP" and momentum == "DOWN":
        return f"momentum filtresi: son {MOMENTUM_BARS} {interval_label} mum düşüş, UP engellendi"
    return None


def momentum_skip_reason_5m(direction: str | None, symbol: str) -> str | None:
    if not MOMENTUM_FILTER or not direction:
        return None
    try:
        momentum = recent_momentum(fetch_klines_5m(symbol, MOMENTUM_BARS + 2))
    except Exception:
        return None
    return _skip_text(direction, momentum, "5m")


def momentum_skip_reason_1h(direction: str | None, symbol: str) -> str | None:
    if not MOMENTUM_FILTER or not direction:
        return None
    try:
        momentum = recent_momentum(fetch_klines_1h(symbol, MOMENTUM_BARS + 2))
    except Exception:
        return None
    return _skip_text(direction, momentum, "1h")


def momentum_skip_reason(direction: str | None, symbol: str) -> str | None:
    """Geriye uyumluluk — varsayılan 1h (Analiz 5/10)."""
    return momentum_skip_reason_1h(direction, symbol)

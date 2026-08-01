"""Jesse GoldenCross TA → saatlik Polymarket UP/DOWN sinyali (1h mum).

Jesse dokumantasyonundaki ornek strateji (EMA 8/21) — jesse.indicators kullanir;
jesse cekirdek koduna dokunulmaz.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_DIR = Path(__file__).resolve().parent
_POLY = _DIR.parent / "temmuzPoly"
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))
if str(_POLY) not in sys.path:
    sys.path.insert(0, str(_POLY))

from jesse.indicators import ema, rsi  # noqa: E402 — jesse kurulumu gerekli
from a3a8_signal_mode import a8_direction  # noqa: E402

FAST_EMA = 8
SLOW_EMA = 21
RSI_PERIOD = 14


@dataclass
class JessePmSignal:
    symbol: str
    predicted_dir: str
    current_price: float
    rsi: float
    ema_fast: float
    ema_slow: float
    golden_cross: bool
    prob_up: float
    prob_down: float
    trend: str


def _fetch_candles(symbol: str, limit: int = 120) -> np.ndarray:
    url = (
        f"https://fapi.binance.com/fapi/v1/klines?"
        f"symbol={symbol}&interval=1h&limit={limit}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.load(resp)
    # Jesse format: [timestamp, open, close, high, low, volume]
    rows = []
    for k in raw:
        rows.append([
            int(k[0]),
            float(k[1]),
            float(k[4]),
            float(k[2]),
            float(k[3]),
            float(k[5]),
        ])
    return np.array(rows, dtype=np.float64)


def predict_pm_direction(symbol: str) -> JessePmSignal | None:
    """Jesse GoldenCross: should_long = EMA8 > EMA21."""
    try:
        candles = _fetch_candles(symbol)
    except Exception as exc:
        print(f"[analiz8_signal] {symbol} veri hatasi: {exc}")
        return None

    if len(candles) < SLOW_EMA + 5:
        return None

    price = float(candles[-1, 2])
    ema_fast = float(ema(candles, FAST_EMA))
    ema_slow = float(ema(candles, SLOW_EMA))
    rsi_val = float(rsi(candles, RSI_PERIOD))
    golden = ema_fast > ema_slow

    klines = [{"close": float(c[2]), "volume": float(c[5])} for c in candles]
    predicted = a8_direction(klines)
    if predicted is None:
        return None

    spread = abs(ema_fast - ema_slow) / price if price else 0
    strength = min(spread * 500 + (abs(rsi_val - 50) / 100), 1.0)
    prob_up = 0.5 + strength / 2 if predicted == "UP" else 0.5 - strength / 2
    prob_down = 1.0 - prob_up

    if ema_fast > ema_slow and price > ema_fast:
        trend = "YUKARI"
    elif ema_fast < ema_slow and price < ema_fast:
        trend = "ASAGI"
    else:
        trend = "NOTR"

    return JessePmSignal(
        symbol=symbol,
        predicted_dir=predicted,
        current_price=price,
        rsi=rsi_val,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        golden_cross=golden,
        prob_up=prob_up,
        prob_down=prob_down,
        trend=trend,
    )

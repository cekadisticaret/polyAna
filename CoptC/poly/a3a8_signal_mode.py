"""A3 / A8 sinyal modu — sıkı (filtreli) vs gevşek (her saat yön).

Anahtar: pm_system_control.json → "a3a8_signal_strict"
  true  — sıkı (filtreli): A3 entry bias veya 3/3 momentum + RSI teyit;
          A8 EMA kesişim veya geniş spread + RSI teyit (~%25–35 bar, saf sıkı ~%0–5)
  false — gevşek: A3 skor oylaması · A8 EMA pozisyonu (her saat yön)

Geri almak: false yap veya dashboard POST {"a3a8_signal_strict": false}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONTROL_FILE = os.path.join(_DIR, "pm_system_control.json")
_TZ_TR = timezone(timedelta(hours=3))

CONTROL_KEY = "a3a8_signal_strict"
_JESSE_FAST = 8
_JESSE_SLOW = 21
_A3_BUY_RSI = 30
_A3_SHORT_RSI = 70
# Sıkı mod fallback — oylama 3/3 + RSI teyit (saat başına ~0.7–1 işlem / 3 sembol)
_A3_FILTER_RSI_UP = 63
_A3_FILTER_RSI_DN = 37
_A8_FILTER_SPREAD = 0.0028  # EMA8–21 aralığı ≥ %0.28
_A8_FILTER_RSI_UP = 63
_A8_FILTER_RSI_DN = 37


def _load_control() -> dict:
    if not os.path.exists(_CONTROL_FILE):
        return {}
    try:
        with open(_CONTROL_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_control(data: dict) -> None:
    with open(_CONTROL_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_a3a8_strict(default: bool = True) -> bool:
    c = _load_control()
    if CONTROL_KEY not in c:
        return default
    return bool(c[CONTROL_KEY])


def set_a3a8_strict(strict: bool, *, source: str = "manual") -> dict:
    data = _load_control()
    data[CONTROL_KEY] = bool(strict)
    data["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    data["updated_by"] = source
    _save_control(data)
    return signal_mode_status()


def signal_mode_status() -> dict:
    strict = is_a3a8_strict()
    return {
        CONTROL_KEY: strict,
        "a3a8_signal_mode": "strict" if strict else "loose",
        "a3a8_signal_mode_label": "sıkı (filtreli)" if strict else "gevşek (her saat)",
    }


def _ema_last(closes: np.ndarray, period: int) -> float:
    if len(closes) < period:
        return float(closes[-1]) if len(closes) else 0.0
    k = 2.0 / (period + 1)
    ema = float(np.mean(closes[:period]))
    for c in closes[period:]:
        ema = float(c) * k + ema * (1 - k)
    return ema


def _ema_series(arr: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    if len(arr) < period:
        return out
    k = 2.0 / (period + 1)
    ema = float(np.mean(arr[:period]))
    out[period - 1] = ema
    for i in range(period, len(arr)):
        ema = float(arr[i]) * k + ema * (1 - k)
        out[i] = ema
    return out


def _rsi_last_two(closes: np.ndarray, period: int = 14) -> tuple[float, float]:
    if len(closes) < period + 2:
        return 50.0, 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    rsis: list[float] = []
    for i in range(period, len(deltas) + 1):
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100.0 - (100.0 / (1.0 + rs)))
        if i < len(deltas):
            g, l = gains[i], losses[i]
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period
    if len(rsis) < 2:
        v = rsis[-1] if rsis else 50.0
        return v, v
    return float(rsis[-2]), float(rsis[-1])


def _macd_hist_last(closes: np.ndarray) -> float:
    if len(closes) < 35:
        return 0.0
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    macd = ema12 - ema26
    valid = macd[~np.isnan(macd)]
    if len(valid) < 10:
        return 0.0
    sig = _ema_series(valid, 9)
    if np.isnan(sig[-1]):
        return 0.0
    return float(valid[-1] - sig[-1])


def a3_direction_strict(klines: list[dict]) -> str | None:
    if len(klines) < 30:
        return None
    closes = np.array([k["close"] for k in klines], dtype=np.float64)
    vol = float(klines[-1].get("volume") or 0.0)
    rsi_prev, rsi = _rsi_last_two(closes)
    tema = _ema_last(closes, 9)
    tema_prev = _ema_last(closes[:-1], 9) if len(closes) > 1 else tema
    tema_rising = tema > tema_prev
    bb_mid = float(np.mean(closes[-20:])) if len(closes) >= 20 else float(closes[-1])

    long_bias = bool(
        rsi_prev <= _A3_BUY_RSI < rsi
        and tema <= bb_mid
        and tema_rising
        and vol > 0
    )
    short_bias = bool(
        rsi_prev <= _A3_SHORT_RSI < rsi
        and tema > bb_mid
        and not tema_rising
        and vol > 0
    )
    if long_bias:
        return "UP"
    if short_bias:
        return "DOWN"
    return None


def a3_direction_loose(klines: list[dict]) -> str | None:
    if len(klines) < 30:
        return None
    closes = np.array([k["close"] for k in klines], dtype=np.float64)
    vol = float(klines[-1].get("volume") or 0.0)
    rsi_prev, rsi = _rsi_last_two(closes)
    tema = _ema_last(closes, 9)
    tema_prev = _ema_last(closes[:-1], 9) if len(closes) > 1 else tema
    tema_rising = tema > tema_prev
    macd_bull = _macd_hist_last(closes) > 0
    bb_mid = float(np.mean(closes[-20:])) if len(closes) >= 20 else float(closes[-1])

    long_bias = bool(
        rsi_prev <= _A3_BUY_RSI < rsi
        and tema <= bb_mid
        and tema_rising
        and vol > 0
    )
    short_bias = bool(
        rsi_prev <= _A3_SHORT_RSI < rsi
        and tema > bb_mid
        and not tema_rising
        and vol > 0
    )

    score = 0
    score += 1 if rsi >= 50 else -1
    score += 1 if tema_rising else -1
    score += 1 if macd_bull else -1
    if long_bias:
        score += 2
    if short_bias:
        score -= 2
    return "UP" if score >= 0 else "DOWN"


def a8_direction_strict(klines: list[dict]) -> str | None:
    if len(klines) < _JESSE_SLOW + 5:
        return None
    closes = np.array([k["close"] for k in klines], dtype=np.float64)
    prev = closes[:-1]
    ema_fast = _ema_last(closes, _JESSE_FAST)
    ema_slow = _ema_last(closes, _JESSE_SLOW)
    ema_fast_prev = _ema_last(prev, _JESSE_FAST)
    ema_slow_prev = _ema_last(prev, _JESSE_SLOW)
    if ema_fast_prev <= ema_slow_prev and ema_fast > ema_slow:
        return "UP"
    if ema_fast_prev >= ema_slow_prev and ema_fast < ema_slow:
        return "DOWN"
    return None


def a8_direction_loose(klines: list[dict]) -> str | None:
    if len(klines) < _JESSE_SLOW + 5:
        return None
    closes = np.array([k["close"] for k in klines], dtype=np.float64)
    ema_fast = _ema_last(closes, _JESSE_FAST)
    ema_slow = _ema_last(closes, _JESSE_SLOW)
    if ema_fast > ema_slow:
        return "UP"
    if ema_fast < ema_slow:
        return "DOWN"
    return None


def a3_direction_filtered(klines: list[dict]) -> str | None:
    """Entry bias veya 3/3 momentum + RSI teyit — saf sıkıdan daha sık, gevşekten seyrek."""
    entry = a3_direction_strict(klines)
    if entry:
        return entry
    if len(klines) < 30:
        return None
    closes = np.array([k["close"] for k in klines], dtype=np.float64)
    _, rsi = _rsi_last_two(closes)
    tema = _ema_last(closes, 9)
    tema_prev = _ema_last(closes[:-1], 9) if len(closes) > 1 else tema
    macd_bull = _macd_hist_last(closes) > 0
    score = (1 if rsi >= 50 else -1) + (1 if tema > tema_prev else -1) + (1 if macd_bull else -1)
    if score == 3 and rsi >= _A3_FILTER_RSI_UP:
        return "UP"
    if score == -3 and rsi <= _A3_FILTER_RSI_DN:
        return "DOWN"
    return None


def a8_direction_filtered(klines: list[dict]) -> str | None:
    """EMA kesişim veya geniş spread + RSI teyit."""
    cross = a8_direction_strict(klines)
    if cross:
        return cross
    if len(klines) < _JESSE_SLOW + 5:
        return None
    closes = np.array([k["close"] for k in klines], dtype=np.float64)
    price = float(closes[-1])
    if price <= 0:
        return None
    ema_fast = _ema_last(closes, _JESSE_FAST)
    ema_slow = _ema_last(closes, _JESSE_SLOW)
    if abs(ema_fast - ema_slow) / price < _A8_FILTER_SPREAD:
        return None
    _, rsi = _rsi_last_two(closes)
    if ema_fast > ema_slow and rsi >= _A8_FILTER_RSI_UP:
        return "UP"
    if ema_fast < ema_slow and rsi <= _A8_FILTER_RSI_DN:
        return "DOWN"
    return None


def a3_direction(klines: list[dict], *, strict: bool | None = None) -> str | None:
    if strict is None:
        strict = is_a3a8_strict()
    if strict:
        return a3_direction_filtered(klines)
    return a3_direction_loose(klines)


def a8_direction(klines: list[dict], *, strict: bool | None = None) -> str | None:
    if strict is None:
        strict = is_a3a8_strict()
    if strict:
        return a8_direction_filtered(klines)
    return a8_direction_loose(klines)

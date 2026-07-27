"""
Çoklu Teyit Sinyal Sistemi — Pine Script portu (Pattern + Hacim + Seviye + Momentum).
Grafik mumları üzerinde LONG/SHORT okları + EMA seviye çizgisi.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

DEFAULT_PARAMS = {
    "body_wick_mult": 2.0,
    "vol_len": 20,
    "vol_mult": 1.3,
    "ema_len": 50,
    "pivot_len": 10,
    "level_tol_pct": 0.5,
    "rsi_len": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "min_confirm": 3,
}


def _sma(arr: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    if period <= 0 or len(arr) < period:
        return out
    for i in range(period - 1, len(arr)):
        out[i] = float(np.mean(arr[i - period + 1 : i + 1]))
    return out


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    if period <= 0 or len(arr) < period:
        return out
    alpha = 2.0 / (period + 1)
    out[period - 1] = float(np.mean(arr[:period]))
    for i in range(period, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(close: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(close), np.nan)
    if len(close) <= period:
        return out
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - 100.0 / (1.0 + rs)
    for i in range(period + 1, len(close)):
        g = gains[i - 1]
        l = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _macd_hist(close: np.ndarray, fast: int, slow: int, signal: int) -> np.ndarray:
    ema_f = _ema(close, fast)
    ema_s = _ema(close, slow)
    macd_line = ema_f - ema_s
    valid = ~np.isnan(macd_line)
    macd_filled = np.where(valid, macd_line, 0.0)
    signal_line = _ema(macd_filled, signal)
    hist = macd_line - signal_line
    hist[~valid] = np.nan
    return hist


def _last_pivot_series(high: np.ndarray, low: np.ndarray, pivot_len: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(high)
    last_high = np.full(n, np.nan)
    last_low = np.full(n, np.nan)
    cur_h = math.nan
    cur_l = math.nan
    left = right = pivot_len
    for i in range(left + right, n):
        center = i - right
        win_h = high[center - left : center + right + 1]
        win_l = low[center - left : center + right + 1]
        if high[center] >= np.max(win_h):
            cur_h = float(high[center])
        if low[center] <= np.min(win_l):
            cur_l = float(low[center])
        last_high[i] = cur_h
        last_low[i] = cur_l
    return last_high, last_low


def compute_multi_confirm_signals(
    candles: list[dict],
    *,
    dec: int = 2,
    params: dict | None = None,
) -> dict[str, Any]:
    """Grafik mum listesi → sinyaller + EMA seviye + son bar durumu."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    if not candles or len(candles) < 60:
        return {"ok": False, "error": "yetersiz mum verisi"}

    times = np.array([int(c["time"]) for c in candles], dtype=np.int64)
    o = np.array([float(c["open"]) for c in candles], dtype=np.float64)
    h = np.array([float(c["high"]) for c in candles], dtype=np.float64)
    l = np.array([float(c["low"]) for c in candles], dtype=np.float64)
    c = np.array([float(c["close"]) for c in candles], dtype=np.float64)
    v = np.array([float(c.get("volume") or 0) for c in candles], dtype=np.float64)

    n = len(candles)
    body = np.abs(c - o)
    upper_wick = h - np.maximum(c, o)
    lower_wick = np.minimum(c, o) - l
    sma20 = _sma(c, 20)

    bull_engulf = np.zeros(n, dtype=bool)
    bear_engulf = np.zeros(n, dtype=bool)
    for i in range(1, n):
        bull_engulf[i] = (
            c[i - 1] < o[i - 1]
            and c[i] > o[i]
            and c[i] >= o[i - 1]
            and o[i] <= c[i - 1]
        )
        bear_engulf[i] = (
            c[i - 1] > o[i - 1]
            and c[i] < o[i]
            and c[i] <= o[i - 1]
            and o[i] >= c[i - 1]
        )

    is_down = c < sma20
    is_up = c > sma20
    bw = float(p["body_wick_mult"])
    hammer = (
        is_down
        & (lower_wick >= bw * body)
        & (upper_wick <= body * 0.5)
        & (body > 0)
    )
    shooting = (
        is_up
        & (upper_wick >= bw * body)
        & (lower_wick <= body * 0.5)
        & (body > 0)
    )
    bull_pattern = bull_engulf | hammer
    bear_pattern = bear_engulf | shooting

    vol_avg = _sma(v, int(p["vol_len"]))
    vol_confirmed = v > vol_avg * float(p["vol_mult"])

    ema_level = _ema(c, int(p["ema_len"]))
    last_ph, last_pl = _last_pivot_series(h, l, int(p["pivot_len"]))
    tol = float(p["level_tol_pct"])

    near_ema = np.zeros(n, dtype=bool)
    near_pl = np.zeros(n, dtype=bool)
    near_ph = np.zeros(n, dtype=bool)
    for i in range(n):
        if c[i] > 0 and not math.isnan(ema_level[i]):
            near_ema[i] = abs(c[i] - ema_level[i]) / c[i] * 100 <= tol
        if c[i] > 0 and not math.isnan(last_pl[i]):
            near_pl[i] = abs(c[i] - last_pl[i]) / c[i] * 100 <= tol
        if c[i] > 0 and not math.isnan(last_ph[i]):
            near_ph[i] = abs(c[i] - last_ph[i]) / c[i] * 100 <= tol

    level_bull = near_ema | near_pl
    level_bear = near_ema | near_ph

    rsi_val = _rsi(c, int(p["rsi_len"]))
    hist = _macd_hist(c, int(p["macd_fast"]), int(p["macd_slow"]), int(p["macd_signal"]))

    rsi_bull = np.zeros(n, dtype=bool)
    rsi_bear = np.zeros(n, dtype=bool)
    macd_bull = np.zeros(n, dtype=bool)
    macd_bear = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if not math.isnan(rsi_val[i]) and not math.isnan(rsi_val[i - 1]):
            rsi_bull[i] = rsi_val[i - 1] <= p["rsi_oversold"] < rsi_val[i]
            rsi_bear[i] = rsi_val[i - 1] >= p["rsi_overbought"] > rsi_val[i]
        if not math.isnan(hist[i]) and not math.isnan(hist[i - 1]):
            macd_bull[i] = hist[i] > hist[i - 1] and hist[i] > 0
            macd_bear[i] = hist[i] < hist[i - 1] and hist[i] < 0

    mom_bull = rsi_bull | macd_bull
    mom_bear = rsi_bear | macd_bear

    min_c = int(p["min_confirm"])
    signals: list[dict] = []
    ema_series: list[dict] = []

    for i in range(n):
        if not math.isnan(ema_level[i]):
            ema_series.append({"time": int(times[i]), "value": round(float(ema_level[i]), dec)})

        bull_score = int(bull_pattern[i]) + int(vol_confirmed[i]) + int(level_bull[i]) + int(mom_bull[i])
        bear_score = int(bear_pattern[i]) + int(vol_confirmed[i]) + int(level_bear[i]) + int(mom_bear[i])

        if bull_pattern[i] and bull_score >= min_c:
            signals.append({
                "time": int(times[i]),
                "dir": "UP",
                "score": bull_score,
                "tag": "MC",
            })
        elif bear_pattern[i] and bear_score >= min_c:
            signals.append({
                "time": int(times[i]),
                "dir": "DOWN",
                "score": bear_score,
                "tag": "MC",
            })

    last_i = n - 1
    bull_score_last = (
        int(bull_pattern[last_i])
        + int(vol_confirmed[last_i])
        + int(level_bull[last_i])
        + int(mom_bull[last_i])
    )
    bear_score_last = (
        int(bear_pattern[last_i])
        + int(vol_confirmed[last_i])
        + int(level_bear[last_i])
        + int(mom_bear[last_i])
    )
    pattern_lbl = "Bull" if bull_pattern[last_i] else ("Bear" if bear_pattern[last_i] else "-")
    direction = None
    label = "—"
    if bull_pattern[last_i] and bull_score_last >= min_c:
        direction = "UP"
        label = f"LONG {bull_score_last}/4"
    elif bear_pattern[last_i] and bear_score_last >= min_c:
        direction = "DOWN"
        label = f"SHORT {bear_score_last}/4"
    elif bull_score_last >= bear_score_last and bull_score_last > 0:
        label = f"Bull {bull_score_last}/4"
    elif bear_score_last > 0:
        label = f"Bear {bear_score_last}/4"

    return {
        "ok": True,
        "params": p,
        "overlays": {"ema_level": ema_series},
        "signals": signals[-30:],
        "current": {
            "pattern": pattern_lbl,
            "volume_ok": bool(vol_confirmed[last_i]),
            "level_ok": bool(level_bull[last_i] or level_bear[last_i]),
            "momentum_ok": bool(mom_bull[last_i] or mom_bear[last_i]),
            "bull_score": bull_score_last,
            "bear_score": bear_score_last,
            "score": max(bull_score_last, bear_score_last),
            "direction": direction,
            "label": label,
        },
    }

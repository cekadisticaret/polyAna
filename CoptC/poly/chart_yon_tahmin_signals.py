"""
Yön Tahmin Sinyali (YUKARI/AŞAĞI %) — Pine Script portu.
Trend(EMA) + RSI + MACD + Hacim ağırlıklı skor → 0–100 olasılık.
Grafik: EMA9/21, kesişim okları, güçlü sinyal etiketleri + anlık rozet.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

DEFAULT_PARAMS = {
    "ema_fast": 9,
    "ema_mid": 21,
    "ema_slow": 50,
    "rsi_len": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "vol_len": 20,
    "w_trend": 35.0,
    "w_rsi": 25.0,
    "w_macd": 25.0,
    "w_vol": 15.0,
    "label_every": 1,
    "eval_bars": 5,
    "min_prob_filter": 0.0,
    "strong_prob": 65.0,
}


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    if period <= 0 or len(arr) < period:
        return out
    k = 2.0 / (period + 1)
    out[period - 1] = float(np.mean(arr[:period]))
    for i in range(period, len(arr)):
        out[i] = arr[i] * k + out[i - 1] * (1 - k)
    return out


def _sma(arr: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    if period <= 0 or len(arr) < period:
        return out
    for i in range(period - 1, len(arr)):
        out[i] = float(np.mean(arr[i - period + 1 : i + 1]))
    return out


def _rsi(closes: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(closes), np.nan)
    if len(closes) < period + 1:
        return out
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g = float(np.mean(gains[:period]))
    avg_l = float(np.mean(losses[:period]))
    if avg_l == 0:
        out[period] = 100.0
    else:
        out[period] = 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    for i in range(period, len(deltas)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        if avg_l == 0:
            out[i + 1] = 100.0
        else:
            out[i + 1] = 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return out


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(c)
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return _sma(tr, period)


def _macd_hist(closes: np.ndarray, fast: int, slow: int, signal: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ema_f = _ema(closes, fast)
    ema_s = _ema(closes, slow)
    macd = ema_f - ema_s
    sig = _ema(np.nan_to_num(macd, nan=0.0), signal)
    # signal EMA only meaningful after slow period; keep NaNs where macd is NaN
    for i in range(len(macd)):
        if math.isnan(macd[i]):
            sig[i] = np.nan
    hist = macd - sig
    return macd, sig, hist


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_yon_tahmin_signals(
    candles: list[dict],
    *,
    dec: int = 2,
    params: dict | None = None,
) -> dict[str, Any]:
    """Mum listesinden yön tahmin overlay + istatistik."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    if len(candles) < 60:
        return {"ok": False, "error": "yetersiz mum", "signals": [], "slot_marks": [], "current": {}}

    n = len(candles)
    times = np.array([int(c["time"]) for c in candles], dtype=np.int64)
    o = np.array([float(c["open"]) for c in candles])
    h = np.array([float(c["high"]) for c in candles])
    l = np.array([float(c["low"]) for c in candles])
    c = np.array([float(c["close"]) for c in candles])
    v = np.array([float(c.get("volume") or 0) for c in candles])

    ema_fast = _ema(c, int(p["ema_fast"]))
    ema_mid = _ema(c, int(p["ema_mid"]))
    ema_slow = _ema(c, int(p["ema_slow"]))
    rsi_val = _rsi(c, int(p["rsi_len"]))
    _, _, hist = _macd_hist(c, int(p["macd_fast"]), int(p["macd_slow"]), int(p["macd_signal"]))
    vol_avg = _sma(v, int(p["vol_len"]))
    atr = _atr(h, l, c, 14)

    w_sum = float(p["w_trend"] + p["w_rsi"] + p["w_macd"] + p["w_vol"]) or 1.0
    up_prob = np.full(n, np.nan)
    is_up = np.zeros(n, dtype=bool)

    for i in range(n):
        if math.isnan(ema_fast[i]) or math.isnan(ema_mid[i]) or math.isnan(ema_slow[i]):
            continue
        if math.isnan(rsi_val[i]) or math.isnan(hist[i]) or math.isnan(vol_avg[i]):
            continue

        trend_align = (1 if ema_fast[i] > ema_mid[i] else -1) + (1 if ema_mid[i] > ema_slow[i] else -1)
        if i >= 3 and not math.isnan(ema_fast[i - 3]):
            ema_slope = ema_fast[i] - ema_fast[i - 3]
        else:
            ema_slope = 0.0
        denom = c[i] * 0.002 if c[i] else 1.0
        trend_score = _clip((trend_align / 2.0) * 0.6 + (ema_slope / denom) * 0.4)

        rsi_centered = (rsi_val[i] - 50) / 50
        rsi_damped = rsi_centered * 0.5 if (rsi_val[i] > 75 or rsi_val[i] < 25) else rsi_centered
        rsi_score = _clip(rsi_damped)

        atr_i = atr[i] if not math.isnan(atr[i]) and atr[i] > 0 else 1e-9
        macd_score = _clip(hist[i] / atr_i)

        candle_dir = 1 if c[i] > o[i] else (-1 if c[i] < o[i] else 0)
        vol_ratio = v[i] / vol_avg[i] if vol_avg[i] > 0 else 1.0
        vol_score = _clip(candle_dir * min(vol_ratio, 2.0) / 2.0)

        raw = (
            trend_score * p["w_trend"]
            + rsi_score * p["w_rsi"]
            + macd_score * p["w_macd"]
            + vol_score * p["w_vol"]
        ) / w_sum
        up = int(round((raw + 1) / 2 * 100))
        up = max(0, min(100, up))
        up_prob[i] = up
        is_up[i] = up >= 50

    # EMA serileri
    ema_fast_s = [
        {"time": int(times[i]), "value": round(float(ema_fast[i]), dec)}
        for i in range(n) if not math.isnan(ema_fast[i])
    ]
    ema_mid_s = [
        {"time": int(times[i]), "value": round(float(ema_mid[i]), dec)}
        for i in range(n) if not math.isnan(ema_mid[i])
    ]

    # Kesişim + güçlü sinyal etiketleri
    signals: list[dict] = []
    label_every = max(1, int(p["label_every"]))
    strong = float(p["strong_prob"])
    min_filt = float(p["min_prob_filter"])

    for i in range(1, n):
        if math.isnan(ema_fast[i]) or math.isnan(ema_mid[i]):
            continue
        if math.isnan(ema_fast[i - 1]) or math.isnan(ema_mid[i - 1]):
            continue
        cross_up = ema_fast[i - 1] <= ema_mid[i - 1] and ema_fast[i] > ema_mid[i]
        cross_dn = ema_fast[i - 1] >= ema_mid[i - 1] and ema_fast[i] < ema_mid[i]
        if cross_up:
            signals.append({
                "time": int(times[i]),
                "dir": "UP",
                "kind": "cross",
                "prob": int(up_prob[i]) if not math.isnan(up_prob[i]) else 50,
                "text": "X↑",
                "tag": "YT",
            })
        elif cross_dn:
            signals.append({
                "time": int(times[i]),
                "dir": "DOWN",
                "kind": "cross",
                "prob": int(100 - up_prob[i]) if not math.isnan(up_prob[i]) else 50,
                "text": "X↓",
                "tag": "YT",
            })

        # Mum üzeri % / kesişim okları grafikte yok; slot_marks kullanılıyor

    # 5dk / 15dk slot başlangıçlarında o anki YT tahmini
    slot_marks: list[dict] = []
    for i in range(n):
        if math.isnan(up_prob[i]):
            continue
        t = int(times[i])
        is_15 = (t % 900) == 0
        is_5 = (t % 300) == 0
        if not is_5:
            continue
        up_p = int(up_prob[i])
        dn_p = 100 - up_p
        direction = "UP" if bool(is_up[i]) else "DOWN"
        prob = up_p if direction == "UP" else dn_p
        arrow = "↑" if direction == "UP" else "↓"
        tf_tag = "15m" if is_15 else "5m"
        slot_marks.append({
            "time": t,
            "dir": direction,
            "prob": prob,
            "tf": tf_tag,
            "text": f"{'15' if is_15 else '5'}{arrow}{prob}%",
            "tag": "YT",
        })

    # İstatistik: eval_bars sonra fiyat yönü
    eval_n = max(1, int(p["eval_bars"]))
    total = correct = total_up = correct_up = total_dn = correct_dn = 0
    for i in range(n):
        if math.isnan(up_prob[i]) or i % label_every != 0:
            continue
        up_p = int(up_prob[i])
        dn_p = 100 - up_p
        if min_filt > 0 and up_p < min_filt and dn_p < min_filt:
            continue
        j = i + eval_n
        if j >= n:
            continue
        was_up = bool(is_up[i])
        ok = (c[j] > c[i]) if was_up else (c[j] < c[i])
        total += 1
        correct += int(ok)
        if was_up:
            total_up += 1
            correct_up += int(ok)
        else:
            total_dn += 1
            correct_dn += int(ok)

    def _rate(w: int, t: int) -> int:
        return int(round(w / t * 100)) if t > 0 else 0

    last = n - 1
    while last >= 0 and math.isnan(up_prob[last]):
        last -= 1
    if last < 0:
        return {"ok": False, "error": "skor yok", "signals": [], "slot_marks": [], "current": {}}

    up_p = int(up_prob[last])
    dn_p = 100 - up_p
    direction = "UP" if is_up[last] else "DOWN"
    label = f"YUKARI {up_p}%" if direction == "UP" else f"AŞAĞI {dn_p}%"

    return {
        "ok": True,
        "params": p,
        "overlays": {
            "ema_fast": ema_fast_s,
            "ema_mid": ema_mid_s,
        },
        "signals": signals[-40:],
        "slot_marks": slot_marks,
        "stats": {
            "eval_bars": eval_n,
            "total": total,
            "correct": correct,
            "overall_pct": _rate(correct, total),
            "up_total": total_up,
            "up_correct": correct_up,
            "up_pct": _rate(correct_up, total_up),
            "down_total": total_dn,
            "down_correct": correct_dn,
            "down_pct": _rate(correct_dn, total_dn),
        },
        "current": {
            "direction": direction,
            "up_prob": up_p,
            "down_prob": dn_p,
            "label": label,
            "rsi": round(float(rsi_val[last]), 1) if not math.isnan(rsi_val[last]) else None,
        },
    }

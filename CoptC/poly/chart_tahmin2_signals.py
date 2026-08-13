"""
TAHMİN2 — 5 bağımsız algoritma oylaması (15m sistemlere uygun).
  LM  : Late momentum vs Ref (price-to-beat)
  ST  : Triple Supertrend
  ADX : ADX + DI yönü
  LZ  : Basitleştirilmiş Lorentzian kNN (RSI/WT/CCI/ADX)
  CVD : Hacim-delta (candle CVD proxy)
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

DEFAULT_PARAMS = {
    "lm_min_pct": 0.05,  # Ref'ten min sapma %
    "adx_len": 14,
    "adx_min": 18.0,
    "st_sets": ((10, 1.0), (11, 2.0), (12, 3.0)),
    "lz_neighbors": 8,
    "lz_lookback": 100,
    "cvd_slope_bars": 12,
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


def _rma(arr: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    if period <= 0 or len(arr) < period:
        return out
    out[period - 1] = float(np.mean(arr[:period]))
    for i in range(period, len(arr)):
        out[i] = (out[i - 1] * (period - 1) + arr[i]) / period
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    out = np.full(len(closes), np.nan)
    if len(closes) < period + 1:
        return out
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g = float(np.mean(gains[:period]))
    avg_l = float(np.mean(losses[:period]))
    out[period] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    for i in range(period, len(deltas)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        out[i + 1] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return out


def _true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    n = len(c)
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int) -> np.ndarray:
    return _rma(_true_range(h, l, c), period)


def _adx_di(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(c)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        plus_dm[i] = up if up > dn and up > 0 else 0.0
        minus_dm[i] = dn if dn > up and dn > 0 else 0.0
    atr = _atr(h, l, c, period)
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    dx = np.full(n, np.nan)
    sm_plus = _rma(plus_dm, period)
    sm_minus = _rma(minus_dm, period)
    for i in range(n):
        if math.isnan(atr[i]) or atr[i] == 0 or math.isnan(sm_plus[i]) or math.isnan(sm_minus[i]):
            continue
        plus_di[i] = 100.0 * sm_plus[i] / atr[i]
        minus_di[i] = 100.0 * sm_minus[i] / atr[i]
        s = plus_di[i] + minus_di[i]
        dx[i] = 0.0 if s == 0 else 100.0 * abs(plus_di[i] - minus_di[i]) / s
    adx = _rma(np.nan_to_num(dx, nan=0.0), period)
    for i in range(n):
        if math.isnan(dx[i]):
            adx[i] = np.nan
    return adx, plus_di, minus_di


def _supertrend_dir(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int, mult: float) -> np.ndarray:
    """+1 up, -1 down, nan incomplete."""
    n = len(c)
    atr = _atr(h, l, c, period)
    out = np.full(n, np.nan)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(n):
        if math.isnan(atr[i]):
            continue
        mid = (h[i] + l[i]) / 2.0
        bu = mid + mult * atr[i]
        bl = mid - mult * atr[i]
        if i == 0 or math.isnan(upper[i - 1]):
            upper[i], lower[i] = bu, bl
            out[i] = 1.0
            continue
        lower[i] = max(bl, lower[i - 1]) if c[i - 1] > lower[i - 1] else bl
        upper[i] = min(bu, upper[i - 1]) if c[i - 1] < upper[i - 1] else bu
        if out[i - 1] == 1.0:
            out[i] = -1.0 if c[i] < lower[i] else 1.0
        else:
            out[i] = 1.0 if c[i] > upper[i] else -1.0
    return out


def _cci(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 20) -> np.ndarray:
    tp = (h + l + c) / 3.0
    out = np.full(len(c), np.nan)
    for i in range(period - 1, len(c)):
        window = tp[i - period + 1 : i + 1]
        sma = float(np.mean(window))
        mad = float(np.mean(np.abs(window - sma)))
        out[i] = 0.0 if mad == 0 else (tp[i] - sma) / (0.015 * mad)
    return out


def _wavetrend(h: np.ndarray, l: np.ndarray, c: np.ndarray, chlen: int = 10, avg: int = 21) -> np.ndarray:
    esa = _ema((h + l + c) / 3.0, chlen)
    d = _ema(np.abs((h + l + c) / 3.0 - esa), chlen)
    ci = np.full(len(c), np.nan)
    for i in range(len(c)):
        if math.isnan(esa[i]) or math.isnan(d[i]) or d[i] == 0:
            continue
        ci[i] = ((h[i] + l[i] + c[i]) / 3.0 - esa[i]) / (0.015 * d[i])
    return _ema(np.nan_to_num(ci, nan=0.0), avg)


def _vote_lm(close: float, ref_price: float | None, min_pct: float) -> dict[str, Any]:
    if ref_price is None or ref_price <= 0 or close <= 0:
        return {"tag": "LM", "dir": None, "label": "LM —"}
    pct = (close - ref_price) / ref_price * 100.0
    if abs(pct) < min_pct:
        return {"tag": "LM", "dir": None, "label": f"LM {pct:+.2f}%"}
    d = "UP" if pct > 0 else "DOWN"
    return {"tag": "LM", "dir": d, "label": f"LM {d} {pct:+.2f}%", "pct": round(pct, 3)}


def _vote_st(h: np.ndarray, l: np.ndarray, c: np.ndarray, sets: tuple) -> dict[str, Any]:
    dirs = []
    for period, mult in sets:
        st = _supertrend_dir(h, l, c, int(period), float(mult))
        if math.isnan(st[-1]):
            continue
        dirs.append(1 if st[-1] > 0 else -1)
    if len(dirs) < 3:
        return {"tag": "ST", "dir": None, "label": "ST —"}
    if all(x > 0 for x in dirs):
        return {"tag": "ST", "dir": "UP", "label": "ST ↑3/3"}
    if all(x < 0 for x in dirs):
        return {"tag": "ST", "dir": "DOWN", "label": "ST ↓3/3"}
    up = sum(1 for x in dirs if x > 0)
    return {"tag": "ST", "dir": None, "label": f"ST {up}/3"}


def _vote_adx(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int, adx_min: float) -> dict[str, Any]:
    adx, plus_di, minus_di = _adx_di(h, l, c, period)
    i = len(c) - 1
    if math.isnan(adx[i]) or math.isnan(plus_di[i]) or math.isnan(minus_di[i]):
        return {"tag": "ADX", "dir": None, "label": "ADX —"}
    if adx[i] < adx_min:
        return {"tag": "ADX", "dir": None, "label": f"ADX {adx[i]:.0f}<{adx_min:.0f}"}
    if plus_di[i] > minus_di[i]:
        return {"tag": "ADX", "dir": "UP", "label": f"ADX ↑{adx[i]:.0f}"}
    if minus_di[i] > plus_di[i]:
        return {"tag": "ADX", "dir": "DOWN", "label": f"ADX ↓{adx[i]:.0f}"}
    return {"tag": "ADX", "dir": None, "label": f"ADX {adx[i]:.0f}="}


def _vote_lz(
    h: np.ndarray, l: np.ndarray, c: np.ndarray,
    neighbors: int, lookback: int,
) -> dict[str, Any]:
    """Basit Lorentzian kNN: özellik mesafesi → sonraki bar yönü oyı."""
    n = len(c)
    rsi = _rsi(c, 14)
    wt = _wavetrend(h, l, c)
    cci = _cci(h, l, c, 20)
    adx, _, _ = _adx_di(h, l, c, 14)
    feats = np.column_stack([rsi, wt, cci, adx])
    # normalize roughly
    start = max(40, n - lookback - 2)
    if n < start + neighbors + 5:
        return {"tag": "LZ", "dir": None, "label": "LZ —"}
    cur = feats[-1]
    if np.any(np.isnan(cur)):
        return {"tag": "LZ", "dir": None, "label": "LZ —"}
    dists: list[tuple[float, int]] = []
    for i in range(start, n - 2):
        row = feats[i]
        if np.any(np.isnan(row)):
            continue
        # Lorentzian-ish: sum ln(1+|diff|)
        d = float(np.sum(np.log1p(np.abs(cur - row))))
        dists.append((d, i))
    if len(dists) < neighbors:
        return {"tag": "LZ", "dir": None, "label": "LZ —"}
    dists.sort(key=lambda x: x[0])
    votes_up = 0
    votes_dn = 0
    for _, i in dists[:neighbors]:
        if c[i + 1] > c[i]:
            votes_up += 1
        elif c[i + 1] < c[i]:
            votes_dn += 1
    if votes_up > votes_dn:
        return {"tag": "LZ", "dir": "UP", "label": f"LZ ↑{votes_up}/{neighbors}"}
    if votes_dn > votes_up:
        return {"tag": "LZ", "dir": "DOWN", "label": f"LZ ↓{votes_dn}/{neighbors}"}
    return {"tag": "LZ", "dir": None, "label": f"LZ ={votes_up}/{neighbors}"}


def _vote_cvd(o: np.ndarray, c: np.ndarray, v: np.ndarray, slope_bars: int) -> dict[str, Any]:
    n = len(c)
    if n < slope_bars + 2:
        return {"tag": "CVD", "dir": None, "label": "CVD —"}
    signed = np.where(c >= o, v, -v)
    cvd = np.cumsum(signed)
    a = cvd[-slope_bars]
    b = cvd[-1]
    delta = float(b - a)
    # scale by avg volume
    avg_v = float(np.mean(v[-slope_bars:])) or 1.0
    score = delta / avg_v
    if score > 0.8:
        return {"tag": "CVD", "dir": "UP", "label": f"CVD ↑{score:.1f}"}
    if score < -0.8:
        return {"tag": "CVD", "dir": "DOWN", "label": f"CVD ↓{abs(score):.1f}"}
    return {"tag": "CVD", "dir": None, "label": f"CVD {score:+.1f}"}


def compute_tahmin2_signals(
    candles: list[dict],
    *,
    ref_price: float | None = None,
    dec: int = 2,
    params: dict | None = None,
) -> dict[str, Any]:
    p = {**DEFAULT_PARAMS, **(params or {})}
    if len(candles) < 60:
        return {"ok": False, "error": "yetersiz mum", "votes": [], "current": {}}

    o = np.array([float(c["open"]) for c in candles])
    h = np.array([float(c["high"]) for c in candles])
    l = np.array([float(c["low"]) for c in candles])
    c = np.array([float(c["close"]) for c in candles])
    v = np.array([float(c.get("volume") or 0) for c in candles])

    votes = [
        _vote_lm(float(c[-1]), float(ref_price) if ref_price is not None else None, float(p["lm_min_pct"])),
        _vote_st(h, l, c, tuple(p["st_sets"])),
        _vote_adx(h, l, c, int(p["adx_len"]), float(p["adx_min"])),
        _vote_lz(h, l, c, int(p["lz_neighbors"]), int(p["lz_lookback"])),
        _vote_cvd(o, c, v, int(p["cvd_slope_bars"])),
    ]

    dirs = [x["dir"] for x in votes if x.get("dir") in ("UP", "DOWN")]
    up_n = sum(1 for d in dirs if d == "UP")
    dn_n = sum(1 for d in dirs if d == "DOWN")
    total = len(votes)  # her zaman 5 (nötrler de paydada)
    if up_n > dn_n:
        direction = "UP"
        label = f"YUKARI {up_n}/{total}"
    elif dn_n > up_n:
        direction = "DOWN"
        label = f"AŞAĞI {dn_n}/{total}"
    elif up_n or dn_n:
        direction = None
        label = f"BERABERE {up_n}-{dn_n}/{total}"
    else:
        direction = None
        label = f"— 0/{total}"

    return {
        "ok": True,
        "params": {k: p[k] for k in ("lm_min_pct", "adx_len", "adx_min", "lz_neighbors", "cvd_slope_bars")},
        "votes": votes,
        "current": {
            "direction": direction,
            "up": up_n,
            "down": dn_n,
            "total": total,
            "label": label,
            "parts": [f"{v['tag']}:{v.get('dir') or '-'}" for v in votes],
        },
    }

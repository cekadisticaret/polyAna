"""D101–D106 — XAUUSD aile sinyalleri.

Poly / CEM01 dosyalarına yazmaz. Emir defteri yok; D104 mum+hacim vekili.
"""
from __future__ import annotations

import math
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_DIR, ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
if _POLY not in sys.path:
    sys.path.insert(0, _POLY)

import algo_signals as sig  # noqa: E402


def _bars(kl: list) -> list[dict]:
    out = []
    for k in kl or []:
        row = {
            "o": float(k.get("o") if k.get("o") is not None else k.get("open") or 0),
            "h": float(k.get("h") if k.get("h") is not None else k.get("high") or 0),
            "l": float(k.get("l") if k.get("l") is not None else k.get("low") or 0),
            "c": float(k.get("c") if k.get("c") is not None else k.get("close") or 0),
            "v": float(k.get("v") if k.get("v") is not None else k.get("volume") or 0),
        }
        t = k.get("t") if k.get("t") is not None else k.get("time")
        if t is not None:
            try:
                row["t"] = int(t)
            except (TypeError, ValueError):
                pass
        out.append(row)
    return out


def _dir(val) -> str:
    return val if val in ("UP", "DOWN") else "NEUTRAL"


def _vote(dirs: list[str], need: int = 2) -> str:
    up = dirs.count("UP")
    down = dirs.count("DOWN")
    if up >= need and up > down:
        return "UP"
    if down >= need and down > up:
        return "DOWN"
    return "NEUTRAL"


def _std_mean(vals: list[float]) -> tuple[float, float]:
    n = len(vals)
    if n < 2:
        return 0.0, (vals[-1] if vals else 0.0)
    m = sum(vals) / n
    var = sum((x - m) ** 2 for x in vals) / n
    return math.sqrt(var), m


def _atr(bars: list[dict], p: int = 14) -> float | None:
    if len(bars) < p + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        trs.append(max(
            bars[i]["h"] - bars[i]["l"],
            abs(bars[i]["h"] - bars[i - 1]["c"]),
            abs(bars[i]["l"] - bars[i - 1]["c"]),
        ))
    if len(trs) < p:
        return None
    return sum(trs[-p:]) / p


def _bb_fade(bars: list[dict]) -> str:
    c = [k["c"] for k in bars]
    if len(c) < 20:
        return "NEUTRAL"
    std, mid = _std_mean(c[-20:])
    if std <= 0:
        return "NEUTRAL"
    px = c[-1]
    if px < mid - 2.0 * std:
        return "UP"
    if px > mid + 2.0 * std:
        return "DOWN"
    return "NEUTRAL"


def _vwap_z_fade(bars: list[dict]) -> str:
    w = bars[-24:] if len(bars) >= 24 else bars
    tv = sum(k["v"] for k in w)
    if tv <= 0:
        tv = float(len(w))
        tps = [(k["h"] + k["l"] + k["c"]) / 3 for k in w]
        vwap = sum(tps) / len(tps)
    else:
        vwap = sum(((k["h"] + k["l"] + k["c"]) / 3) * k["v"] for k in w) / tv
    resid = [k["c"] - vwap for k in w]
    std, _ = _std_mean(resid)
    if std <= 1e-9:
        return "NEUTRAL"
    z = (bars[-1]["c"] - vwap) / std
    if z <= -1.2:
        return "UP"
    if z >= 1.2:
        return "DOWN"
    return "NEUTRAL"


def _squeeze_expand(bars: list[dict]) -> str:
    c = [k["c"] for k in bars]
    if len(c) < 40:
        return "NEUTRAL"
    widths = []
    for i in range(20, len(c) + 1):
        std, mid = _std_mean(c[i - 20:i])
        if mid <= 0:
            widths.append(0.0)
        else:
            widths.append(2.0 * std / mid)
    if len(widths) < 8:
        return "NEUTRAL"
    hist = widths[-21:-1] if len(widths) > 21 else widths[:-1]
    if not hist:
        return "NEUTRAL"
    cutoff = sorted(hist)[max(0, len(hist) // 5)]
    prev, cur = widths[-2], widths[-1]
    if prev > cutoff:
        return "NEUTRAL"
    if cur <= prev * 1.05:
        return "NEUTRAL"
    std, mid = _std_mean(c[-20:])
    px = c[-1]
    if px > mid:
        return "UP"
    if px < mid:
        return "DOWN"
    return "NEUTRAL"


def _orb(bars: list[dict]) -> str:
    """Londra 07:00 / NY 13:00 UTC ilk saat aralığı; zaman yoksa son 4 mum."""
    if len(bars) < 6:
        return "NEUTRAL"
    last = bars[-1]
    px = last["c"]
    timed = [k for k in bars if k.get("t")]
    if len(timed) >= 8:
        last_t = int(last.get("t") or 0)
        day0 = last_t - (last_t % 86400)
        london = [k for k in timed if int(k["t"]) == day0 + 7 * 3600]
        ny = [k for k in timed if int(k["t"]) == day0 + 13 * 3600]
        or_bar = (london or ny or [None])[0]
        if or_bar and int(last["t"]) > int(or_bar["t"]):
            hi, lo = or_bar["h"], or_bar["l"]
            if px > hi:
                return "UP"
            if px < lo:
                return "DOWN"
            return "NEUTRAL"
    window = bars[-5:-1]
    hi = max(k["h"] for k in window)
    lo = min(k["l"] for k in window)
    if px > hi:
        return "UP"
    if px < lo:
        return "DOWN"
    return "NEUTRAL"


def _liq_sweep(bars: list[dict]) -> str:
    k = bars[-1]
    rng = k["h"] - k["l"]
    if rng <= 0:
        return "NEUTRAL"
    body_lo = min(k["o"], k["c"])
    body_hi = max(k["o"], k["c"])
    lower = body_lo - k["l"]
    upper = k["h"] - body_hi
    mid = (k["h"] + k["l"]) / 2
    if lower >= 0.55 * rng and k["c"] > mid:
        return "UP"
    if upper >= 0.55 * rng and k["c"] < mid:
        return "DOWN"
    return "NEUTRAL"


def _kalman_velocity(closes: list[float], q: float = 8e-5, r: float = 2e-2) -> float:
    if len(closes) < 8:
        return 0.0
    x0, x1 = float(closes[0]), 0.0
    p00, p01, p10, p11 = 1.0, 0.0, 0.0, 1.0
    for z in closes:
        x0, x1 = x0 + x1, x1
        a, b, c, d = p00, p01, p10, p11
        p00 = a + b + c + d + q
        p01 = b + d
        p10 = c + d
        p11 = d + q
        y = float(z) - x0
        s = p00 + r
        if s == 0:
            continue
        k0 = p00 / s
        k1 = p10 / s
        x0 += k0 * y
        x1 += k1 * y
        p00, p01, p10, p11 = (
            (1 - k0) * p00,
            (1 - k0) * p01,
            -k1 * p00 + p10,
            -k1 * p01 + p11,
        )
    return float(x1)


def _hurst(closes: list[float]) -> float | None:
    x = closes[-64:] if len(closes) >= 64 else closes
    if len(x) < 32:
        return None
    rets = []
    for i in range(1, len(x)):
        if x[i - 1] > 0 and x[i] > 0:
            rets.append(math.log(x[i] / x[i - 1]))
    n = len(rets)
    if n < 24:
        return None
    m = sum(rets) / n
    dev = [r - m for r in rets]
    walk = []
    acc = 0.0
    for d in dev:
        acc += d
        walk.append(acc)
    rs = (max(walk) - min(walk)) / (math.sqrt(sum(d * d for d in dev) / n) or 1e-9)
    if rs <= 0:
        return None
    return math.log(rs) / math.log(n)


def d101(kl: list) -> str:
    """Trend / momentum: EMA kesişim + Donchian + ADX filtresi."""
    bars = _bars(kl)
    if len(bars) < 40:
        return "NEUTRAL"
    adx = _dir(sig.adx_regime(bars))
    if adx == "NEUTRAL":
        return "NEUTRAL"
    return _vote([
        _dir(sig.ema_crossover(bars)),
        _dir(sig.donchian_channel(bars)),
        adx,
    ], 2)


def d102(kl: list) -> str:
    """Mean reversion: BB + VWAP-z + RSI div; yalnız range (ADX zayıf)."""
    bars = _bars(kl)
    if len(bars) < 30:
        return "NEUTRAL"
    if _dir(sig.adx_regime(bars)) != "NEUTRAL":
        return "NEUTRAL"
    return _vote([
        _bb_fade(bars),
        _vwap_z_fade(bars),
        _dir(sig.rsi_divergence_strict(bars)),
        _dir(sig.mean_reversion(bars)),
    ], 2)


def d103(kl: list) -> str:
    """Volatilite kırılımı: ATR + squeeze→expansion + açılış aralığı."""
    bars = _bars(kl)
    if len(bars) < 30:
        return "NEUTRAL"
    return _vote([
        _dir(sig.atr_breakout(bars)),
        _squeeze_expand(bars),
        _orb(bars),
    ], 2)


def d104(kl: list) -> str:
    """Akış vekili: OBV + hacim profili + MFI + likidite süpürmesi."""
    bars = _bars(kl)
    if len(bars) < 50:
        return "NEUTRAL"
    return _vote([
        _dir(sig.obv(bars)),
        _dir(sig.volume_profile(bars)),
        _dir(sig.money_flow_index(bars)),
        _liq_sweep(bars),
    ], 2)


def d105(kl: list) -> str:
    """Kalman hız + Hurst rejim: H yüksekse trend, düşükse fade."""
    bars = _bars(kl)
    if len(bars) < 40:
        return "NEUTRAL"
    closes = [k["c"] for k in bars]
    h = _hurst(closes)
    if h is None:
        return "NEUTRAL"
    vel = _kalman_velocity(closes)
    atr = _atr(bars) or 0.0
    scale = max(atr, 0.15)
    if h >= 0.55:
        if vel > 0.15 * scale:
            return "UP"
        if vel < -0.15 * scale:
            return "DOWN"
        return "NEUTRAL"
    if h <= 0.45:
        return _dir(sig.mean_reversion(bars))
    return "NEUTRAL"


def d106(kl: list) -> str:
    """Çok faktör: D101–D105 en az 3 aynı yön."""
    return _vote([d101(kl), d102(kl), d103(kl), d104(kl), d105(kl)], 3)


HANDLERS = {
    "d101": d101,
    "d102": d102,
    "d103": d103,
    "d104": d104,
    "d105": d105,
    "d106": d106,
}


def signal_for_d(uid: str, kl: list) -> str:
    fn = HANDLERS.get((uid or "").strip().lower())
    if not fn:
        return "NEUTRAL"
    try:
        return _dir(fn(kl))
    except Exception as e:
        print(f"[fx_algo] {uid}: {e}")
        return "NEUTRAL"

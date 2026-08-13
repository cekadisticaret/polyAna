"""Genişletilmiş algo kataloğu — OHLCV (+ taker buy) ile backtest edilebilir göstergeler."""
from __future__ import annotations

import math

from algo_signals import (
    _atr,
    _ema,
    _rsi,
    _std,
    _wma,
    adx_regime,
    bb_squeeze,
    donchian_channel,
    ema_crossover,
    heikin_ashi,
    hull_ma,
    keltner_channel,
    macd_div,
    mean_reversion,
    money_flow_index,
    obv,
    stoch_rsi,
    supertrend,
    tema_crossover,
    triple_ema,
    vwap,
)


def _closes(kl):
    return [k["c"] for k in kl]


def _to_kl(bars):
    return [
        {
            "o": b["open"],
            "h": b["high"],
            "l": b["low"],
            "c": b["close"],
            "v": b["volume"],
            "taker_buy": b.get("taker_buy", b["volume"] * 0.5),
        }
        for b in bars
    ]


def williams_r(kl, p=14):
    if len(kl) < p:
        return "NEUTRAL"
    w = kl[-p:]
    hh, ll = max(k["h"] for k in w), min(k["l"] for k in w)
    if hh == ll:
        return "NEUTRAL"
    wr = (hh - kl[-1]["c"]) / (hh - ll) * -100
    if wr < -80:
        return "UP"
    if wr > -20:
        return "DOWN"
    return "UP" if wr < -50 else "DOWN"


def cci(kl, p=20):
    if len(kl) < p:
        return "NEUTRAL"
    tp = [(k["h"] + k["l"] + k["c"]) / 3 for k in kl]
    m = sum(tp[-p:]) / p
    md = sum(abs(x - m) for x in tp[-p:]) / p
    if not md:
        return "NEUTRAL"
    val = (tp[-1] - m) / (0.015 * md)
    if val < -100:
        return "UP"
    if val > 100:
        return "DOWN"
    return "UP" if val > 0 else "DOWN"


def chaikin_mf(kl, p=20):
    if len(kl) < p + 1:
        return "NEUTRAL"
    mf = []
    for k in kl:
        r = (k["h"] - k["l"]) or 1e-9
        clv = ((k["c"] - k["l"]) - (k["h"] - k["c"])) / r
        mf.append(clv * k["v"])
    cmf = sum(mf[-p:]) / (sum(k["v"] for k in kl[-p:]) or 1e-9)
    if cmf > 0.05:
        return "UP"
    if cmf < -0.05:
        return "DOWN"
    return "UP" if cmf > 0 else "DOWN"


def aroon(kl, p=25):
    if len(kl) < p + 1:
        return "NEUTRAL"
    w = kl[-p:]
    hi_i = max(range(len(w)), key=lambda i: w[i]["h"])
    lo_i = max(range(len(w)), key=lambda i: -w[i]["l"])
    up = (p - (len(w) - 1 - hi_i)) / p * 100
    dn = (p - (len(w) - 1 - lo_i)) / p * 100
    if up > 70 and dn < 30:
        return "UP"
    if dn > 70 and up < 30:
        return "DOWN"
    return "UP" if up > dn else "DOWN"


def trix(kl, p=15):
    c = _closes(kl)
    if len(c) < p * 3 + 5:
        return "NEUTRAL"
    e1 = [x for x in _ema(c, p) if x is not None]
    e2 = [x for x in _ema(e1, p) if x is not None]
    e3 = [x for x in _ema(e2, p) if x is not None]
    if len(e3) < 2:
        return "NEUTRAL"
    roc = (e3[-1] - e3[-2]) / (abs(e3[-2]) or 1e-9) * 100
    return "UP" if roc > 0 else "DOWN" if roc < 0 else "NEUTRAL"


def ultimate_oscillator(kl):
    if len(kl) < 30:
        return "NEUTRAL"
    bp, tr = [], []
    for i in range(1, len(kl)):
        bp.append(kl[i]["c"] - min(kl[i]["l"], kl[i - 1]["c"]))
        tr.append(max(kl[i]["h"], kl[i - 1]["c"]) - min(kl[i]["l"], kl[i - 1]["c"]))
    if not tr[-28:]:
        return "NEUTRAL"

    def _avg(n):
        s = sum(tr[-n:])
        return sum(bp[-n:]) / s * 100 if s else 50

    uo = (_avg(7) * 4 + _avg(14) * 2 + _avg(28)) / 7
    if uo < 30:
        return "UP"
    if uo > 70:
        return "DOWN"
    return "UP" if uo > 55 else "DOWN"


def awesome_oscillator(kl):
    if len(kl) < 34:
        return "NEUTRAL"
    mid = [(k["h"] + k["l"]) / 2 for k in kl]
    s5 = sum(mid[-5:]) / 5
    s34 = sum(mid[-34:]) / 34
    ao = s5 - s34
    if len(kl) < 39:
        return "UP" if ao > 0 else "DOWN"
    prev = sum(mid[-6:-1]) / 5 - sum(mid[-35:-1]) / 34
    if ao > 0 and ao > prev:
        return "UP"
    if ao < 0 and ao < prev:
        return "DOWN"
    return "UP" if ao > 0 else "DOWN"


def coppock_curve(kl):
    c = _closes(kl)
    if len(c) < 15:
        return "NEUTRAL"
    roc1 = (c[-1] - c[-11]) / (c[-11] or 1e-9) * 100 if len(c) >= 11 else 0
    roc2 = (c[-1] - c[-14]) / (c[-14] or 1e-9) * 100 if len(c) >= 14 else 0
    val = roc1 + roc2
    return "UP" if val > 0 else "DOWN"


def vortex_indicator(kl, p=14):
    if len(kl) < p + 2:
        return "NEUTRAL"
    vp, vm, tr = 0.0, 0.0, 0.0
    for i in range(-p, 0):
        vp += abs(kl[i]["h"] - kl[i - 1]["l"])
        vm += abs(kl[i]["l"] - kl[i - 1]["h"])
        tr += max(
            kl[i]["h"] - kl[i]["l"],
            abs(kl[i]["h"] - kl[i - 1]["c"]),
            abs(kl[i]["l"] - kl[i - 1]["c"]),
        )
    if not tr:
        return "NEUTRAL"
    vi_p, vi_m = vp / tr, vm / tr
    if vi_p > vi_m * 1.05:
        return "UP"
    if vi_m > vi_p * 1.05:
        return "DOWN"
    return "NEUTRAL"


def elder_force_index(kl, p=13):
    if len(kl) < p + 2:
        return "NEUTRAL"
    efi = []
    for i in range(1, len(kl)):
        efi.append((kl[i]["c"] - kl[i - 1]["c"]) * kl[i]["v"])
    if len(efi) < p:
        return "NEUTRAL"
    s = sum(efi[-p:])
    return "UP" if s > 0 else "DOWN" if s < 0 else "NEUTRAL"


def choppiness_index(kl, p=14):
    if len(kl) < p + 1:
        return "NEUTRAL"
    w = kl[-p:]
    hh, ll = max(k["h"] for k in w), min(k["l"] for k in w)
    tr_sum = 0.0
    for i in range(-p, 0):
        tr_sum += max(
            kl[i]["h"] - kl[i]["l"],
            abs(kl[i]["h"] - kl[i - 1]["c"]),
            abs(kl[i]["l"] - kl[i - 1]["c"]),
        )
    if not tr_sum or hh == ll:
        return "NEUTRAL"
    chop = 100 * math.log10(tr_sum / (hh - ll)) / math.log10(p)
    if chop > 61.8:
        return mean_reversion(kl)
    return ema_crossover(kl)


def pivot_points(kl):
    if len(kl) < 2:
        return "NEUTRAL"
    prev = kl[-2]
    pp = (prev["h"] + prev["l"] + prev["c"]) / 3
    r1 = 2 * pp - prev["l"]
    s1 = 2 * pp - prev["h"]
    px = kl[-1]["c"]
    if px > r1:
        return "UP"
    if px < s1:
        return "DOWN"
    return "UP" if px > pp else "DOWN"


def fib_retracement(kl):
    if len(kl) < 30:
        return "NEUTRAL"
    w = kl[-30:]
    hi, lo = max(k["h"] for k in w), min(k["l"] for k in w)
    rng = hi - lo
    if not rng:
        return "NEUTRAL"
    fib382 = hi - 0.382 * rng
    fib618 = hi - 0.618 * rng
    px = kl[-1]["c"]
    if px <= fib618:
        return "UP"
    if px >= fib382 and px < hi - 0.236 * rng:
        return "DOWN"
    return "UP" if px < (hi + lo) / 2 else "DOWN"


def roc_momentum(kl, p=12):
    c = _closes(kl)
    if len(c) <= p:
        return "NEUTRAL"
    roc = (c[-1] - c[-1 - p]) / (c[-1 - p] or 1e-9) * 100
    if roc > 1.5:
        return "UP"
    if roc < -1.5:
        return "DOWN"
    return "UP" if roc > 0 else "DOWN"


def ppo(kl):
    c = _closes(kl)
    if len(c) < 30:
        return "NEUTRAL"
    e12, e26 = _ema(c, 12), _ema(c, 26)
    if e12[-1] is None or e26[-1] is None:
        return "NEUTRAL"
    ppo = (e12[-1] - e26[-1]) / (e26[-1] or 1e-9) * 100
    return "UP" if ppo > 0 else "DOWN"


def kama(kl, p=10):
    c = _closes(kl)
    if len(c) < p + 10:
        return "NEUTRAL"
    change = abs(c[-1] - c[-1 - p])
    vol = sum(abs(c[i] - c[i - 1]) for i in range(-p, 0))
    er = change / vol if vol else 0
    sc = (er * (2 / 3 - 2 / 31) + 2 / 31) ** 2
    kama = c[-1 - p]
    for i in range(-p, 0):
        kama = kama + sc * (c[i] - kama)
    return "UP" if c[-1] > kama else "DOWN"


def linreg_slope(kl, p=20):
    c = _closes(kl)
    if len(c) < p:
        return "NEUTRAL"
    y = c[-p:]
    x = list(range(p))
    xm, ym = sum(x) / p, sum(y) / p
    num = sum((x[i] - xm) * (y[i] - ym) for i in range(p))
    den = sum((x[i] - xm) ** 2 for i in range(p)) or 1e-9
    slope = num / den
    return "UP" if slope > 0 else "DOWN"


def taker_buy_ratio(kl):
    if len(kl) < 10:
        return "NEUTRAL"
    tb = sum(k.get("taker_buy", k["v"] * 0.5) for k in kl[-10:])
    vol = sum(k["v"] for k in kl[-10:]) or 1e-9
    ratio = tb / vol
    if ratio > 0.55:
        return "UP"
    if ratio < 0.45:
        return "DOWN"
    return "NEUTRAL"


def cvd_proxy(kl):
    if len(kl) < 15:
        return "NEUTRAL"
    cvd = 0.0
    for k in kl[-15:]:
        tb = k.get("taker_buy", k["v"] * 0.5)
        cvd += (2 * tb - k["v"])
    return "UP" if cvd > 0 else "DOWN" if cvd < 0 else "NEUTRAL"


def higher_high_trend(kl):
    if len(kl) < 10:
        return "NEUTRAL"
    h = [k["h"] for k in kl[-5:]]
    l = [k["l"] for k in kl[-5:]]
    if h[-1] > max(h[:-1]) and l[-1] > min(l[:-1]):
        return "UP"
    if h[-1] < max(h[:-1]) and l[-1] < min(l[:-1]):
        return "DOWN"
    return "NEUTRAL"


def engulfing_pattern(kl):
    if len(kl) < 3:
        return "NEUTRAL"
    p, c = kl[-2], kl[-1]
    pb = p["c"] > p["o"]
    cb = c["c"] > c["o"]
    if not pb and cb and c["c"] > p["o"] and c["o"] < p["c"]:
        return "UP"
    if pb and not cb and c["c"] < p["o"] and c["o"] > p["c"]:
        return "DOWN"
    return "NEUTRAL"


def inside_bar_breakout(kl):
    if len(kl) < 4:
        return "NEUTRAL"
    ib, cur = kl[-2], kl[-1]
    prev = kl[-3]
    if ib["h"] <= prev["h"] and ib["l"] >= prev["l"]:
        if cur["c"] > ib["h"]:
            return "UP"
        if cur["c"] < ib["l"]:
            return "DOWN"
    return "NEUTRAL"


def squeeze_momentum(kl):
    if len(kl) < 25:
        return "NEUTRAL"
    c = _closes(kl)
    std, m = _std(c[-20:])
    bb_u, bb_l = m + 2 * std, m - 2 * std
    av = _atr(kl, 10)
    if av[-1] is None:
        return "NEUTRAL"
    kc_u, kc_l = m + 1.5 * av[-1], m - 1.5 * av[-1]
    squeeze = bb_u < kc_u and bb_l > kc_l
    if squeeze:
        return "NEUTRAL"
    return bb_squeeze(kl)


def accumulation_distribution(kl):
    if len(kl) < 20:
        return "NEUTRAL"
    ad = [0.0]
    for k in kl[1:]:
        r = (k["h"] - k["l"]) or 1e-9
        mfm = ((k["c"] - k["l"]) - (k["h"] - k["c"])) / r
        ad.append(ad[-1] + mfm * k["v"])
    if ad[-1] > ad[-5]:
        return "UP"
    if ad[-1] < ad[-5]:
        return "DOWN"
    return "NEUTRAL"


def ease_of_movement(kl, p=14):
    if len(kl) < p + 1:
        return "NEUTRAL"
    eom = []
    for i in range(1, len(kl)):
        dist = ((kl[i]["h"] + kl[i]["l"]) / 2) - ((kl[i - 1]["h"] + kl[i - 1]["l"]) / 2)
        box = kl[i]["v"] / ((kl[i]["h"] - kl[i]["l"]) or 1e-9)
        eom.append(dist / (box or 1e-9))
    s = sum(eom[-p:]) / p
    return "UP" if s > 0 else "DOWN" if s < 0 else "NEUTRAL"


def price_channel(kl, p=20):
    return donchian_channel(kl, p)


def breakout_retest(kl):
    if len(kl) < 25:
        return "NEUTRAL"
    w = kl[-22:-2]
    hi, lo = max(k["h"] for k in w), min(k["l"] for k in w)
    recent = kl[-2:]
    if recent[0]["c"] > hi and recent[1]["c"] >= hi * 0.998:
        return "UP"
    if recent[0]["c"] < lo and recent[1]["c"] <= lo * 1.002:
        return "DOWN"
    return "NEUTRAL"


def range_bounce(kl):
    if len(kl) < 30:
        return "NEUTRAL"
    w = kl[-30:-1]
    hi, lo = max(k["h"] for k in w), min(k["l"] for k in w)
    mid = (hi + lo) / 2
    px = kl[-1]["c"]
    if px <= lo * 1.002:
        return "UP"
    if px >= hi * 0.998:
        return "DOWN"
    return "UP" if px < mid else "DOWN"


def volume_spike(kl):
    if len(kl) < 25:
        return "NEUTRAL"
    avg = sum(k["v"] for k in kl[-21:-1]) / 20
    if not avg:
        return "NEUTRAL"
    if kl[-1]["v"] < avg * 1.8:
        return "NEUTRAL"
    return "UP" if kl[-1]["c"] > kl[-1]["o"] else "DOWN"


def fvg_proxy(kl):
    if len(kl) < 4:
        return "NEUTRAL"
    a, b, c = kl[-3], kl[-2], kl[-1]
    if a["h"] < c["l"]:
        return "UP"
    if a["l"] > c["h"]:
        return "DOWN"
    return "NEUTRAL"


def order_block_proxy(kl):
    if len(kl) < 6:
        return "NEUTRAL"
    for k in kl[-5:-1]:
        body = abs(k["c"] - k["o"])
        rng = k["h"] - k["l"]
        if rng and body / rng > 0.65:
            if k["c"] > k["o"] and kl[-1]["c"] > k["h"]:
                return "UP"
            if k["c"] < k["o"] and kl[-1]["c"] < k["l"]:
                return "DOWN"
    return "NEUTRAL"


def liquidity_sweep_proxy(kl):
    if len(kl) < 10:
        return "NEUTRAL"
    w = kl[-10:-1]
    hi, lo = max(k["h"] for k in w), min(k["l"] for k in w)
    cur = kl[-1]
    if cur["h"] > hi and cur["c"] < hi:
        return "DOWN"
    if cur["l"] < lo and cur["c"] > lo:
        return "UP"
    return "NEUTRAL"


def wyckoff_proxy(kl):
    if len(kl) < 40:
        return "NEUTRAL"
    w = kl[-40:]
    vol = [k["v"] for k in w]
    px = [k["c"] for k in w]
    v_avg = sum(vol) / len(vol)
    price_range = max(px) - min(px)
    if not price_range:
        return "NEUTRAL"
    recent_vol = sum(vol[-10:]) / 10
    drift = px[-1] - px[-20]
    if recent_vol > v_avg * 1.2 and abs(drift) < price_range * 0.1:
        return "UP" if px[-1] > sum(px[-10:]) / 10 else "DOWN"
    return ema_crossover(kl)


def gmma(kl):
    c = _closes(kl)
    if len(c) < 60:
        return "NEUTRAL"
    short = [_ema(c, p)[-1] for p in (3, 5, 8, 10, 12, 15)]
    long = [_ema(c, p)[-1] for p in (30, 35, 40, 45, 50, 60)]
    if None in short + long:
        return "NEUTRAL"
    if min(short) > max(long):
        return "UP"
    if max(short) < min(long):
        return "DOWN"
    return "UP" if sum(short) / len(short) > sum(long) / len(long) else "DOWN"


def mcginley_dynamic(kl, p=14):
    c = _closes(kl)
    if len(c) < p + 5:
        return "NEUTRAL"
    md = c[0]
    for price in c[1:]:
        md = md + (price - md) / (p * (price / (md or 1e-9)) ** 4)
    return "UP" if c[-1] > md else "DOWN"


def schaff_trend_cycle(kl):
    return stoch_rsi(kl)


def tsi(kl, r=25, s=13):
    c = _closes(kl)
    if len(c) < r + s + 5:
        return "NEUTRAL"
    pc = [c[i] - c[i - 1] for i in range(1, len(c))]
    abs_pc = [abs(x) for x in pc]
    def _double_smooth(vals, period):
        e1 = [x for x in _ema(vals, period) if x is not None]
        e2 = [x for x in _ema(e1, period) if x is not None]
        return e2[-1] if e2 else 0
    num = _double_smooth(pc, r)
    den = _double_smooth(abs_pc, r) or 1e-9
    tsi = num / den * 100
    return "UP" if tsi > 0 else "DOWN"


def kst(kl):
    c = _closes(kl)
    if len(c) < 30:
        return "NEUTRAL"

    def _roc(n):
        return (c[-1] - c[-1 - n]) / (c[-1 - n] or 1e-9) * 100 if len(c) > n else 0

    kst = _roc(10) + 2 * _roc(15) + 3 * _roc(20) + 4 * _roc(30)
    return "UP" if kst > 0 else "DOWN"


def fractal_breakout(kl):
    if len(kl) < 7:
        return "NEUTRAL"
    highs = [kl[i]["h"] for i in range(-5, 0)]
    if kl[-3]["h"] == max(highs) and kl[-1]["c"] > kl[-3]["h"]:
        return "UP"
    lows = [kl[i]["l"] for i in range(-5, 0)]
    if kl[-3]["l"] == min(lows) and kl[-1]["c"] < kl[-3]["l"]:
        return "DOWN"
    return "NEUTRAL"


def alligator(kl):
    c = _closes(kl)
    if len(c) < 21:
        return "NEUTRAL"
    jaw = _ema(c, 13)
    teeth = _ema(c, 8)
    lips = _ema(c, 5)
    if None in (jaw[-1], teeth[-1], lips[-1]):
        return "NEUTRAL"
    if lips[-1] > teeth[-1] > jaw[-1]:
        return "UP"
    if lips[-1] < teeth[-1] < jaw[-1]:
        return "DOWN"
    return "NEUTRAL"


def hurst_proxy(kl):
    c = _closes(kl)
    if len(c) < 50:
        return "NEUTRAL"
    lags = [2, 4, 8, 16]
    rs_vals = []
    for lag in lags:
        diff = [c[i] - c[i - lag] for i in range(lag, len(c))]
        if not diff:
            continue
        m = sum(diff) / len(diff)
        std = math.sqrt(sum((d - m) ** 2 for d in diff) / len(diff)) or 1e-9
        rs_vals.append((max(diff) - min(diff)) / std)
    if len(rs_vals) < 2:
        return "NEUTRAL"
    # H > 0.5 trend, H < 0.5 mean reversion
    trendish = rs_vals[-1] > rs_vals[0]
    return ema_crossover(kl) if trendish else mean_reversion(kl)


def zscore_pairs_proxy(kl):
    return mean_reversion(kl)


def markov_simple(kl):
    c = _closes(kl)
    if len(c) < 30:
        return "NEUTRAL"
    ups = sum(1 for i in range(-20, 0) if c[i] > c[i - 1])
    p_up = ups / 20
    if p_up > 0.6:
        return "UP"
    if p_up < 0.4:
        return "DOWN"
    return "NEUTRAL"


def h1_combo_extended(kl):
    s1 = ema_crossover(kl)
    s2 = macd_div(kl)
    s3 = money_flow_index(kl)
    votes = [s for s in (s1, s2, s3) if s in ("UP", "DOWN")]
    if not votes:
        return "NEUTRAL"
    up = votes.count("UP")
    if up >= 2:
        return "UP"
    if up <= 0:
        return "DOWN"
    return "NEUTRAL"


# id, kategori, isim, fonksiyon
EXTENDED_CATALOG = [
    (40, "Momentum", "Williams %R", williams_r),
    (41, "Momentum", "CCI", cci),
    (42, "Hacim", "Chaikin Money Flow", chaikin_mf),
    (43, "Trend", "Aroon Indicator", aroon),
    (44, "Momentum", "TRIX", trix),
    (45, "Momentum", "Ultimate Oscillator", ultimate_oscillator),
    (46, "Momentum", "Awesome Oscillator", awesome_oscillator),
    (47, "Momentum", "Coppock Curve", coppock_curve),
    (48, "Trend", "Vortex Indicator", vortex_indicator),
    (49, "Hacim", "Elder Force Index", elder_force_index),
    (50, "Volatilite", "Choppiness Index", choppiness_index),
    (51, "Price Action", "Pivot Points", pivot_points),
    (52, "Price Action", "Fibonacci Retracement", fib_retracement),
    (53, "Momentum", "ROC Momentum", roc_momentum),
    (54, "Momentum", "PPO", ppo),
    (55, "Trend", "KAMA", kama),
    (56, "Trend", "Linear Regression Slope", linreg_slope),
    (57, "Order Flow", "Taker Buy Ratio", taker_buy_ratio),
    (58, "Order Flow", "CVD Proxy", cvd_proxy),
    (59, "Price Action", "Higher High / Higher Low", higher_high_trend),
    (60, "Price Action", "Engulfing Pattern", engulfing_pattern),
    (61, "Price Action", "Inside Bar Breakout", inside_bar_breakout),
    (62, "Volatilite", "Squeeze Momentum (BB+KC)", squeeze_momentum),
    (63, "Hacim", "Accumulation/Distribution", accumulation_distribution),
    (64, "Hacim", "Ease of Movement", ease_of_movement),
    (65, "Breakout", "Price Channel (Donchian)", price_channel),
    (66, "Breakout", "Breakout + Retest", breakout_retest),
    (67, "Range", "Range Trading S/R Bounce", range_bounce),
    (68, "Hacim", "Volume Spike Momentum", volume_spike),
    (69, "SMC", "Fair Value Gap Proxy", fvg_proxy),
    (70, "SMC", "Order Block Proxy", order_block_proxy),
    (71, "SMC", "Liquidity Sweep Proxy", liquidity_sweep_proxy),
    (72, "Price Action", "Wyckoff Proxy", wyckoff_proxy),
    (73, "Trend", "GMMA", gmma),
    (74, "Trend", "McGinley Dynamic", mcginley_dynamic),
    (75, "Momentum", "Schaff Trend Cycle", schaff_trend_cycle),
    (76, "Momentum", "True Strength Index (TSI)", tsi),
    (77, "Momentum", "Know Sure Thing (KST)", kst),
    (78, "Price Action", "Fractal Breakout", fractal_breakout),
    (79, "Trend", "Alligator Indicator", alligator),
    (80, "İstatistik", "Hurst Proxy (trend/MR)", hurst_proxy),
    (81, "İstatistik", "Z-Score Mean Reversion", zscore_pairs_proxy),
    (82, "İstatistik", "Markov Chain Simple", markov_simple),
    (83, "Kombinasyon", "EMA+MACD+MFI Combo", h1_combo_extended),
]

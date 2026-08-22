#!/usr/bin/env python3
"""
algo_signals.py — 36 algoritma için BTC/ETH/SOL saatlik sinyal üretici
(21 teknik + 15 gelişmiş algoritma)
Her :04:40'ta cron ile çalışır (4 * * * * sleep 40), /tmp/algo_signals.json'a kaydeder
"""
import json, requests, datetime, math, os, sys

SYMBOLS       = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
FUTURES       = "https://fapi.binance.com"
OUT_FILE      = "/tmp/algo_signals.json"
PREV_FILE     = "/tmp/algo_signals_prev.json"
_DIR          = os.path.dirname(os.path.abspath(__file__))
ACCURACY_FILE = os.path.join(_DIR, "algo_accuracy.json")

# ── Binance veri çekimi ───────────────────────────────────────────────

def fetch_klines(pair, interval="1h", limit=200):
    """Mum — süreç önbelleği + fapi ban'de spot. Aynı BTC 1h'ı 17 kez çekme."""
    root = os.path.dirname(_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from binance_fapi_guard import public_klines  # noqa: WPS433
        data = public_klines(pair, interval, limit)
    except Exception as e:
        raise RuntimeError(f"binance klines hata {pair} {interval} {e}") from e
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"binance klines hata {pair} {interval} boş")
    return [{"o": float(x[1]), "h": float(x[2]), "l": float(x[3]),
             "c": float(x[4]), "v": float(x[5])} for x in data]

# ── Teknik göstergeler ────────────────────────────────────────────────

def _ema(values, p):
    k, res = 2 / (p + 1), [None] * len(values)
    if len(values) < p: return res
    res[p - 1] = sum(values[:p]) / p
    for i in range(p, len(values)):
        res[i] = values[i] * k + res[i - 1] * (1 - k)
    return res

def _rsi(closes, p=14):
    res = [None] * len(closes)
    if len(closes) < p + 1: return res
    gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:p]) / p
    al = sum(losses[:p]) / p
    res[p] = 100 - 100 / (1 + ag / al) if al else 100.0
    for i in range(p + 1, len(closes)):
        ag = (ag * (p - 1) + gains[i - 1]) / p
        al = (al * (p - 1) + losses[i - 1]) / p
        res[i] = 100 - 100 / (1 + ag / al) if al else 100.0
    return res

def _atr(klines, p=14):
    trs = [max(klines[i]["h"] - klines[i]["l"],
               abs(klines[i]["h"] - klines[i-1]["c"]),
               abs(klines[i]["l"] - klines[i-1]["c"])) for i in range(1, len(klines))]
    res = [None] * len(klines)
    if len(trs) < p: return res
    res[p] = sum(trs[:p]) / p
    for i in range(p + 1, len(klines)):
        res[i] = (res[i-1] * (p-1) + trs[i-1]) / p
    return res

def _std(vals):
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)), m

# ── Algoritmalar ──────────────────────────────────────────────────────

def ema_crossover(kl):
    c = [k["c"] for k in kl]
    e9, e21, e50, e200 = _ema(c, 9), _ema(c, 21), _ema(c, 50), _ema(c, 200)
    if None in (e9[-1], e21[-1], e50[-1], e200[-1]): return "NEUTRAL"
    fb = e9[-1] > e21[-1]
    sb = e50[-1] > e200[-1]
    return "UP" if fb and sb else "DOWN" if not fb and not sb else "NEUTRAL"

def macd_div(kl):
    c = [k["c"] for k in kl]
    e12, e26 = _ema(c, 12), _ema(c, 26)
    ml = [e12[i] - e26[i] if e12[i] and e26[i] else None for i in range(len(c))]
    valid = [x for x in ml if x is not None]
    if len(valid) < 9: return "NEUTRAL"
    sl = _ema(valid, 9)
    if sl[-1] is None or sl[-2] is None: return "NEUTRAL"
    m, s = valid[-1], sl[-1]
    mp, sp = valid[-2], sl[-2]
    if mp < sp and m > s: return "UP"
    if mp > sp and m < s: return "DOWN"
    return "UP" if m > s else "DOWN"

def supertrend(kl, p=10, mult=3.0):
    if len(kl) < p + 5: return "NEUTRAL"
    c = [k["c"] for k in kl]
    h = [k["h"] for k in kl]
    l = [k["l"] for k in kl]
    av = _atr(kl, p)
    up = [None]*len(kl); dn = [None]*len(kl)
    st = [None]*len(kl); dr = [0]*len(kl)
    for i in range(p, len(kl)):
        if av[i] is None: continue
        hl2 = (h[i] + l[i]) / 2
        bu = hl2 + mult * av[i]
        bl = hl2 - mult * av[i]
        up[i] = min(bu, up[i-1]) if up[i-1] and c[i-1] > up[i-1] else bu
        dn[i] = max(bl, dn[i-1]) if dn[i-1] and c[i-1] < dn[i-1] else bl
        if st[i-1] is None:
            st[i] = up[i]; dr[i] = -1
        elif st[i-1] == up[i-1]:
            if c[i] < up[i]: st[i] = up[i]; dr[i] = -1
            else:             st[i] = dn[i]; dr[i] =  1
        else:
            if c[i] > dn[i]: st[i] = dn[i]; dr[i] =  1
            else:             st[i] = up[i]; dr[i] = -1
    return "UP" if dr[-1] == 1 else "DOWN" if dr[-1] == -1 else "NEUTRAL"

def ichimoku(kl):
    if len(kl) < 52: return "NEUTRAL"
    h = [k["h"] for k in kl]; l = [k["l"] for k in kl]; c = [k["c"] for k in kl]
    def don(p, off=0):
        idx = -(1 + off)
        s = slice(idx - p + 1, idx + 1) if idx + 1 else slice(idx - p + 1, None)
        return (max(h[s]) + min(l[s])) / 2
    tenkan  = don(9)
    kijun   = don(26)
    sa      = (don(9, 26) + don(26, 26)) / 2
    sb      = don(52, 26)
    price   = c[-1]
    ct, cb  = max(sa, sb), min(sa, sb)
    bull    = (2 if price > ct else 0) + (1 if tenkan > kijun else 0)
    bear    = (2 if price < cb else 0) + (1 if tenkan < kijun else 0)
    return "UP" if bull > bear else "DOWN" if bear > bull else "NEUTRAL"

def rsi_div(kl):
    c   = [k["c"] for k in kl]
    rv  = _rsi(c, 14)
    lr  = next((x for x in reversed(rv) if x), None)
    if lr is None: return "NEUTRAL"
    if lr < 30: return "UP"
    if lr > 70: return "DOWN"
    window_c = c[-10:]; window_r = [x for x in rv[-10:] if x]
    if len(window_r) >= 5:
        if c[-1] >= max(window_c) * .999 and lr < max(window_r) * .97: return "DOWN"
        if c[-1] <= min(window_c) * 1.001 and lr > min(window_r) * 1.03: return "UP"
    return "UP" if lr > 55 else "DOWN" if lr < 45 else "NEUTRAL"

def stoch_rsi(kl):
    c   = [k["c"] for k in kl]
    rv  = [x for x in _rsi(c, 14) if x is not None]
    if len(rv) < 14: return "NEUTRAL"
    w   = rv[-14:]
    mn, mx = min(w), max(w)
    if mx == mn: return "NEUTRAL"
    st  = (rv[-1] - mn) / (mx - mn) * 100
    stp = (rv[-2] - mn) / (mx - mn) * 100 if len(rv) >= 2 else st
    if st < 20 and st > stp: return "UP"
    if st > 80 and st < stp: return "DOWN"
    return "UP" if st < 50 else "DOWN"

def bb_squeeze(kl):
    c = [k["c"] for k in kl]
    if len(c) < 20: return "NEUTRAL"
    std20, m20 = _std(c[-20:])
    upper, lower = m20 + 2*std20, m20 - 2*std20
    pct = (c[-1] - lower) / (upper - lower) if upper > lower else .5
    return "DOWN" if pct > .8 else "UP" if pct < .2 else "UP" if pct > .5 else "DOWN"

def vwap(kl):
    w = kl[-24:] if len(kl) >= 24 else kl
    tv = sum(k["v"] for k in w)
    if not tv: return "NEUTRAL"
    v  = sum(((k["h"]+k["l"]+k["c"])/3)*k["v"] for k in w) / tv
    p  = kl[-1]["c"]
    return "UP" if p > v*1.001 else "DOWN" if p < v*.999 else "NEUTRAL"

def obv(kl):
    vals = [0]
    for i in range(1, len(kl)):
        if kl[i]["c"] > kl[i-1]["c"]:   vals.append(vals[-1] + kl[i]["v"])
        elif kl[i]["c"] < kl[i-1]["c"]: vals.append(vals[-1] - kl[i]["v"])
        else:                            vals.append(vals[-1])
    oe = _ema(vals, 20)
    if oe[-1] is None or oe[-2] is None: return "NEUTRAL"
    return "UP" if vals[-1] > oe[-1] and oe[-1] > oe[-2] else \
           "DOWN" if vals[-1] < oe[-1] and oe[-1] < oe[-2] else "NEUTRAL"

def volume_profile(kl):
    if len(kl) < 50: return "NEUTRAL"
    w = kl[-50:]
    pmin = min(k["l"] for k in w); pmax = max(k["h"] for k in w)
    if pmax == pmin: return "NEUTRAL"
    bins = [0.0] * 20; bs = (pmax - pmin) / 20
    for k in w:
        mid = (k["h"]+k["l"]+k["c"]) / 3
        bins[min(int((mid - pmin) / bs), 19)] += k["v"]
    poc = pmin + (bins.index(max(bins)) + .5) * bs
    p   = kl[-1]["c"]
    return "DOWN" if poc > p*1.01 else "UP" if poc < p*.99 else "NEUTRAL"

def mean_reversion(kl):
    c = [k["c"] for k in kl]
    if len(c) < 20: return "NEUTRAL"
    std, mean = _std(c[-20:])
    if not std: return "NEUTRAL"
    z = (c[-1] - mean) / std
    return "UP" if z < -1.5 else "DOWN" if z > 1.5 else \
           "UP" if z < -.5 else "DOWN" if z > .5 else "NEUTRAL"

def pairs_trading(klines_dict):
    eth = klines_dict.get("ETH", [])
    btc = klines_dict.get("BTC", [])
    n   = min(len(eth), len(btc))
    neutral = {sym: "NEUTRAL" for sym in SYMBOLS}
    if n < 20: return neutral
    ratios = [eth[i]["c"] / btc[i]["c"] for i in range(n) if btc[i]["c"]]
    std, mean = _std(ratios[-20:])
    if not std: return neutral
    z = (ratios[-1] - mean) / std
    result = dict(neutral)
    result["ETH"] = "UP" if z < -1 else "DOWN" if z > 1 else "NEUTRAL"
    result["BTC"] = "DOWN" if z < -1 else "UP" if z > 1 else "NEUTRAL"
    return result

def multi_tf(kl_1h, kl_4h):
    s1 = ema_crossover(kl_1h)
    s4 = ema_crossover(kl_4h)
    if s1 == s4 and s1 != "NEUTRAL": return s1
    return s4 if s4 != "NEUTRAL" else s1

# ── Yeni algoritmalar (16-21) ─────────────────────────────────────────

def atr_breakout(kl, p=14):
    """ATR Momentum Breakout — fiyat ATR bandını kırınca yön tespiti"""
    if len(kl) < p + 10: return "NEUTRAL"
    c   = [k["c"] for k in kl]
    av  = _atr(kl, p)
    atr = next((x for x in reversed(av) if x), None)
    if atr is None: return "NEUTRAL"
    hi  = max(k["h"] for k in kl[-11:-1])
    lo  = min(k["l"] for k in kl[-11:-1])
    px  = c[-1]
    if px > hi + atr * 0.5: return "UP"
    if px < lo - atr * 0.5: return "DOWN"
    e20 = _ema(c, 20)
    if e20[-1] is None: return "NEUTRAL"
    diff = px - e20[-1]
    if diff >  atr * 0.3: return "UP"
    if diff < -atr * 0.3: return "DOWN"
    return "NEUTRAL"

def heikin_ashi(kl):
    """Heikin Ashi Trend — gürültü azaltılmış trend yönü"""
    if len(kl) < 5: return "NEUTRAL"
    ha = []
    for k in kl:
        ha_c = (k["o"] + k["h"] + k["l"] + k["c"]) / 4
        ha_o = (ha[-1]["o"] + ha[-1]["c"]) / 2 if ha else (k["o"] + k["c"]) / 2
        ha_h = max(k["h"], ha_o, ha_c)
        ha_l = min(k["l"], ha_o, ha_c)
        ha.append({"o": ha_o, "h": ha_h, "l": ha_l, "c": ha_c})
    last3 = ha[-3:]
    bull = sum(1 for x in last3 if x["c"] > x["o"] and x["l"] >= min(x["o"], x["c"]) * 0.9999)
    bear = sum(1 for x in last3 if x["c"] < x["o"] and x["h"] <= max(x["o"], x["c"]) * 1.0001)
    if bull >= 2: return "UP"
    if bear >= 2: return "DOWN"
    return "UP" if ha[-1]["c"] > ha[-1]["o"] else "DOWN"

def tema_crossover(kl):
    """TEMA Crossover (9/21) — lag azaltılmış EMA kesişimi"""
    c = [k["c"] for k in kl]
    if len(c) < 70: return "NEUTRAL"
    def _tema_val(vals, p):
        e1 = _ema(vals, p)
        v1 = [x for x in e1 if x is not None]
        if len(v1) < p: return None, None
        e2 = _ema(v1, p)
        v2 = [x for x in e2 if x is not None]
        if len(v2) < p: return None, None
        e3 = _ema(v2, p)
        if e3[-1] is None or e3[-2] is None: return None, None
        return 3*v1[-1] - 3*v2[-1] + e3[-1], 3*v1[-2] - 3*v2[-2] + e3[-2]
    fc, fp = _tema_val(c, 9)
    sc, sp = _tema_val(c, 21)
    if fc is None or sc is None: return "NEUTRAL"
    if fp < sp and fc > sc: return "UP"
    if fp > sp and fc < sc: return "DOWN"
    return "UP" if fc > sc else "DOWN" if fc < sc else "NEUTRAL"

def adx_regime(kl, p=14):
    """ADX Market Regime — trend gücü + yön (ADX>25 trend, <20 nötr)"""
    if len(kl) < p * 2 + 5: return "NEUTRAL"
    pdm, mdm, trs = [], [], []
    for i in range(1, len(kl)):
        up  = kl[i]["h"] - kl[i-1]["h"]
        dn  = kl[i-1]["l"] - kl[i]["l"]
        pdm.append(up if up > dn and up > 0 else 0)
        mdm.append(dn if dn > up and dn > 0 else 0)
        tr  = max(kl[i]["h"] - kl[i]["l"],
                  abs(kl[i]["h"] - kl[i-1]["c"]),
                  abs(kl[i]["l"] - kl[i-1]["c"]))
        trs.append(tr)
    if len(trs) < p: return "NEUTRAL"
    atr_s = sum(trs[:p]); ps = sum(pdm[:p]); ms = sum(mdm[:p])
    dx_list = []
    for i in range(p, len(trs)):
        atr_s = atr_s - atr_s/p + trs[i]
        ps    = ps    - ps/p    + pdm[i]
        ms    = ms    - ms/p    + mdm[i]
        pdi   = 100 * ps / atr_s if atr_s else 0
        mdi   = 100 * ms / atr_s if atr_s else 0
        sm    = pdi + mdi
        dx_list.append(100 * abs(pdi - mdi) / sm if sm else 0)
    if len(dx_list) < p: return "NEUTRAL"
    adx = sum(dx_list[:p]) / p
    for v in dx_list[p:]: adx = (adx * (p-1) + v) / p
    # Final DI values
    atr_s = sum(trs[:p]); ps = sum(pdm[:p]); ms = sum(mdm[:p])
    for i in range(p, len(trs)):
        atr_s = atr_s - atr_s/p + trs[i]
        ps    = ps    - ps/p    + pdm[i]
        ms    = ms    - ms/p    + mdm[i]
    pdi = 100 * ps / atr_s if atr_s else 0
    mdi = 100 * ms / atr_s if atr_s else 0
    if adx < 20: return "NEUTRAL"
    return "UP" if pdi > mdi else "DOWN"

def fetch_oi_hist(pair, limit=10):
    """Binance Futures OI geçmişi"""
    r = requests.get(f"{FUTURES}/futures/data/openInterestHist",
                     params={"symbol": pair, "period": "1h", "limit": limit},
                     timeout=8)
    data = r.json()
    if isinstance(data, list) and data:
        return [float(x["sumOpenInterestValue"]) for x in data]
    return []

def oi_divergence(kl, pair):
    """OI Divergence — fiyat+OI yönü uyumu (Binance Futures)"""
    try:
        oi = fetch_oi_hist(pair, 10)
        if len(oi) < 5: return "NEUTRAL"
        c = [k["c"] for k in kl[-10:]]
        if len(c) < 5: return "NEUTRAL"
        pc = (c[-1] - c[-5]) / c[-5] if c[-5] else 0
        oc = (oi[-1] - oi[-5]) / oi[-5] if oi[-5] else 0
        if pc >  0.005 and oc >  0.005: return "UP"    # Her iki yükseliyor: güçlü trend
        if pc < -0.005 and oc >  0.005: return "DOWN"  # Short ekliyor
        if pc >  0.005 and oc < -0.005: return "DOWN"  # Zayıf ralli, dönüş riski
        if pc < -0.005 and oc < -0.005: return "UP"    # Short kapatma potansiyeli
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"

def fetch_fear_greed():
    """Alternative.me Fear & Greed Index (0=aşırı korku, 100=aşırı açgözlülük)"""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6)
        val = int(r.json()["data"][0]["value"])
        if val <= 20: return "UP"    # Extreme Fear → kontrarian al
        if val >= 80: return "DOWN"  # Extreme Greed → kontrarian sat
        if val <= 35: return "UP"
        if val >= 65: return "DOWN"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"

# ── Yeni algoritmalar (25-39) ─────────────────────────────────────────

def parabolic_sar_adx(kl, af_start=0.02, af_max=0.2):
    """25. Parabolic SAR + ADX — SAR yönü + ADX>25 trend filtresi"""
    if len(kl) < 30: return "NEUTRAL"
    # ADX hesapla
    adx_sig = adx_regime(kl, 14)
    if adx_sig == "NEUTRAL": return "NEUTRAL"
    # Parabolic SAR
    h = [k["h"] for k in kl]; l = [k["l"] for k in kl]; c = [k["c"] for k in kl]
    bull = True; sar = l[0]; ep = h[0]; af = af_start
    for i in range(1, len(kl)):
        sar = sar + af * (ep - sar)
        if bull:
            sar = min(sar, l[i-1], l[i-2] if i >= 2 else l[i-1])
            if c[i] < sar:
                bull = False; sar = ep; ep = l[i]; af = af_start
            else:
                if h[i] > ep: ep = h[i]; af = min(af + af_start, af_max)
        else:
            sar = max(sar, h[i-1], h[i-2] if i >= 2 else h[i-1])
            if c[i] > sar:
                bull = True; sar = ep; ep = h[i]; af = af_start
            else:
                if l[i] < ep: ep = l[i]; af = min(af + af_start, af_max)
    return "UP" if bull else "DOWN"

def macd_histogram_div(kl):
    """26. MACD Histogram Divergence — histogram zirve/dip sapması"""
    c = [k["c"] for k in kl]
    e12, e26 = _ema(c, 12), _ema(c, 26)
    ml = [e12[i] - e26[i] if e12[i] and e26[i] else None for i in range(len(c))]
    valid = [x for x in ml if x is not None]
    if len(valid) < 12: return "NEUTRAL"
    sl = _ema(valid, 9)
    hist = [valid[i] - sl[i] for i in range(len(sl)) if sl[i] is not None]
    if len(hist) < 5: return "NEUTRAL"
    # Yükselen fiyat + düşen histogram → bearish div
    if (c[-1] > c[-5] and hist[-1] < hist[-5] and hist[-1] > 0): return "DOWN"
    # Düşen fiyat + yükselen histogram → bullish div
    if (c[-1] < c[-5] and hist[-1] > hist[-5] and hist[-1] < 0): return "UP"
    # Basit trend
    return "UP" if hist[-1] > 0 and hist[-1] > hist[-2] else \
           "DOWN" if hist[-1] < 0 and hist[-1] < hist[-2] else "NEUTRAL"

def stoch_rsi_kd(kl, rsi_p=14, stoch_p=14, smooth_k=3, smooth_d=3):
    """27. Stochastic RSI (14) K/D Kesişimi — aşırı bölge + crossover"""
    c = [k["c"] for k in kl]
    rv = [x for x in _rsi(c, rsi_p) if x is not None]
    if len(rv) < stoch_p + smooth_k + smooth_d: return "NEUTRAL"
    # K hesapla
    k_raw = []
    for i in range(stoch_p, len(rv)):
        window = rv[i-stoch_p:i]
        mn, mx = min(window), max(window)
        k_raw.append((rv[i] - mn) / (mx - mn) * 100 if mx > mn else 50.0)
    if len(k_raw) < smooth_k + smooth_d: return "NEUTRAL"
    k_line = _ema(k_raw, smooth_k)
    k_v = [x for x in k_line if x is not None]
    if len(k_v) < smooth_d: return "NEUTRAL"
    d_line = _ema(k_v, smooth_d)
    d_v = [x for x in d_line if x is not None]
    if len(d_v) < 2: return "NEUTRAL"
    k_last, k_prev = k_v[-1], k_v[-2]
    d_last, d_prev = d_v[-1], d_v[-2]
    if k_prev < d_prev and k_last > d_last and k_last < 80: return "UP"
    if k_prev > d_prev and k_last < d_last and k_last > 20: return "DOWN"
    return "UP" if k_last < 20 else "DOWN" if k_last > 80 else \
           "UP" if k_last > d_last else "DOWN"

def triple_ema(kl):
    """28. Triple EMA (8, 21, 55) — üçlü hizalanma trendi"""
    c = [k["c"] for k in kl]
    if len(c) < 60: return "NEUTRAL"
    e8  = _ema(c, 8)
    e21 = _ema(c, 21)
    e55 = _ema(c, 55)
    if None in (e8[-1], e21[-1], e55[-1]): return "NEUTRAL"
    if e8[-1] > e21[-1] > e55[-1]: return "UP"
    if e8[-1] < e21[-1] < e55[-1]: return "DOWN"
    # Kısmi hizalama
    if e8[-1] > e21[-1]: return "UP"
    if e8[-1] < e21[-1]: return "DOWN"
    return "NEUTRAL"

def _wma(values, p):
    """Weighted Moving Average"""
    if len(values) < p: return None
    weights = list(range(1, p + 1))
    total_w = sum(weights)
    return sum(values[-(p-i)] * weights[i] for i in range(p)) / total_w

def hull_ma(kl, p=20):
    """29. Hull Moving Average (HMA) — lag azaltılmış trend"""
    c = [k["c"] for k in kl]
    if len(c) < p + int(math.sqrt(p)) + 5: return "NEUTRAL"
    half_p = max(p // 2, 2)
    sqrt_p = max(int(math.sqrt(p)), 2)
    hma_series = []
    for i in range(p - 1, len(c)):
        w1 = _wma(c[:i+1], half_p)
        w2 = _wma(c[:i+1], p)
        if w1 is None or w2 is None: continue
        hma_series.append(2 * w1 - w2)
    if len(hma_series) < sqrt_p + 2: return "NEUTRAL"
    final = []
    for i in range(sqrt_p, len(hma_series)):
        v = _wma(hma_series[i-sqrt_p:i+1], sqrt_p)
        if v is not None: final.append(v)
    if len(final) < 3: return "NEUTRAL"
    if final[-1] > final[-2] > final[-3]: return "UP"
    if final[-1] < final[-2] < final[-3]: return "DOWN"
    return "UP" if final[-1] > final[-2] else "DOWN"

def keltner_channel(kl, ema_p=20, atr_p=10, mult=2.0):
    """30. Keltner Kanalı (20, 2) — kanal kırılımı / pozisyon"""
    if len(kl) < ema_p + atr_p + 5: return "NEUTRAL"
    c = [k["c"] for k in kl]
    e = _ema(c, ema_p)
    av = _atr(kl, atr_p)
    if e[-1] is None or av[-1] is None: return "NEUTRAL"
    upper = e[-1] + mult * av[-1]
    lower = e[-1] - mult * av[-1]
    px = c[-1]
    if px > upper: return "UP"    # Üst bant kırıldı → güçlü trend
    if px < lower: return "DOWN"  # Alt bant kırıldı
    # Kanal içi: pozisyon
    mid = (upper + lower) / 2
    return "UP" if px > mid else "DOWN"

def donchian_channel(kl, p=20):
    """31. Donchian Kanalı (20) — fiyat yüksek/düşük pozisyonu"""
    if len(kl) < p + 3: return "NEUTRAL"
    window = kl[-(p+1):-1]  # son p bar (şimdiki hariç)
    upper = max(k["h"] for k in window)
    lower = min(k["l"] for k in window)
    c = kl[-1]["c"]
    mid = (upper + lower) / 2
    rng = upper - lower
    if not rng: return "NEUTRAL"
    # Kırılım
    if c > upper: return "UP"
    if c < lower: return "DOWN"
    # Pozisyon skoru
    pct = (c - lower) / rng
    return "UP" if pct > 0.6 else "DOWN" if pct < 0.4 else "NEUTRAL"

def vwap_volume_profile(kl):
    """32. VWAP + Hacim Profili — ikisi aynı yönü gösterirse sinyal"""
    s_v = vwap(kl)
    s_p = volume_profile(kl)
    if s_v == s_p and s_v != "NEUTRAL": return s_v
    # Tek taraflı sinyal
    if s_v != "NEUTRAL": return s_v
    return s_p

def money_flow_index(kl, p=14):
    """33. Money Flow Index (MFI) — hacim ağırlıklı RSI"""
    if len(kl) < p + 2: return "NEUTRAL"
    tp    = [(k["h"] + k["l"] + k["c"]) / 3 for k in kl]
    mf    = [tp[i] * kl[i]["v"] for i in range(len(kl))]
    pos_mf = [mf[i] if tp[i] > tp[i-1] else 0 for i in range(1, len(tp))]
    neg_mf = [mf[i] if tp[i] < tp[i-1] else 0 for i in range(1, len(tp))]
    pmf_sum = sum(pos_mf[-p:]); nmf_sum = sum(neg_mf[-p:])
    if not nmf_sum: return "UP"
    mfi = 100 - 100 / (1 + pmf_sum / nmf_sum)
    if mfi < 20: return "UP"    # Aşırı satım
    if mfi > 80: return "DOWN"  # Aşırı alım
    # Trend yönü
    return "UP" if mfi > 55 else "DOWN" if mfi < 45 else "NEUTRAL"

def random_forest_clf(kl):
    """34. Random Forest Classifier (basit) — çoklu özellik çoğunluk oyu"""
    if len(kl) < 55: return "NEUTRAL"
    c = [k["c"] for k in kl]
    # Özellikler (her biri +1 UP, -1 DOWN, 0 nötr)
    features = []
    # F1: RSI pozisyonu
    rv = _rsi(c, 14); rsi_v = next((x for x in reversed(rv) if x), 50)
    features.append(+1 if rsi_v < 45 else -1 if rsi_v > 55 else 0)
    # F2: EMA trend
    e20, e50 = _ema(c, 20), _ema(c, 50)
    features.append(+1 if (e20[-1] and e50[-1] and e20[-1] > e50[-1]) else -1)
    # F3: Bollinger pozisyonu
    std, mean = _std(c[-20:])
    features.append(-1 if c[-1] > mean + 1.5*std else +1 if c[-1] < mean - 1.5*std else 0)
    # F4: MACD yönü
    e12, e26 = _ema(c, 12), _ema(c, 26)
    ml = [e12[i]-e26[i] if e12[i] and e26[i] else 0 for i in range(len(c))]
    sl = _ema(ml, 9)
    features.append(+1 if (sl[-1] and ml[-1] > sl[-1]) else -1)
    # F5: Hacim trendi
    avg_vol = sum(k["v"] for k in kl[-20:]) / 20
    features.append(+1 if kl[-1]["v"] > avg_vol * 1.3 and c[-1] > c[-2] else
                    -1 if kl[-1]["v"] > avg_vol * 1.3 and c[-1] < c[-2] else 0)
    # F6: Fiyat momentum (5 bar)
    features.append(+1 if c[-1] > c[-5] * 1.002 else -1 if c[-1] < c[-5] * 0.998 else 0)
    score = sum(features)
    if score >= 3: return "UP"
    if score <= -3: return "DOWN"
    if score >= 2: return "UP"
    if score <= -2: return "DOWN"
    return "NEUTRAL"

def markov_chain(kl, window=20):
    """35. Markov Zinciri Modeli — geçiş olasılıkları ile tahmin"""
    if len(kl) < window + 5: return "NEUTRAL"
    c = [k["c"] for k in kl]
    # Son window bar için UP/DOWN serisi
    moves = ["UP" if c[i] >= c[i-1] else "DOWN" for i in range(1, len(c))]
    recent = moves[-window:]
    # Geçiş matrisi: UU, UD, DU, DD
    uu = ud = du = dd = 0
    for i in range(len(recent) - 1):
        cur, nxt = recent[i], recent[i+1]
        if cur == "UP"   and nxt == "UP":   uu += 1
        elif cur == "UP"  and nxt == "DOWN": ud += 1
        elif cur == "DOWN" and nxt == "UP":  du += 1
        else:                               dd += 1
    last = recent[-1]
    if last == "UP":
        total = uu + ud
        if not total: return "NEUTRAL"
        p_up = uu / total
        return "UP" if p_up > 0.55 else "DOWN" if p_up < 0.45 else "NEUTRAL"
    else:
        total = du + dd
        if not total: return "NEUTRAL"
        p_up = du / total
        return "UP" if p_up > 0.55 else "DOWN" if p_up < 0.45 else "NEUTRAL"

def supertrend_v2(kl, p=7, mult=2.0):
    """36. SuperTrend v2 (7, 2.0) — daha hassas parametreler"""
    return supertrend(kl, p=p, mult=mult)

def ichimoku_v2(kl):
    """37. Ichimoku Cloud v2 — TK kesişimi + bulut rengi"""
    if len(kl) < 52: return "NEUTRAL"
    h = [k["h"] for k in kl]; l = [k["l"] for k in kl]; c = [k["c"] for k in kl]
    def don(p, off=0):
        idx = -(1 + off)
        s = slice(idx - p + 1, idx + 1) if idx + 1 else slice(idx - p + 1, None)
        return (max(h[s]) + min(l[s])) / 2
    tenkan = don(9); kijun = don(26)
    sa     = (don(9, 26) + don(26, 26)) / 2
    sb     = don(52, 26)
    # TK kesişimi (son 2 bar)
    tenkan_p = don(9, 1); kijun_p = don(26, 1)
    tk_cross_up   = tenkan_p <= kijun_p and tenkan > kijun
    tk_cross_down = tenkan_p >= kijun_p and tenkan < kijun
    # Bulut rengi ve pozisyon
    cloud_bull = sa > sb
    above_cloud = c[-1] > max(sa, sb)
    below_cloud = c[-1] < min(sa, sb)
    if tk_cross_up and above_cloud: return "UP"
    if tk_cross_down and below_cloud: return "DOWN"
    if above_cloud and cloud_bull: return "UP"
    if below_cloud and not cloud_bull: return "DOWN"
    return "UP" if tenkan > kijun else "DOWN"

def rsi_divergence_strict(kl, lookback=10):
    """38. RSI Diverjansı (14) — katı bullish/bearish sapma tespiti"""
    c  = [k["c"] for k in kl]
    rv = _rsi(c, 14)
    rv_clean = [x if x is not None else 50.0 for x in rv]
    if len(c) < lookback + 5: return "NEUTRAL"
    c_win  = c[-lookback:]
    r_win  = rv_clean[-lookback:]
    c_max  = max(c_win); c_min  = min(c_win)
    r_max  = max(r_win); r_min  = min(r_win)
    c_last = c[-1]; r_last = rv_clean[-1]
    # Bearish divergence: fiyat yeni zirve, RSI değil
    if c_last >= c_max * 0.998 and r_last < r_max * 0.97: return "DOWN"
    # Bullish divergence: fiyat yeni dip, RSI değil
    if c_last <= c_min * 1.002 and r_last > r_min * 1.03: return "UP"
    # Aşırı bölge
    if r_last < 30: return "UP"
    if r_last > 70: return "DOWN"
    return "NEUTRAL"

def h1_combination(kl):
    """39. H1 Profesyonel Kombinasyon — EMA55+ADX filtresi, MACD+RSI giriş, Hacim onayı"""
    if len(kl) < 60: return "NEUTRAL"
    c = [k["c"] for k in kl]
    # 1. Trend Filtresi: Fiyat EMA55 üzerinde + ADX > 25
    e55 = _ema(c, 55)
    if e55[-1] is None: return "NEUTRAL"
    adx_dir = adx_regime(kl, 14)
    price_above_ema55 = c[-1] > e55[-1]
    price_below_ema55 = c[-1] < e55[-1]
    adx_trending = adx_dir != "NEUTRAL"
    # 2. Giriş: MACD kesişimi + RSI 40-60 aralığında
    e12, e26 = _ema(c, 12), _ema(c, 26)
    ml = [e12[i]-e26[i] if e12[i] and e26[i] else None for i in range(len(c))]
    valid = [x for x in ml if x is not None]
    sl = _ema(valid, 9) if len(valid) >= 9 else [None]
    macd_cross_up   = (sl[-2] is not None and valid[-2] < sl[-2] and
                       sl[-1] is not None and valid[-1] > sl[-1])
    macd_cross_down = (sl[-2] is not None and valid[-2] > sl[-2] and
                       sl[-1] is not None and valid[-1] < sl[-1])
    rv = _rsi(c, 14)
    rsi_val = next((x for x in reversed(rv) if x is not None), 50)
    rsi_neutral = 40 <= rsi_val <= 60
    # 3. Hacim onayı: son hacim 20 mumun ortalamasının üzerinde
    avg_vol = sum(k["v"] for k in kl[-20:]) / 20
    vol_confirm = kl[-1]["v"] > avg_vol
    # Sinyal
    if price_above_ema55 and adx_trending and macd_cross_up and rsi_neutral and vol_confirm:
        return "UP"
    if price_below_ema55 and adx_trending and macd_cross_down and rsi_neutral and vol_confirm:
        return "DOWN"
    # Zayıf sinyal: sadece EMA55 + ADX + MACD
    if price_above_ema55 and adx_trending and valid[-1] > 0:
        return "UP"
    if price_below_ema55 and adx_trending and valid[-1] < 0:
        return "DOWN"
    return "NEUTRAL"


# ── Ana fonksiyon ─────────────────────────────────────────────────────

ALGO_META = [
    (1,  "EMA Crossover (9/21/50/200)"),
    (2,  "MACD Histogram + Divergence"),
    (3,  "Supertrend"),
    (4,  "Ichimoku Cloud"),
    (5,  "RSI + Divergence"),
    (6,  "Stochastic RSI"),
    (7,  "Bollinger Bands + Squeeze"),
    (8,  "VWAP"),
    (9,  "OBV"),
    (10, "Volume Profile (POC)"),
    (11, "Mean Reversion (Z-Score)"),
    (12, "Pairs Trading"),
    (13, "Grid Trading Bot"),
    (14, "LSTM"),
    (15, "Multi-Timeframe Confluence"),
    (16, "ATR Momentum Breakout"),
    (17, "Heikin Ashi Trend Filter"),
    (18, "TEMA Crossover (9/21)"),
    (19, "ADX Market Regime"),
    (20, "Open Interest Divergence"),
    (21, "Fear & Greed Momentum"),
    (25, "Parabolic SAR + ADX"),
    (26, "MACD Histogram Diverjansı"),
    (27, "Stochastic RSI (14) K/D"),
    (28, "Triple EMA (8-21-55)"),
    (29, "Hull Moving Average (HMA)"),
    (30, "Keltner Kanalı (20,2)"),
    (31, "Donchian Kanalı (20)"),
    (32, "VWAP + Hacim Profili"),
    (33, "Money Flow Index (MFI)"),
    (34, "Random Forest Classifier"),
    (35, "Markov Zinciri Modeli"),
    (36, "SuperTrend v2 (7,2.0)"),
    (37, "Ichimoku Cloud v2 (TK+Bulut)"),
    (38, "RSI Diverjansı (14) Katı"),
    (39, "H1 Profesyonel Kombinasyon"),
]

SKIP = {13, 14}   # Yön tahmini yok


def _build_all_signals(
    interval: str = "1h",
    htf_interval: str = "4h",
    limit: int = 200,
    htf_limit: int = 100,
) -> tuple[dict, dict, dict]:
    """36 algo sinyalleri + sembol konsensüsü (interval: 5m / 15m / 1h)."""
    kl_primary, kl_htf = {}, {}
    for sym, pair in SYMBOLS.items():
        try:
            kl_primary[sym] = fetch_klines(pair, interval, limit)
            kl_htf[sym] = fetch_klines(pair, htf_interval, htf_limit)
        except Exception as e:
            print(f"Fetch error {sym}: {e}")
            kl_primary[sym] = []
            kl_htf[sym] = []

    pairs_sig = pairs_trading(kl_primary)
    fg_signal = fetch_fear_greed()

    oi_cache = {}
    for sym, pair in SYMBOLS.items():
        try:
            oi_cache[sym] = fetch_oi_hist(pair, 10)
        except Exception:
            oi_cache[sym] = []

    def _oi_for(sym):
        kl = kl_primary.get(sym, [])
        oi = oi_cache.get(sym, [])
        if len(oi) < 5 or len(kl) < 5:
            return "NEUTRAL"
        try:
            c = [k["c"] for k in kl[-10:]]
            pc = (c[-1] - c[-5]) / c[-5] if c[-5] else 0
            oc = (oi[-1] - oi[-5]) / oi[-5] if oi[-5] else 0
            if pc > 0.005 and oc > 0.005:
                return "UP"
            if pc < -0.005 and oc > 0.005:
                return "DOWN"
            if pc > 0.005 and oc < -0.005:
                return "DOWN"
            if pc < -0.005 and oc < -0.005:
                return "UP"
        except Exception:
            pass
        return "NEUTRAL"

    SIMPLE_FN = {
        1: ema_crossover, 2: macd_div, 3: supertrend, 4: ichimoku, 5: rsi_div,
        6: stoch_rsi, 7: bb_squeeze, 8: vwap, 9: obv, 10: volume_profile,
        11: mean_reversion, 16: atr_breakout, 17: heikin_ashi, 18: tema_crossover,
        19: adx_regime, 25: parabolic_sar_adx, 26: macd_histogram_div,
        27: stoch_rsi_kd, 28: triple_ema, 29: hull_ma, 30: keltner_channel,
        31: donchian_channel, 32: vwap_volume_profile, 33: money_flow_index,
        34: random_forest_clf, 35: markov_chain, 36: supertrend_v2,
        37: ichimoku_v2, 38: rsi_divergence_strict, 39: h1_combination,
    }

    signals = {}
    for num, name in ALGO_META:
        entry = {sym: "NEUTRAL" for sym in SYMBOLS}
        entry["name"] = name
        if num in SKIP:
            pass
        elif num == 12:
            entry.update(pairs_sig)
        elif num == 15:
            for sym in SYMBOLS:
                if kl_primary.get(sym) and kl_htf.get(sym):
                    entry[sym] = multi_tf(kl_primary[sym], kl_htf[sym])
        elif num == 20:
            for sym in SYMBOLS:
                entry[sym] = _oi_for(sym)
        elif num == 21:
            for sym in SYMBOLS:
                entry[sym] = fg_signal
        elif num in SIMPLE_FN:
            fn = SIMPLE_FN[num]
            for sym in SYMBOLS:
                kl = kl_primary.get(sym, [])
                if kl:
                    try:
                        entry[sym] = fn(kl)
                    except Exception as e:
                        print(f"Algo {num} {sym} error: {e}")
        signals[str(num)] = entry

    active = [v for k, v in signals.items() if int(k) not in SKIP]
    consensus = {}
    for sym in SYMBOLS:
        up = sum(1 for v in active if v[sym] == "UP")
        down = sum(1 for v in active if v[sym] == "DOWN")
        consensus[sym] = {
            "UP": up, "DOWN": down, "NEUTRAL": len(active) - up - down, "total": len(active),
        }
    return signals, consensus, kl_primary


def collect_btc_algo_votes() -> list[dict]:
    """36 algo → BTC yön oyları."""
    signals, _, _ = _build_all_signals()
    return [
        {
            "id": num,
            "name": name,
            "signal": signals.get(str(num), {}).get("BTC", "NEUTRAL"),
            "group": "algo",
        }
        for num, name in ALGO_META
    ]


def run():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)

    signals, consensus, kl_1h = _build_all_signals()
    # klines[-2] = yeni biten saatin kapanışı (bu saatin price to beat)
    # klines[-3] = bir önceki saatin kapanışı (geçen sinyalin entry_price)
    try:
        prev_data = json.load(open(PREV_FILE)) if os.path.exists(PREV_FILE) else None
        if prev_data and prev_data.get("signals"):
            acc = {}
            if os.path.exists(ACCURACY_FILE):
                with open(ACCURACY_FILE) as f:
                    acc = json.load(f)

            updated_any = False
            for sym, pair in SYMBOLS.items():
                kl = kl_1h.get(sym, [])
                if len(kl) < 3:
                    continue
                prev_close = kl[-3]["c"]  # geçen saatten bir önceki kapanış
                curr_close = kl[-2]["c"]  # geçen saatin kapanışı (gerçek sonuç)
                if curr_close == prev_close:
                    continue
                actual = "UP" if curr_close > prev_close else "DOWN"

                for algo_num, sigs in prev_data["signals"].items():
                    algo_sig = sigs.get(sym)
                    if algo_sig not in ("UP", "DOWN"):
                        continue
                    correct = 1 if algo_sig == actual else 0
                    if algo_num not in acc:
                        acc[algo_num] = {"name": sigs.get("name", ""), "total": 0, "correct": 0, "by_sym": {}}
                    if not acc[algo_num].get("name") and sigs.get("name"):
                        acc[algo_num]["name"] = sigs["name"]
                    acc[algo_num]["total"]   += 1
                    acc[algo_num]["correct"] += correct
                    by_sym = acc[algo_num].setdefault("by_sym", {})
                    if sym not in by_sym:
                        by_sym[sym] = {"total": 0, "correct": 0}
                    by_sym[sym]["total"]   += 1
                    by_sym[sym]["correct"] += correct
                    updated_any = True

            if updated_any:
                with open(ACCURACY_FILE, "w") as f:
                    json.dump(acc, f, indent=2, ensure_ascii=False)
                print(f"[{now.strftime('%H:%M')}] algo_accuracy.json güncellendi")
        if prev_data and prev_data.get("consensus"):
            from chart_signal_accuracy import update_consensus_accuracy
            update_consensus_accuracy(
                prev_data["consensus"],
                {sym: kl_1h.get(sym, []) for sym in SYMBOLS},
                ACCURACY_FILE,
                name="Analiz 1 Konsensüs",
            )
    except Exception as e:
        print(f"[{now.strftime('%H:%M')}] accuracy güncelleme hatası: {e}")

    try:
        from chart_signal_accuracy import ensure_backfill, update_hourly
        if not os.path.isfile(os.path.join(_DIR, "chart_signal_accuracy.json")):
            ensure_backfill(150)
        update_hourly()
    except Exception as e:
        print(f"[{now.strftime('%H:%M')}] chart_signal_accuracy: {e}")

    # Mevcut sinyalleri önce prev'e yaz, sonra out'a
    try:
        with open(PREV_FILE, "w") as f:
            json.dump({"signals": signals, "consensus": consensus}, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # Mevcut periyot: bu saatin :05'i → bir sonraki saatin :00'ı
    period_start = now.replace(minute=5, second=0, microsecond=0)
    period_end   = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    out = {
        "updated":      now.strftime("%H:%M"),
        "period_start": period_start.strftime("%H:%M"),
        "period_end":   period_end.strftime("%H:%M"),
        "signals":     signals,
        "consensus":   consensus,
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"[{now.strftime('%H:%M')}] Sinyaller kaydedildi → {OUT_FILE}")
    for sym in SYMBOLS:
        c = consensus[sym]
        print(f"  {sym}: ▲{c['UP']} ▼{c['DOWN']} ={c['NEUTRAL']}")

if __name__ == "__main__":
    run()

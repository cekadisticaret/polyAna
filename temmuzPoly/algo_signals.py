#!/usr/bin/env python3
"""
algo_signals.py — 24 algoritma için BTC/ETH/SOL saatlik sinyal üretici
(21 teknik + Analiz-1/9/10 sistemleri)
Her :05'te cron ile çalışır, /tmp/algo_signals.json'a kaydeder
"""
import json, requests, datetime, math, os

SYMBOLS       = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
FUTURES       = "https://fapi.binance.com"
OUT_FILE      = "/tmp/algo_signals.json"
PREV_FILE     = "/tmp/algo_signals_prev.json"
_DIR          = os.path.dirname(os.path.abspath(__file__))
ACCURACY_FILE = os.path.join(_DIR, "algo_accuracy.json")

# ── Binance veri çekimi ───────────────────────────────────────────────

def fetch_klines(pair, interval="1h", limit=200):
    r = requests.get(f"{FUTURES}/fapi/v1/klines",
                     params={"symbol": pair, "interval": interval, "limit": limit},
                     timeout=10)
    return [{"o": float(x[1]), "h": float(x[2]), "l": float(x[3]),
             "c": float(x[4]), "v": float(x[5])} for x in r.json()]

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
    if n < 20: return {"BTC": "NEUTRAL", "ETH": "NEUTRAL", "SOL": "NEUTRAL"}
    ratios = [eth[i]["c"] / btc[i]["c"] for i in range(n) if btc[i]["c"]]
    std, mean = _std(ratios[-20:])
    if not std: return {"BTC": "NEUTRAL", "ETH": "NEUTRAL", "SOL": "NEUTRAL"}
    z = (ratios[-1] - mean) / std
    eth_sig = "UP" if z < -1 else "DOWN" if z > 1 else "NEUTRAL"
    btc_sig = "DOWN" if z < -1 else "UP" if z > 1 else "NEUTRAL"
    return {"BTC": btc_sig, "ETH": eth_sig, "SOL": "NEUTRAL"}

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

# ── Analiz-1/9/10 sistemleri (22-24) ─────────────────────────────────

def fetch_funding_rate(pair):
    """Binance Futures anlık funding rate"""
    try:
        r = requests.get(f"{FUTURES}/fapi/v1/premiumIndex",
                         params={"symbol": pair}, timeout=6)
        return float(r.json().get("lastFundingRate", 0))
    except Exception:
        return 0.0

def analiz1_system(kl):
    """Analiz-1 sistemi: RSI + MACD + EMA çoğunluk oyu (3 indikatör)"""
    c = [k["c"] for k in kl]
    # RSI oyu
    rv = _rsi(c, 14)
    rsi_val = next((x for x in reversed(rv) if x is not None), 50)
    rsi_v = +1 if rsi_val < 50 else -1
    # MACD oyu
    e12, e26 = _ema(c, 12), _ema(c, 26)
    ml = [e12[i] - e26[i] if e12[i] and e26[i] else None for i in range(len(c))]
    valid = [x for x in ml if x is not None]
    sl = _ema(valid, 9) if len(valid) >= 9 else [None]
    macd_v = +1 if (sl[-1] and valid[-1] > sl[-1]) else -1
    # EMA oyu (9 vs 21)
    e9, e21 = _ema(c, 9), _ema(c, 21)
    ema_v = +1 if (e9[-1] and e21[-1] and e9[-1] > e21[-1]) else -1
    # Çoğunluk
    score = rsi_v + macd_v + ema_v
    if score >= 2: return "UP"
    if score <= -2: return "DOWN"
    return "NEUTRAL"

def analiz9_system(kl, funding_rate=0.0):
    """Analiz-9 sistemi: Trend(EMA20/50) + MR(RSI+BB) + Orderflow(CVD) + Funding (4 oy)"""
    c = [k["c"] for k in kl]
    # --- Trend oyu: EMA20 vs EMA50 ---
    e20, e50 = _ema(c, 20), _ema(c, 50)
    trend_v = +1 if (e20[-1] and e50[-1] and e20[-1] > e50[-1]) else -1
    # --- MR oyu: RSI + BB ---
    rv = _rsi(c, 14)
    rsi_val = next((x for x in reversed(rv) if x is not None), 50)
    rsi_v = +1 if rsi_val <= 35 else -1 if rsi_val >= 65 else 0
    if len(c) >= 20:
        std20, m20 = _std(c[-20:])
        upper, lower = m20 + 2*std20, m20 - 2*std20
        bb_v = +1 if c[-1] < lower else -1 if c[-1] > upper else 0
    else:
        bb_v = 0
    mr_v = max(-1, min(1, rsi_v + bb_v))
    # --- Orderflow oyu: CVD yaklaşımı ---
    window = kl[-20:]
    cvd = sum((k["c"] - k["o"]) / k["o"] * k["v"] for k in window if k["o"] > 0)
    norm = max(abs(cvd), 1e-9)
    cvd_n = cvd / norm
    of_v = +1 if cvd_n > 0.1 else -1 if cvd_n < -0.1 else 0
    # --- Funding oyu ---
    fund_v = -1 if funding_rate > 0.0001 else +1 if funding_rate < -0.0001 else 0
    score = trend_v + mr_v + of_v + fund_v
    if score >= 2: return "UP"
    if score <= -2: return "DOWN"
    return "NEUTRAL"

def analiz10_system(kl, funding_rate=0.0):
    """Analiz-10 sistemi: A1 + A9 ikisi de aynı yönü söylüyorsa sinyal"""
    s1 = analiz1_system(kl)
    s9 = analiz9_system(kl, funding_rate)
    if s1 == s9 and s1 != "NEUTRAL": return s1
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
    (22, "Analiz-1 Sistemi (RSI+MACD+EMA)"),
    (23, "Analiz-9 Sistemi (Trend+MR+OF+Fund)"),
    (24, "Analiz-10 Sistemi (A1+A9 Konsensüs)"),
]

SKIP = {13, 14}   # Yön tahmini yok

def run():
    now    = datetime.datetime.utcnow() + datetime.timedelta(hours=3)  # Istanbul Time

    kl_1h, kl_4h = {}, {}
    for sym, pair in SYMBOLS.items():
        try:
            kl_1h[sym] = fetch_klines(pair, "1h", 200)
            kl_4h[sym] = fetch_klines(pair, "4h", 100)
        except Exception as e:
            print(f"Fetch error {sym}: {e}")
            kl_1h[sym] = []; kl_4h[sym] = []

    pairs_sig  = pairs_trading(kl_1h)
    fg_signal  = fetch_fear_greed()  # Tüm semboller için aynı

    # OI geçmişini bir kez çek
    oi_cache = {}
    for sym, pair in SYMBOLS.items():
        try:
            oi_cache[sym] = fetch_oi_hist(pair, 10)
        except Exception:
            oi_cache[sym] = []

    # Funding rate'leri bir kez çek
    funding_cache = {}
    for sym, pair in SYMBOLS.items():
        try:
            funding_cache[sym] = fetch_funding_rate(pair)
        except Exception:
            funding_cache[sym] = 0.0

    # Sembol başına OI divergence hesapla
    def _oi_for(sym):
        kl  = kl_1h.get(sym, [])
        oi  = oi_cache.get(sym, [])
        if len(oi) < 5 or len(kl) < 5: return "NEUTRAL"
        try:
            c  = [k["c"] for k in kl[-10:]]
            pc = (c[-1] - c[-5]) / c[-5] if c[-5] else 0
            oc = (oi[-1] - oi[-5]) / oi[-5] if oi[-5] else 0
            if pc >  0.005 and oc >  0.005: return "UP"
            if pc < -0.005 and oc >  0.005: return "DOWN"
            if pc >  0.005 and oc < -0.005: return "DOWN"
            if pc < -0.005 and oc < -0.005: return "UP"
        except Exception:
            pass
        return "NEUTRAL"

    SIMPLE_FN = {
        1: ema_crossover, 2: macd_div, 3: supertrend, 4: ichimoku,
        5: rsi_div, 6: stoch_rsi, 7: bb_squeeze, 8: vwap,
        9: obv, 10: volume_profile, 11: mean_reversion,
        16: atr_breakout, 17: heikin_ashi, 18: tema_crossover, 19: adx_regime,
    }

    signals = {}
    for num, name in ALGO_META:
        entry = {"name": name, "BTC": "NEUTRAL", "ETH": "NEUTRAL", "SOL": "NEUTRAL"}
        if num in SKIP:
            pass
        elif num == 12:
            entry.update(pairs_sig)
        elif num == 15:
            for sym in SYMBOLS:
                if kl_1h.get(sym) and kl_4h.get(sym):
                    entry[sym] = multi_tf(kl_1h[sym], kl_4h[sym])
        elif num == 20:
            for sym in SYMBOLS:
                entry[sym] = _oi_for(sym)
        elif num == 21:
            for sym in SYMBOLS:
                entry[sym] = fg_signal
        elif num == 22:
            for sym in SYMBOLS:
                kl = kl_1h.get(sym, [])
                if kl:
                    try: entry[sym] = analiz1_system(kl)
                    except Exception as e: print(f"Algo 22 {sym} error: {e}")
        elif num == 23:
            for sym in SYMBOLS:
                kl = kl_1h.get(sym, [])
                if kl:
                    try: entry[sym] = analiz9_system(kl, funding_cache.get(sym, 0.0))
                    except Exception as e: print(f"Algo 23 {sym} error: {e}")
        elif num == 24:
            for sym in SYMBOLS:
                kl = kl_1h.get(sym, [])
                if kl:
                    try: entry[sym] = analiz10_system(kl, funding_cache.get(sym, 0.0))
                    except Exception as e: print(f"Algo 24 {sym} error: {e}")
        elif num in SIMPLE_FN:
            fn = SIMPLE_FN[num]
            for sym in SYMBOLS:
                kl = kl_1h.get(sym, [])
                if kl:
                    try: entry[sym] = fn(kl)
                    except Exception as e:
                        print(f"Algo {num} {sym} error: {e}")
        signals[str(num)] = entry

    # Consensus (13 ve 14 hariç)
    active = [v for k, v in signals.items() if int(k) not in SKIP]
    consensus = {}
    for sym in SYMBOLS:
        up   = sum(1 for v in active if v[sym] == "UP")
        down = sum(1 for v in active if v[sym] == "DOWN")
        consensus[sym] = {"UP": up, "DOWN": down, "NEUTRAL": len(active)-up-down, "total": len(active)}

    # ── Önceki saatin doğruluk kontrolü ──────────────────────────────────
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
    except Exception as e:
        print(f"[{now.strftime('%H:%M')}] accuracy güncelleme hatası: {e}")

    # Mevcut sinyalleri önce prev'e yaz, sonra out'a
    try:
        with open(PREV_FILE, "w") as f:
            json.dump({"signals": signals}, f, indent=2, ensure_ascii=False)
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

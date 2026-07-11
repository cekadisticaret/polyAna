#!/usr/bin/env python3
"""
algo_signals.py — 15 algoritma için BTC/ETH/SOL saatlik sinyal üretici
Her :05'te cron ile çalışır, /tmp/algo_signals.json'a kaydeder
"""
import json, requests, datetime, math

SYMBOLS   = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
FUTURES   = "https://fapi.binance.com"
OUT_FILE  = "/tmp/algo_signals.json"

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

    pairs_sig = pairs_trading(kl_1h)

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
        else:
            fn = {1: ema_crossover, 2: macd_div, 3: supertrend, 4: ichimoku,
                  5: rsi_div, 6: stoch_rsi, 7: bb_squeeze, 8: vwap,
                  9: obv, 10: volume_profile, 11: mean_reversion}[num]
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

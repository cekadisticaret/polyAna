"""
ETH/SOL teknik analiz indikatörleri.
Orijinal algoritma korunmuştur — Binance/OKX üzerinden OHLCV verisi çeker.
"""
import json
import logging
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

STRUCT_LEN = 5
ADX_MIN = 25
USE_HTF_FILTER = False


def get_klines(symbol: str, interval: str = "15m", limit: int = 250):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return [float(d[4]) for d in data], [float(d[5]) for d in data], [float(d[2]) for d in data], [float(d[3]) for d in data]
    except Exception:
        pass

    base = symbol.replace("USDT", "")
    okx_bar = {"15m": "15m", "1h": "1H", "5m": "5m"}.get(interval, interval)
    okx_url = f"https://www.okx.com/api/v5/market/candles?instId={base}-USDT-SWAP&bar={okx_bar}&limit={limit}"
    try:
        req = urllib.request.Request(okx_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("code") != "0" or not data.get("data"):
            raise Exception("OKX no data")
        candles = list(reversed(data["data"]))
        return [float(d[4]) for d in candles], [float(d[5]) for d in candles], [float(d[2]) for d in candles], [float(d[3]) for d in candles]
    except Exception:
        pass
    return None, None, None, None


def ema(series, n):
    if len(series) < n:
        return []
    k = 2 / (n + 1)
    result = [sum(series[:n]) / n]
    for price in series[n:]:
        result.append(price * k + result[-1] * (1 - k))
    return result


def calc_rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[-n:]) / n
    avg_loss = sum(losses[-n:]) / n
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def calc_macd(closes, fast=8, slow=21, sig=5):
    if len(closes) < slow + sig + 5:
        return None, None
    e_fast = ema(closes, fast)
    e_slow = ema(closes, slow)
    min_len = min(len(e_fast), len(e_slow))
    macd_line = [e_fast[-(min_len-i)] - e_slow[-(min_len-i)] for i in range(min_len)]
    signal_line = ema(macd_line, sig)
    if not signal_line:
        return None, None
    return macd_line[-1], signal_line[-1]


def calc_adx(highs, lows, closes, n=14):
    if len(closes) < n * 2:
        return None
    trs, dmp, dmm = [], [], []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        up = highs[i] - highs[i-1]
        dn = lows[i-1] - lows[i]
        trs.append(tr)
        dmp.append(up if up > dn and up > 0 else 0)
        dmm.append(dn if dn > up and dn > 0 else 0)

    def smooth(arr, n):
        s = sum(arr[:n])
        result = [s]
        for v in arr[n:]:
            result.append(result[-1] - result[-1]/n + v)
        return result

    atr_s = smooth(trs, n)
    dmp_s = smooth(dmp, n)
    dmm_s = smooth(dmm, n)
    dx_list = []
    for i in range(len(atr_s)):
        di_p = 100 * dmp_s[i] / atr_s[i] if atr_s[i] else 0
        di_m = 100 * dmm_s[i] / atr_s[i] if atr_s[i] else 0
        denom = di_p + di_m
        dx_list.append(100 * abs(di_p - di_m) / denom if denom else 0)
    adx_list = ema(dx_list, n)
    return round(adx_list[-1], 2) if adx_list else None


def calc_atr(highs, lows, closes, n=14):
    if len(closes) < n + 1:
        return None
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(closes))]
    atr_vals = ema(trs, n)
    return atr_vals[-1] if atr_vals else None


def calc_atr_pct_hot(highs, lows, closes, ref_len=100, hot_mult=1.8):
    atr = calc_atr(highs, lows, closes, 14)
    if not atr or not closes[-1]:
        return False
    atr_pct = (atr / closes[-1]) * 100
    if len(closes) < ref_len + 15:
        return False
    ref_atrs = []
    for i in range(ref_len):
        idx = -(ref_len - i)
        a = calc_atr(highs[:idx], lows[:idx], closes[:idx], 14)
        if a and closes[idx]:
            ref_atrs.append((a / closes[idx]) * 100)
    if not ref_atrs:
        return False
    return atr_pct > (sum(ref_atrs) / len(ref_atrs)) * hot_mult


def get_pivots(highs, lows, left, right):
    def is_pivot_high(arr, i):
        if i < left or i + right >= len(arr):
            return False
        c = arr[i]
        for j in range(1, left + 1):
            if arr[i - j] >= c:
                return False
        for j in range(1, right + 1):
            if arr[i + j] >= c:
                return False
        return True

    def is_pivot_low(arr, i):
        if i < left or i + right >= len(arr):
            return False
        c = arr[i]
        for j in range(1, left + 1):
            if arr[i - j] <= c:
                return False
        for j in range(1, right + 1):
            if arr[i + j] <= c:
                return False
        return True

    ph_list, pl_list = [], []
    for i in range(left, len(highs) - right):
        if is_pivot_high(highs, i):
            ph_list.append((i, highs[i]))
        if is_pivot_low(lows, i):
            pl_list.append((i, lows[i]))
    return (ph_list[-1][1] if ph_list else None), (pl_list[-1][1] if pl_list else None)


def get_market_bias(symbol: str = "ETHUSDT"):
    try:
        closes, _, _, _ = get_klines(symbol, "1h", 150)
        if not closes or len(closes) < 110:
            return "NEUTRAL", f"{symbol} verisi alınamadı"
        k = 2 / (21 + 1)
        e21 = sum(closes[:21]) / 21
        for c in closes[21:]:
            e21 = c * k + e21 * (1 - k)
        k2 = 2 / (100 + 1)
        e100 = sum(closes[:100]) / 100
        for c in closes[100:]:
            e100 = c * k2 + e100 * (1 - k2)
        price = closes[-2]
        if price > e21 and e21 > e100:
            return "BULL", f"{symbol} {round(price,0)}$ > EMA21({round(e21,0)}) > EMA100({round(e100,0)})"
        elif price < e21 and e21 < e100:
            return "BEAR", f"{symbol} {round(price,0)}$ < EMA21({round(e21,0)}) < EMA100({round(e100,0)})"
        else:
            return "NEUTRAL", f"{symbol} EMA21/100 karışık ({round(price,0)}$ / EMA21:{round(e21,0)} / EMA100:{round(e100,0)})"
    except Exception as e:
        logger.exception("get_market_bias: %s", e)
        return "NEUTRAL", f"{symbol} analiz hatası"


def get_htf_bias(symbol):
    try:
        closes_1h, _, _, _ = get_klines(symbol, "1h", 60)
        if not closes_1h or len(closes_1h) < 25:
            return "NEUTRAL"
        ema21_1h = ema(closes_1h, 21)
        if not ema21_1h:
            return "NEUTRAL"
        price_1h = closes_1h[-2]
        e21_1h = ema21_1h[-1]
        if price_1h > e21_1h:
            return "BULL"
        elif price_1h < e21_1h:
            return "BEAR"
    except Exception:
        pass
    return "NEUTRAL"


def analyze(symbol, interval="15m"):
    closes, volumes, highs, lows = get_klines(symbol, interval, 250)
    if not closes or len(closes) < 120:
        return None
    rsi_val = calc_rsi(closes[-20:], 14)
    rsi_prev = calc_rsi(closes[-21:-1], 14)
    macd_val, sig_val = calc_macd(closes)
    macd_prev, sig_prev = calc_macd(closes[:-1])
    adx_val = calc_adx(highs, lows, closes)
    atr_val = calc_atr(highs, lows, closes)
    if any(v is None for v in [rsi_val, rsi_prev, macd_val, sig_val, adx_val, atr_val]):
        return None
    ema21_s, ema100_s = ema(closes, 21), ema(closes, 100)
    if not ema21_s or not ema100_s:
        return None
    ema21, ema100, price = ema21_s[-1], ema100_s[-1], closes[-2]
    vol_avg = sum(volumes[-20:]) / 20
    vol_spike = volumes[-2] > vol_avg * 1.5
    vol_confirm = volumes[-2] > max(volumes[-12:-2]) * 1.2
    dist_pct = abs((price - ema100) / ema100) * 100
    is_not_far = dist_pct < 5.0
    is_hot_vol = calc_atr_pct_hot(highs, lows, closes)
    rsi_rising = rsi_val > rsi_prev
    rsi_falling = rsi_val < rsi_prev
    htf_bias = get_htf_bias(symbol) if USE_HTF_FILTER else "OFF"
    htf_bull = htf_bias in ("BULL", "NEUTRAL") if USE_HTF_FILTER else True
    htf_bear = htf_bias in ("BEAR", "NEUTRAL") if USE_HTF_FILTER else True
    vol_ok = vol_spike or vol_confirm
    strong_buy = not is_hot_vol and htf_bull and price > ema100 and price > ema21 and rsi_val >= 50 and rsi_val <= 65 and rsi_rising and macd_val > sig_val and adx_val > ADX_MIN and vol_ok and is_not_far
    strong_sell = not is_hot_vol and htf_bear and price < ema100 and price < ema21 and rsi_val >= 35 and rsi_val <= 45 and rsi_falling and macd_val < sig_val and adx_val > ADX_MIN and vol_ok and is_not_far
    exit_long = rsi_val > 75 or price < ema100 or (macd_val < sig_val and rsi_val < 52)
    exit_short = rsi_val < 25 or price > ema100 or (macd_val > sig_val and rsi_val > 48)
    last_sh, last_sl = get_pivots(highs, lows, STRUCT_LEN, STRUCT_LEN)
    return {
        "symbol": symbol, "price": round(price, 6), "bar_high": round(highs[-2], 6), "bar_low": round(lows[-2], 6),
        "atr": round(atr_val, 6), "rsi": rsi_val, "adx": adx_val, "ema21": round(ema21, 6), "ema100": round(ema100, 6),
        "macd_bull": macd_val > sig_val, "vol_spike": vol_spike, "strong_buy": strong_buy, "strong_sell": strong_sell,
        "exit_long": exit_long, "exit_short": exit_short, "is_hot_vol": is_hot_vol, "htf_bias": htf_bias,
        "last_sh": round(last_sh, 6) if last_sh else None, "last_sl": round(last_sl, 6) if last_sl else None,
    }

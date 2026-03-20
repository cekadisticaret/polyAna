#!/usr/bin/env python3
"""
Binance USDT-M Futures Gerçek Trader
Tüm sinyal, indikatör ve analiz mantığı bu dosyada — paper_trader bağımlılığı yok.
MAX_OPEN 8 — yön kotası yok.
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from binance_config import TG_BOT_TOKEN, TG_CHAT_ID
from binance_api import (
    get_balance, get_positions, set_leverage,
    place_market_order, place_stop_market, place_take_profit_market,
    cancel_all_orders, round_quantity, round_price, get_user_trades,
)

# ========== AYARLAR ==========

INITIAL_CAPITAL = 200.0
STATE_FILE      = os.path.join(os.path.dirname(__file__), "binance_state.json")

LEVERAGE        = 10
STOP_ATR_MULT   = 2.0
TAKE_ATR_MULT   = 4.5
MAX_SL_PCT      = 0.8
MAX_OPEN        = 8
COOLDOWN_BARS   = 4
MIN_HOLD_BARS   = 2
MAX_LOSS_BARS   = 3
POS_SIZE_PCT    = 0.10
COMMISSION_PCT  = 0.001
ADX_MIN         = 25
STRUCT_LEN      = 5
MIN_RR_RATIO    = 2.0

# Confluence (paper_trader ile aynı)
MIN_CONFLUENCE  = 3
CROSS_LOOKBACK  = 3
EMA_FAST_LEN    = 9
EMA_TREND_LEN   = 50

# Yön kotası (paper_trader ile aynı)
BULL_MAX_LONG   = 5
BULL_MAX_SHORT  = 3
BEAR_MAX_LONG   = 3
BEAR_MAX_SHORT  = 5
NEUT_MAX_LONG   = 4
NEUT_MAX_SHORT  = 4

TRAIL_ATR_MULT       = 1.5   # Trailing stop mesafesi: en iyi fiyattan ATR × 1.5 geride
TRAIL_MIN_PROFIT_ATR = 0.8   # Trailing başlama eşiği: kâr ATR × 0.8'i geçince aktifleşir
TRAIL_TIGHTEN        = 0.3   # TP her geçilince trail_mult bu kadar sıkışır
TRAIL_MIN_MULT       = 0.7   # Minimum trail mesafesi (ATR × 0.7)
HOT_VOL_MULT         = 1.5   # Volatilite filtresi: ATR% > 100bar_ort × bu çarpan ise işlem açma

BULL_LONG_LEV   = 10
BULL_SHORT_LEV  = 10
BEAR_LONG_LEV   = 10
BEAR_SHORT_LEV  = 10
NEUT_LONG_LEV   = 10
NEUT_SHORT_LEV  = 10

# Risk limitleri
DAILY_LOSS_LIMIT_USDT = 30
DRAWDOWN_PCT          = 20

# ========== TELEGRAM ==========

def tg_send(text):
    try:
        url  = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception:
        pass

def now_str():
    now   = datetime.now(timezone.utc)
    ist_h = (now.hour + 3) % 24
    return f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')} İST"

# ========== VERİ ==========

def get_klines(symbol, interval="15m", limit=250):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        closes  = [float(d[4]) for d in data]
        volumes = [float(d[5]) for d in data]
        highs   = [float(d[2]) for d in data]
        lows    = [float(d[3]) for d in data]
        return closes, volumes, highs, lows
    except Exception:
        pass

    base    = symbol.replace("USDT", "")
    okx_bar = {"15m": "15m", "1h": "1H", "5m": "5m"}.get(interval, interval)
    okx_url = f"https://www.okx.com/api/v5/market/candles?instId={base}-USDT-SWAP&bar={okx_bar}&limit={limit}"
    try:
        req = urllib.request.Request(okx_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("code") != "0" or not data.get("data"):
            raise Exception("OKX no data")
        candles = list(reversed(data["data"]))
        return (
            [float(d[4]) for d in candles],
            [float(d[5]) for d in candles],
            [float(d[2]) for d in candles],
            [float(d[3]) for d in candles],
        )
    except Exception:
        pass
    return None, None, None, None

# ========== PİYASA YÖN ANALİZİ ==========

def get_market_bias():
    """
    BTC 1h verisiyle genel piyasa yönünü belirler.
    EMA21 > EMA100 ve fiyat > EMA21 → BULL
    EMA21 < EMA100 ve fiyat < EMA21 → BEAR
    Aksi halde → NEUTRAL
    """
    try:
        closes, _, _, _ = get_klines("BTCUSDT", "1h", 150)
        if not closes or len(closes) < 110:
            return "NEUTRAL", "BTC verisi alınamadı"

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
            return "BULL", f"BTC {round(price,0)}$ > EMA21({round(e21,0)}) > EMA100({round(e100,0)})"
        elif price < e21 and e21 < e100:
            return "BEAR", f"BTC {round(price,0)}$ < EMA21({round(e21,0)}) < EMA100({round(e100,0)})"
        else:
            return "NEUTRAL", f"BTC EMA21/100 karışık ({round(price,0)}$ / EMA21:{round(e21,0)} / EMA100:{round(e100,0)})"
    except Exception:
        return "NEUTRAL", "Piyasa yönü hesaplanamadı"

# ========== İNDİKATÖRLER ==========

def ema(series, n):
    if len(series) < n:
        return []
    k      = 2 / (n + 1)
    result = [sum(series[:n]) / n]
    for price in series[n:]:
        result.append(price * k + result[-1] * (1 - k))
    return result

def calc_rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    deltas   = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains    = [max(d, 0)      for d in deltas]
    losses   = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[-n:]) / n
    avg_loss = sum(losses[-n:]) / n
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

def calc_macd(closes, fast=8, slow=21, sig=5):
    if len(closes) < slow + sig + 5:
        return None, None
    e_fast  = ema(closes, fast)
    e_slow  = ema(closes, slow)
    min_len = min(len(e_fast), len(e_slow))
    macd_line   = [e_fast[-(min_len-i)] - e_slow[-(min_len-i)] for i in range(min_len)]
    signal_line = ema(macd_line, sig)
    if not signal_line:
        return None, None
    return macd_line[-1], signal_line[-1]

def calc_adx(highs, lows, closes, n=14):
    if len(closes) < n * 2:
        return None
    trs, dmp, dmm = [], [], []
    for i in range(1, len(closes)):
        tr  = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        up  = highs[i] - highs[i-1]
        dn  = lows[i-1] - lows[i]
        trs.append(tr)
        dmp.append(up if up > dn and up > 0 else 0)
        dmm.append(dn if dn > up and dn > 0 else 0)
    def smooth(arr, n):
        s      = sum(arr[:n])
        result = [s]
        for v in arr[n:]:
            result.append(result[-1] - result[-1]/n + v)
        return result
    atr_s   = smooth(trs, n)
    dmp_s   = smooth(dmp, n)
    dmm_s   = smooth(dmm, n)
    dx_list = []
    for i in range(len(atr_s)):
        di_p  = 100 * dmp_s[i] / atr_s[i] if atr_s[i] else 0
        di_m  = 100 * dmm_s[i] / atr_s[i] if atr_s[i] else 0
        denom = di_p + di_m
        dx_list.append(100 * abs(di_p - di_m) / denom if denom else 0)
    adx_list = ema(dx_list, n)
    return round(adx_list[-1], 2) if adx_list else None

def calc_atr(highs, lows, closes, n=14):
    if len(closes) < n + 1:
        return None
    trs      = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
                for i in range(1, len(closes))]
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
        a   = calc_atr(highs[:idx], lows[:idx], closes[:idx], 14)
        if a and closes[idx]:
            ref_atrs.append((a / closes[idx]) * 100)
    if not ref_atrs:
        return False
    ref_avg = sum(ref_atrs) / len(ref_atrs)
    return atr_pct > ref_avg * hot_mult

def get_pivots(highs, lows, left, right):
    """Son pivot high ve low döndür (swing varsa SL/TP için)."""
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
    last_sh = ph_list[-1][1] if ph_list else None
    prev_sh = ph_list[-2][1] if len(ph_list) >= 2 else None
    last_sl = pl_list[-1][1] if pl_list else None
    prev_sl = pl_list[-2][1] if len(pl_list) >= 2 else None
    return last_sh, prev_sh, last_sl, prev_sl

# ========== ANALİZ ==========

def get_htf_bias(symbol):
    """
    1h + 4h EMA50 filtresi (paper_trader ile birebir aynı).
    Her iki TF'de fiyat EMA50 üstünde → BULL
    Her iki TF'de fiyat EMA50 altında  → BEAR
    Aksi halde                         → NEUTRAL
    """
    try:
        c1h, _, _, _ = get_klines(symbol, "1h", 60)
        c4h, _, _, _ = get_klines(symbol, "4h", 60)
        if not c1h or len(c1h) < 55:
            return "NEUTRAL"
        ema50_1h = ema(c1h, 50)
        ema50_4h = ema(c4h, 50) if c4h and len(c4h) >= 55 else None
        p1h = c1h[-2]
        e1h = ema50_1h[-1] if ema50_1h else p1h
        p4h = c4h[-2] if c4h and len(c4h) >= 2 else p1h
        e4h = ema50_4h[-1] if ema50_4h else p4h
        if p1h > e1h and p4h > e4h:
            return "BULL"
        elif p1h < e1h and p4h < e4h:
            return "BEAR"
    except Exception:
        pass
    return "NEUTRAL"


def analyze(symbol, interval="15m"):
    closes, volumes, highs, lows = get_klines(symbol, interval, 250)
    if not closes or len(closes) < 120:
        return None

    rsi_val           = calc_rsi(closes[-20:], 14)
    macd_val, sig_val = calc_macd(closes)
    adx_val           = calc_adx(highs, lows, closes)
    atr_val           = calc_atr(highs, lows, closes)

    if any(v is None for v in [rsi_val, macd_val, sig_val, adx_val, atr_val]):
        return None

    ema9_s   = ema(closes, EMA_FAST_LEN)
    ema21_s  = ema(closes, 21)
    ema50_s  = ema(closes, EMA_TREND_LEN)
    ema100_s = ema(closes, 100)
    if not ema9_s or not ema21_s or not ema50_s or not ema100_s:
        return None

    ema9   = ema9_s[-1]
    ema21  = ema21_s[-1]
    ema50  = ema50_s[-1]
    ema100 = ema100_s[-1]
    price  = closes[-2]

    # EMA cross — son CROSS_LOOKBACK barda crossover olduysa geçerli
    recent_cross_up = any(
        ema9_s[-(CROSS_LOOKBACK - i)] > ema21_s[-(CROSS_LOOKBACK - i)] and
        ema9_s[-(CROSS_LOOKBACK - i + 1)] <= ema21_s[-(CROSS_LOOKBACK - i + 1)]
        for i in range(CROSS_LOOKBACK) if (CROSS_LOOKBACK - i + 1) <= len(ema9_s)
    )
    recent_cross_down = any(
        ema9_s[-(CROSS_LOOKBACK - i)] < ema21_s[-(CROSS_LOOKBACK - i)] and
        ema9_s[-(CROSS_LOOKBACK - i + 1)] >= ema21_s[-(CROSS_LOOKBACK - i + 1)]
        for i in range(CROSS_LOOKBACK) if (CROSS_LOOKBACK - i + 1) <= len(ema9_s)
    )

    vol_avg    = sum(volumes[-20:]) / 20
    vol_spike  = volumes[-2] > vol_avg * 1.5
    high_vol   = vol_spike
    is_hot_vol = calc_atr_pct_hot(highs, lows, closes, hot_mult=HOT_VOL_MULT)

    # HTF bias — 1h + 4h EMA50 (paper_trader ile aynı)
    htf_bias = get_htf_bias(symbol)
    htf_bull = htf_bias == "BULL"
    htf_bear = htf_bias == "BEAR"

    # Swing yapısı — HH/HL ve LH/LL (paper_trader ile aynı)
    last_sh, prev_sh, last_sl, prev_sl = get_pivots(highs, lows, STRUCT_LEN, STRUCT_LEN)
    struct_bull = bool(last_sh and prev_sh and last_sl and prev_sl and
                       last_sh > prev_sh and last_sl > prev_sl)
    struct_bear = bool(last_sh and prev_sh and last_sl and prev_sl and
                       last_sh < prev_sh and last_sl < prev_sl)

    near_resist  = bool(last_sh and abs(price - last_sh) / price < 0.005)
    near_support = bool(last_sl and abs(price - last_sl) / price < 0.005)

    hist = macd_val - sig_val

    # ── CONFLUENCE SKORLAMA (paper_trader ile birebir aynı) ──
    c_trend_bull  = htf_bull
    c_struct_bull = struct_bull
    c_ema_bull    = ema9 > ema21 and price > ema50
    c_rsi_bull    = 50 < rsi_val < 70
    c_macd_bull   = macd_val > sig_val and hist > 0
    c_vol_bull    = high_vol

    c_trend_bear  = htf_bear
    c_struct_bear = struct_bear
    c_ema_bear    = ema9 < ema21 and price < ema50
    c_rsi_bear    = 30 < rsi_val < 50
    c_macd_bear   = macd_val < sig_val and hist < 0
    c_vol_bear    = high_vol

    long_score  = sum([c_trend_bull, c_struct_bull, c_ema_bull, c_rsi_bull, c_macd_bull, c_vol_bull])
    short_score = sum([c_trend_bear, c_struct_bear, c_ema_bear, c_rsi_bear, c_macd_bear, c_vol_bear])

    strong_buy  = (not is_hot_vol and long_score  >= MIN_CONFLUENCE
                   and recent_cross_up   and not near_resist  and adx_val > ADX_MIN)
    strong_sell = (not is_hot_vol and short_score >= MIN_CONFLUENCE
                   and recent_cross_down and not near_support and adx_val > ADX_MIN)

    exit_long  = rsi_val > 75 or price < ema100 or (macd_val < sig_val and rsi_val < 48)
    exit_short = rsi_val < 25 or price > ema100 or (macd_val > sig_val and rsi_val > 52)

    return {
        "symbol":       symbol,
        "price":        round(price, 6),
        "bar_high":     round(highs[-2], 6),
        "bar_low":      round(lows[-2], 6),
        "atr":          round(atr_val, 6),
        "rsi":          rsi_val,
        "adx":          adx_val,
        "ema21":        round(ema21, 6),
        "ema50":        round(ema50, 6),
        "ema100":       round(ema100, 6),
        "macd_bull":    macd_val > sig_val,
        "vol_spike":    vol_spike,
        "long_score":   long_score,
        "short_score":  short_score,
        "strong_buy":   strong_buy,
        "strong_sell":  strong_sell,
        "exit_long":    exit_long,
        "exit_short":   exit_short,
        "is_hot_vol":   is_hot_vol,
        "htf_bias":     htf_bias,
        "last_sh":      round(last_sh, 6) if last_sh else None,
        "last_sl":      round(last_sl, 6) if last_sl else None,
    }


def build_entry_reason(result, direction):
    """İşlem açılma gerekçesini indikatör değerlerinden üretir."""
    rsi    = result.get("rsi", 0)
    adx    = result.get("adx", 0)
    price  = result.get("price", 1)
    ema21  = result.get("ema21", price)
    ema100 = result.get("ema100", price)

    parts = []

    if direction == "LONG":
        parts.append("EMA21/100 üstünde (trend ↑)")
    else:
        parts.append("EMA21/100 altında (trend ↓)")

    if direction == "LONG":
        rsi_label = "güçlü momentum" if rsi >= 63 else "yükselen momentum"
        parts.append(f"RSI {round(rsi,1)} — {rsi_label}")
    else:
        rsi_label = "güçlü baskı" if rsi <= 37 else "düşen momentum"
        parts.append(f"RSI {round(rsi,1)} — {rsi_label}")

    adx_label = "çok güçlü trend" if adx >= 40 else "güçlü trend" if adx >= 30 else "trend başlangıcı"
    parts.append(f"ADX {round(adx,1)} — {adx_label}")

    if result.get("macd_bull"):
        parts.append("MACD sinyal üstünde")
    else:
        parts.append("MACD sinyal altında")

    if result.get("vol_spike"):
        parts.append("hacim patlaması ✅")

    return parts


def calc_win_prob(result, direction, sl_pct, tp_pct):
    """
    0-100 arası tahmini başarı olasılığı.
    RSI gücü, ADX, MACD mesafesi, hacim ve R:R oranına göre hesaplanır.
    """
    rsi    = result.get("rsi", 50)
    adx    = result.get("adx", 0)
    price  = result.get("price", 1)
    ema21  = result.get("ema21", price)
    ema100 = result.get("ema100", price)

    rr        = tp_pct / sl_pct if sl_pct > 0 else 1.0
    base_prob = round(1 / (1 + rr) * 100, 1)

    bonus = 0

    if direction == "LONG":
        if 58 <= rsi <= 68:   bonus += 15
        elif 55 <= rsi < 58:  bonus += 8
        elif rsi > 68:        bonus += 4
    else:
        if 32 <= rsi <= 42:   bonus += 15
        elif 42 < rsi <= 45:  bonus += 8
        elif rsi < 32:        bonus += 4

    if adx >= 40:   bonus += 15
    elif adx >= 30: bonus += 10
    elif adx >= 22: bonus += 5

    ema21_dist = abs(price - ema21) / ema21 * 100 if ema21 else 99
    if ema21_dist < 0.5:   bonus += 10
    elif ema21_dist < 1.5: bonus += 6
    elif ema21_dist < 3.0: bonus += 3

    ema100_dist = abs(price - ema100) / ema100 * 100 if ema100 else 99
    if ema100_dist < 1.0:   bonus += 8
    elif ema100_dist < 2.5: bonus += 4

    if result.get("vol_spike"):
        bonus += 7

    prob = min(round(base_prob + bonus), 89)
    prob = max(prob, 35)
    return prob, round(rr, 2)

# ========== DURUM YÖNETİMİ ==========

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"positions": {}, "total_bars": 0, "bar_counter": {}, "closed": []}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def _today_str():
    return datetime.now(timezone.utc).strftime("%d.%m.%Y")

def calc_daily_pnl(state):
    """Bugün kapanan işlemlerin toplam PnL'i (USDT)."""
    today = _today_str()
    total = 0
    for t in state.get("closed", []):
        et = t.get("exit_time", "")
        if et.startswith(today):
            total += t.get("pnl_usdt", 0)
    return round(total, 2)

def check_risk_limits(state, total_equity):
    """total_equity = walletBalance (margin dahil toplam). avail değil — pozisyon açınca avail düşer."""
    daily_pnl = calc_daily_pnl(state)
    daily_limit_hit = daily_pnl <= -DAILY_LOSS_LIMIT_USDT

    peak = state.get("peak_balance")
    if peak is None or (peak == INITIAL_CAPITAL and total_equity < INITIAL_CAPITAL):
        peak = total_equity
    if total_equity > peak:
        peak = total_equity
    state["peak_balance"] = peak
    drawdown = (peak - total_equity) / peak * 100 if peak > 0 else 0
    drawdown_hit = drawdown >= DRAWDOWN_PCT

    return daily_limit_hit, drawdown_hit, daily_pnl, peak, drawdown

def _binance_close_fill_summary(symbol):
    """
    Pozisyon borsada kapandıktan sonra userTrades'ten gerçek realized PnL ve çıkış fiyatı.
    Analizdeki entry_price ile değil, Binance'in realizedPnl'i ile uyumlu sonuç verir.
    Dönüş: (exit_price_avg, net_pnl_usdt, sum_commission) veya None.
    """
    try:
        trades = get_user_trades(symbol, limit=50)
        if not trades:
            return None
        by_time     = sorted(trades, key=lambda t: int(t.get("time", 0)), reverse=True)
        oid         = by_time[0].get("orderId")
        close_fills = [t for t in trades if t.get("orderId") == oid]
        if not close_fills:
            return None
        rpnl        = sum(float(t.get("realizedPnl", 0) or 0) for t in close_fills)
        comm_signed = sum(float(t.get("commission", 0) or 0) for t in close_fills)
        qty_sum     = sum(float(t.get("qty", 0) or 0) for t in close_fills)
        if qty_sum <= 0:
            exit_px = float(close_fills[0].get("price", 0))
        else:
            exit_px = sum(
                float(t.get("price", 0)) * float(t.get("qty", 0)) for t in close_fills
            ) / qty_sum
        # Binance: commission genelde negatif USDT; cüzdan ≈ realizedPnl + commission
        net      = round(rpnl + comm_signed, 4)
        comm_abs = abs(comm_signed)
        return exit_px, net, comm_abs
    except Exception:
        return None

def _notify_trail(sym, old_sl, new_sl, entry, entry_atr, direction):
    """Trailing stop güncellemesinde Telegram bildirimi — sadece anlamlı kademede."""
    if direction == "LONG":
        old_locked = (old_sl - entry) / entry_atr
        new_locked = (new_sl - entry) / entry_atr
        was_profit = old_sl > entry
        now_profit = new_sl > entry
    else:
        old_locked = (entry - old_sl) / entry_atr
        new_locked = (entry - new_sl) / entry_atr
        was_profit = old_sl < entry
        now_profit = new_sl < entry

    # SL ilk defa kâr bölgesine girdi
    if not was_profit and now_profit:
        tg_send(
            f"🔒 <b>Trailing Stop — Breakeven</b> | {sym}\n"
            f"SL kâr bölgesine girdi: {old_sl} → <b>{new_sl}</b>"
        )
    # Her tam ATR kademesinde bildir
    elif now_profit and int(new_locked) > int(max(0, old_locked)):
        tier = int(new_locked)
        emoji = "📈" if direction == "LONG" else "📉"
        tg_send(
            f"{emoji} <b>Trailing Stop +{tier} ATR</b> | {sym}\n"
            f"SL: {old_sl} → <b>{new_sl}</b>\n"
            f"✅ Kilitli kâr: +{round(new_locked, 1)} ATR"
        )

def _extend_tp(state, sym, pos, entry_atr, hit_tp):
    """
    TP aşıldığında pozisyonu kapatmak yerine:
    - trail_mult sıkılaştır (min TRAIL_MIN_MULT)
    - TP'yi bir ATR × RR_RATIO kadar uzat
    - Binance order'larını güncelle
    - Telegram bildirimi gönder
    """
    direction   = pos["direction"]
    entry       = pos["entry_price"]
    trail_mult  = pos.get("trail_mult", TRAIL_ATR_MULT)
    trail_level = pos.get("trail_level", 0)

    new_mult    = max(TRAIL_MIN_MULT, trail_mult - TRAIL_TIGHTEN)
    new_level   = trail_level + 1
    old_tp      = pos["tp"]

    if direction == "LONG":
        new_tp = round_price(sym, old_tp + entry_atr * 2.0)
        new_sl = round_price(sym, hit_tp - entry_atr * new_mult)
    else:
        new_tp = round_price(sym, old_tp - entry_atr * 2.0)
        new_sl = round_price(sym, hit_tp + entry_atr * new_mult)

    # SL sadece kâr yönünde hareket eder
    if direction == "LONG" and new_sl <= pos["sl"]:
        new_sl = pos["sl"]
    if direction == "SHORT" and new_sl >= pos["sl"]:
        new_sl = pos["sl"]

    pos["tp"]          = new_tp
    pos["sl"]          = new_sl
    pos["trail_mult"]  = new_mult
    pos["trail_level"] = new_level
    pos["best_price"]  = hit_tp

    # Binance order'larını güncelle
    try:
        cancel_all_orders(sym)
        side = "SELL" if direction == "LONG" else "BUY"
        place_stop_market(sym, side, new_sl)
        place_take_profit_market(sym, side, new_tp)
    except Exception as e:
        _log_open(f"{sym}: _extend_tp order hatası: {e}")

    best = pos.get("best_price", entry)
    pnl_atr = ((best - entry) / entry_atr) if direction == "LONG" else ((entry - best) / entry_atr)
    emoji   = "📈" if direction == "LONG" else "📉"
    stars   = "🟢" * min(new_level, 5)
    print(f"  {stars} TP EXT [{sym}] Sev.{new_level}: TP {old_tp} → {new_tp} | SL → {new_sl} | Trail x{new_mult}")
    tg_send(
        f"{stars} <b>TP Aşıldı — Uzatıldı #{new_level}</b> | {sym}\n"
        f"{emoji} {direction}\n"
        f"━━━━━━━━━━━━━━\n"
        f"✅ Geçilen TP : {old_tp}\n"
        f"🎯 Yeni TP   : {new_tp}\n"
        f"🛑 Yeni SL   : {new_sl} (trail x{new_mult})\n"
        f"📊 Anlık kâr : ~+{round(pnl_atr, 1)} ATR"
    )


def _log_open(msg):
    print(f"   [binance_open] {msg}")

# ========== POZİSYON AÇMA ==========

def open_position(state, symbol, direction, price, atr, result, bias="NEUTRAL"):
    positions = state["positions"]
    if symbol in positions:
        _log_open(f"{symbol}: zaten açık — atlandı")
        return False
    if len(positions) >= MAX_OPEN:
        _log_open(f"{symbol}: max açık pozisyon ({MAX_OPEN}) — atlandı")
        return False

    last_bar = state.get("bar_counter", {}).get(symbol, -999)
    if state.get("total_bars", 0) - last_bar < COOLDOWN_BARS:
        _log_open(f"{symbol}: cooldown (son bar {last_bar}, gerekli aralık {COOLDOWN_BARS})")
        return False

    if bias == "BULL":
        lev       = BULL_LONG_LEV  if direction == "LONG" else BULL_SHORT_LEV
        max_long  = BULL_MAX_LONG
        max_short = BULL_MAX_SHORT
    elif bias == "BEAR":
        lev       = BEAR_LONG_LEV  if direction == "LONG" else BEAR_SHORT_LEV
        max_long  = BEAR_MAX_LONG
        max_short = BEAR_MAX_SHORT
    else:
        lev       = NEUT_LONG_LEV  if direction == "LONG" else NEUT_SHORT_LEV
        max_long  = NEUT_MAX_LONG
        max_short = NEUT_MAX_SHORT

    open_longs  = sum(1 for p in positions.values() if p.get("direction") == "LONG")
    open_shorts = sum(1 for p in positions.values() if p.get("direction") == "SHORT")
    if direction == "LONG"  and open_longs  >= max_long:
        _log_open(f"{symbol}: BULL yön kotası dolu ({open_longs}/{max_long} LONG) — atlandı")
        return False
    if direction == "SHORT" and open_shorts >= max_short:
        _log_open(f"{symbol}: SHORT yön kotası dolu ({open_shorts}/{max_short} SHORT) — atlandı")
        return False

    avail, total = get_balance()
    desired = max(total * POS_SIZE_PCT, 20.0)   # minimum 20 USDT margin
    margin  = min(desired, avail)
    if desired > avail:
        _log_open(f"{symbol}: margin hedef {desired:.2f} USDT → serbeste göre {margin:.2f} (avail={avail:.2f}, total={total:.2f})")
    if margin < 5 and avail < 5:
        _log_open(f"{symbol}: kullanılabilir margin çok düşük (avail={avail:.2f})")
        return False

    MIN_NOTIONAL = 100
    notional = margin * lev
    qty      = round_quantity(symbol, notional / price)
    if qty * price < MIN_NOTIONAL:
        need_m   = max(margin, (MIN_NOTIONAL / lev) + 2)
        margin   = min(need_m, avail)
        notional = margin * lev
        qty      = round_quantity(symbol, notional / price)
    if qty <= 0 or qty * price < MIN_NOTIONAL:
        _log_open(
            f"{symbol}: min notional sağlanamıyor (notional≈{qty * price if qty else 0:.2f}, "
            f"min={MIN_NOTIONAL}, avail={avail:.2f})"
        )
        return False

    last_sh         = (result or {}).get("last_sh")
    last_sl         = (result or {}).get("last_sl")
    MIN_PRICE_RATIO = 0.001

    if direction == "LONG":
        atr_sl = max(price - atr * STOP_ATR_MULT, price * (1 - MAX_SL_PCT/100))
        atr_tp = price + atr * TAKE_ATR_MULT
        if last_sl and last_sl < price:
            sl_pre = max(last_sl, price * (1 - MAX_SL_PCT/100))
        else:
            sl_pre = atr_sl
        if last_sh and last_sh > price:
            tp_pre = last_sh
        else:
            tp_pre = atr_tp
        if sl_pre <= 0:
            _log_open(f"{symbol}: LONG SL geçersiz (sl_pre={sl_pre}, price={price})")
            return False
        sl = round_price(symbol, max(sl_pre, price * MIN_PRICE_RATIO))
        tp = round_price(symbol, max(tp_pre, price * (1 + MIN_PRICE_RATIO)))
    else:
        atr_sl = min(price + atr * STOP_ATR_MULT, price * (1 + MAX_SL_PCT/100))
        atr_tp = price - atr * TAKE_ATR_MULT
        if last_sh and last_sh > price:
            sl_pre = min(last_sh, price * (1 + MAX_SL_PCT/100))
        else:
            sl_pre = atr_sl
        if last_sl and last_sl < price:
            tp_pre = last_sl
        else:
            tp_pre = atr_tp
        if tp_pre <= 0:
            _log_open(f"{symbol}: SHORT TP geçersiz (tp_pre={tp_pre}, price={price}, ATR={atr})")
            return False
        sl = round_price(symbol, sl_pre)
        tp = round_price(symbol, max(tp_pre, price * MIN_PRICE_RATIO))

    if sl <= 0 or tp <= 0:
        _log_open(f"{symbol}: SL/TP tick sonrası geçersiz (sl={sl}, tp={tp})")
        return False

    swing_note = []
    if direction == "LONG":
        if last_sl and last_sl < price:
            swing_note.append("SL pivot")
        if last_sh and last_sh > price:
            swing_note.append("TP pivot")
    else:
        if last_sh and last_sh > price:
            swing_note.append("SL pivot")
        if last_sl and last_sl < price:
            swing_note.append("TP pivot")
    if swing_note:
        _log_open(f"{symbol}: swing kullanıldı ({', '.join(swing_note)})")

    atr_pct            = round((atr / price) * 100, 3) if price else 0
    atr_lvl            = round(price + atr, 6) if direction == "LONG" else round(price - atr, 6)
    sl_pct             = round(abs(price - sl) / price * 100, 3)
    tp_pct             = round(abs(tp - price) / price * 100, 3)
    win_prob, rr_ratio = calc_win_prob(result or {}, direction, sl_pct, tp_pct)
    if rr_ratio < MIN_RR_RATIO:
        _log_open(f"{symbol}: R:R 1:{rr_ratio} < min {MIN_RR_RATIO} (sl%{sl_pct} tp%{tp_pct}) — atlandı")
        return False
    reasons        = build_entry_reason(result or {}, direction)
    reason_str     = "\n".join(f"   • {r}" for r in reasons)
    htf_bias_val   = (result or {}).get("htf_bias", bias)
    bias_label     = "Boğa (1h)" if htf_bias_val == "BULL" else "Ayı (1h)" if htf_bias_val == "BEAR" else ("HTF kapalı" if htf_bias_val == "OFF" else "Nötr (1h)")
    prob_filled    = min(6, max(0, round(win_prob * 6 / 100)))
    prob_bar       = "⬜️" * prob_filled + "⬛️" * (6 - prob_filled)
    prob_emoji     = "🟢" if win_prob >= 60 else "🟡" if win_prob >= 45 else "🔴"

    try:
        set_leverage(symbol, lev)
        if direction == "LONG":
            place_market_order(symbol, "BUY", qty)
            place_stop_market(symbol, "SELL", sl)
            place_take_profit_market(symbol, "SELL", tp)
        else:
            place_market_order(symbol, "SELL", qty)
            place_stop_market(symbol, "BUY", sl)
            place_take_profit_market(symbol, "BUY", tp)

        # Gerçek fill fiyatını Binance position'dan çek (entryPrice en güvenilir kaynak)
        fill_price = price
        try:
            import time as _time
            _time.sleep(1.0)  # pozisyon kayıt süresi
            positions = get_positions()
            for p in positions:
                if p.get("symbol") == symbol:
                    ep = float(p.get("entryPrice", 0))
                    if ep > 0:
                        fill_price = ep
                    break
        except Exception:
            pass

        state["positions"][symbol] = {
            "symbol":       symbol,
            "direction":    direction,
            "entry_price":  fill_price,
            "sl":           sl, "tp": tp,
            "open_bar":     state.get("total_bars", 0),
            "open_time":    now_str(),
            "leverage":     lev,
            "margin":       margin,
            "entry_atr":    round(atr, 6),
            "win_prob":     win_prob,
            "entry_reason": reasons,
            "htf_bias":     htf_bias_val,
            "best_price":   fill_price,
            "trail_mult":   TRAIL_ATR_MULT,
            "trail_level":  0,
        }
        state.setdefault("bar_counter", {})[symbol] = state.get("total_bars", 0)

        emoji  = "📈" if direction == "LONG" else "📉"
        n_open = len(state["positions"])
        _log_open(f"{symbol}: OK | {direction} margin={margin:.2f} R:R=1:{rr_ratio} açık={n_open} fill={fill_price}")
        print(f"  {emoji} {direction}: {symbol} @ {fill_price} | SL:{sl} ({sl_pct}%) | TP:{tp} ({tp_pct}%) | Başarı:%{win_prob} | {bias_label} {lev}x")
        tg_send(
            f"{emoji} <b>Yeni İşlem Açıldı #{n_open}</b>\n"
            f"<b>{direction}</b> | <b>{symbol}</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎯 Giriş : {fill_price}\n"
            f"🛑 SL : {sl} (-%{sl_pct})\n"
            f"✅ TP : {tp} (+%{tp_pct})\n"
            f"📉 ATR : {atr} (%{atr_pct}) → {atr_lvl}\n"
            f"━━━━━━━━━━━━━━\n"
            f"{prob_emoji} <b>Başarı Tahmini : %{win_prob}</b>\n"
            f"{prob_bar} R:R = 1:{rr_ratio}\n"
            f"━━━━━━━━━━━━━━\n"
            f"⚖️ Piyasa: {bias_label} -> {lev}x kaldıraç\n"
            f"Margin: {margin:.2f} USDT | Açık pozisyon: {n_open}\n"
            f"━━━━━━━━━━━━━━\n"
            f"📋 <b>Neden açtım?</b>\n"
            f"{reason_str}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 Bakiye: {avail:.2f} USDT\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
        )
        return True
    except Exception as e:
        print(f"   ❌ {symbol} emir hatası: {e}")
        tg_send(f"❌ <b>Binance Emir Hatası</b>\n{symbol}: {str(e)}")
        return False

# ========== POZİSYON KAPATMA ==========

def close_position(
    state,
    pos,
    price,
    reason,
    already_closed=False,
    binance_net_pnl_usdt=None,
    binance_commission_usdt=None,
):
    """
    binance_net_pnl_usdt: userTrades realizedPnl − fill komisyonu (borsa ile uyumlu net).
    binance_commission_usdt: fill komisyonları toplamı (gösterim için).
    Verilmezse: grafik entry_price vs çıkış (slippage'da telefonla çelişebilir).
    """
    symbol = pos["symbol"]
    if not already_closed:
        try:
            cancel_all_orders(symbol)
            positions = get_positions()
            for p in positions:
                if p["symbol"] == symbol:
                    amt  = float(p["positionAmt"])
                    side = "SELL" if amt > 0 else "BUY"
                    place_market_order(symbol, side, abs(amt))
                    break
        except Exception as e:
            print(f"   ❌ Kapatma hatası {symbol}: {e}")
            tg_send(f"❌ Kapatma hatası {symbol}: {e}")
            return

    direction = pos["direction"]
    entry     = pos["entry_price"]
    lev       = pos.get("leverage", LEVERAGE)
    margin    = pos.get("margin", 10)
    notional  = margin * lev

    if binance_net_pnl_usdt is not None:
        pnl_usdt = round(float(binance_net_pnl_usdt), 2)
        pnl_pct  = round((pnl_usdt / margin) * 100, 2) if margin else 0.0
        if binance_commission_usdt is not None:
            commission = round(float(binance_commission_usdt), 4)
        else:
            commission = round(notional * COMMISSION_PCT, 4)
    else:
        if direction == "LONG":
            price_chg_pct = (price - entry) / entry * 100
        else:
            price_chg_pct = (entry - price) / entry * 100
        pnl_pct    = round(price_chg_pct * lev, 2)
        commission = round(notional * COMMISSION_PCT, 4)
        pnl_usdt   = round(margin * pnl_pct / 100 - commission, 2)

    trade = {
        **pos, "exit_price": price, "exit_time": now_str(),
        "reason": reason, "pnl_pct": pnl_pct, "pnl_usdt": pnl_usdt,
        "commission": commission, "trade_no": len(state.get("closed", [])) + 1,
        "pnl_from_binance": binance_net_pnl_usdt is not None,
        "win_prob": pos.get("win_prob"),
    }
    state["closed"] = state.get("closed", []) + [trade]
    if symbol in state.get("positions", {}):
        del state["positions"][symbol]
    state.setdefault("bar_counter", {})[symbol] = state.get("total_bars", 0)

    emoji      = "✅" if pnl_pct > 0 else "🔴"
    dir_emoji  = "📈" if direction == "LONG" else "📉"
    entry_atr  = pos.get("entry_atr")
    if entry_atr and entry:
        _atr_pct  = round(entry_atr / entry * 100, 3)
        _atr_lvl  = round(entry + entry_atr, 6) if direction == "LONG" else round(entry - entry_atr, 6)
        atr_line  = f"📉 ATR     : {entry_atr} (%{_atr_pct}) → {_atr_lvl}\n"
    else:
        atr_line  = ""
    held_bars  = state.get("total_bars", 0) - pos.get("open_bar", 0)
    held_min   = held_bars * 15
    duration_str = f"{held_min} dk" if held_min < 60 else (f"{held_min // 60}s {held_min % 60}dk" if held_min % 60 else f"{held_min // 60} saat")
    avail, _   = get_balance()

    bn_note = ""
    if trade.get("pnl_from_binance"):
        bn_note = "📌 <i>Net PnL borsa realized — Giriş satırı sinyal fiyatı; gerçek ort. giriş farklı olabilir.</i>\n"

    print(f"  {emoji} KAPANDI [{direction}]: {symbol} @ {price} | {'+' if pnl_pct>0 else ''}{pnl_pct}% | {reason}")
    tg_send(
        f"{emoji} <b>İşlem Kapandı #{trade['trade_no']}</b>\n"
        f"{dir_emoji} {direction} | <b>{symbol}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🕐 Açılış : {pos.get('open_time', '-')}\n"
        f"⏱ Süre   : {duration_str}\n"
        f"🎯 Giriş  : {pos['entry_price']}\n"
        f"🏁 Çıkış  : {price}\n"
        f"📊 Sonuç  : <b>{'+' if pnl_pct>0 else ''}{pnl_pct}%</b> ({'+' if pnl_usdt>0 else ''}{pnl_usdt:.3f} USDT) — {lev}x\n"
        f"💸 Komisyon: -{commission:.3f} USDT\n"
        f"{atr_line}"
        f"{bn_note}"
        f"💡 Neden  : {reason}\n"
        f"💰 Bakiye : {avail:.2f} USDT\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    )

# ========== ANA DÖNGÜ ==========

def run_scan(symbols):
    state = load_state()
    state.setdefault("total_bars", 0)
    now_utc    = datetime.now(timezone.utc)
    is_new_15m = now_utc.minute % 15 <= 4

    if is_new_15m:
        state["total_bars"] = state.get("total_bars", 0) + 1

    avail, total       = get_balance()
    binance_positions  = {p["symbol"]: p for p in get_positions()}
    cur_bar            = state["total_bars"]

    daily_limit_hit, drawdown_hit, daily_pnl, peak, drawdown = check_risk_limits(state, total)
    state["peak_balance"] = max(state.get("peak_balance", peak), total)

    print(f"\n🤖 Binance Trader 15m | {now_str()}")
    print(f"   İşlem: {len(state.get('closed', []))} | Bakiye: {avail:.2f} / {total:.2f} USDT | Açık: {len(state['positions'])}")
    if daily_limit_hit:
        print(f"   ⛔ Günlük limit: {daily_pnl:.2f} USDT (max -{DAILY_LOSS_LIMIT_USDT})")
    if drawdown_hit:
        print(f"   ⛔ Drawdown: %{drawdown:.1f} (limit %{DRAWDOWN_PCT})")

    # Her 5 dk: Açık pozisyonlarda Binance sync + 5m bar SL/TP kontrolü
    if state["positions"]:
        # Binance SL/TP ile kapanan pozisyonlar — her çalışmada sync
        for sym in list(state["positions"].keys()):
            if sym not in binance_positions:
                pos     = dict(state["positions"][sym], symbol=sym)
                summary = _binance_close_fill_summary(sym)
                if summary:
                    exit_price, net_pnl, comm_fills = summary
                    try:
                        if abs(exit_price - pos["sl"]) < abs(exit_price - pos["tp"]):
                            reason = "STOP LOSS (Binance)"
                        else:
                            reason = "TAKE PROFIT (Binance)"
                    except Exception:
                        reason = "BINANCE SL/TP"
                    print(f"   [binance_close] {sym}: net realized ≈ {net_pnl} USDT (userTrades)")
                    close_position(
                        state, pos, exit_price, reason,
                        already_closed=True,
                        binance_net_pnl_usdt=net_pnl,
                        binance_commission_usdt=comm_fills,
                    )
                else:
                    exit_price = pos["entry_price"]
                    reason     = "BINANCE SL/TP"
                    try:
                        trades = get_user_trades(sym, limit=5)
                        if trades:
                            by_t       = sorted(trades, key=lambda t: int(t.get("time", 0)), reverse=True)
                            exit_price = float(by_t[0].get("price", exit_price))
                            if abs(exit_price - pos["sl"]) < abs(exit_price - pos["tp"]):
                                reason = "STOP LOSS (Binance)"
                            else:
                                reason = "TAKE PROFIT (Binance)"
                    except Exception:
                        pass
                    close_position(state, pos, exit_price, reason, already_closed=True)

        # 5m bar ile SL/TP kontrolü + Trailing Stop
        for sym, pos in list(state["positions"].items()):
            if sym not in state["positions"]:
                continue
            pos_with_sym = dict(pos, symbol=sym)
            try:
                _, _, highs, lows = get_klines(sym, "5m", 5)
                if not highs or len(highs) < 2:
                    continue
                b_high, b_low = highs[-2], lows[-2]

                # ── SL / TP Kontrolü ──
                closed    = False
                entry_atr = pos.get("entry_atr", 0)
                if pos["direction"] == "LONG":
                    if b_low <= pos["sl"]:
                        close_position(state, pos_with_sym, pos["sl"], "STOP LOSS (5m)")
                        closed = True
                    elif b_high >= pos["tp"] and entry_atr > 0:
                        _extend_tp(state, sym, pos, entry_atr, pos["tp"])
                else:
                    if b_high >= pos["sl"]:
                        close_position(state, pos_with_sym, pos["sl"], "STOP LOSS (5m)")
                        closed = True
                    elif b_low <= pos["tp"] and entry_atr > 0:
                        _extend_tp(state, sym, pos, entry_atr, pos["tp"])

                if closed or sym not in state["positions"]:
                    continue

                # ── Trailing Stop ──
                entry     = pos["entry_price"]
                entry_atr = pos.get("entry_atr", 0)
                if entry_atr <= 0:
                    continue

                if pos["direction"] == "LONG":
                    new_best = max(pos.get("best_price", entry), b_high)
                    pos["best_price"] = new_best
                    profit_atr = (new_best - entry) / entry_atr
                    if profit_atr >= TRAIL_MIN_PROFIT_ATR:
                        new_sl = round_price(sym, new_best - entry_atr * TRAIL_ATR_MULT)
                        if new_sl > pos["sl"] + entry_atr * 0.1:
                            old_sl = pos["sl"]
                            try:
                                cancel_all_orders(sym)
                                place_stop_market(sym, "SELL", new_sl)
                                place_take_profit_market(sym, "SELL", pos["tp"])
                                pos["sl"] = new_sl
                                print(f"  📈 TRAIL [{sym}]: SL {old_sl} → {new_sl} (best={round(new_best,4)})")
                                _notify_trail(sym, old_sl, new_sl, entry, entry_atr, "LONG")
                            except Exception as e:
                                _log_open(f"{sym}: trail SL hatası: {e}")
                else:
                    new_best = min(pos.get("best_price", entry), b_low)
                    pos["best_price"] = new_best
                    profit_atr = (entry - new_best) / entry_atr
                    if profit_atr >= TRAIL_MIN_PROFIT_ATR:
                        new_sl = round_price(sym, new_best + entry_atr * TRAIL_ATR_MULT)
                        if new_sl < pos["sl"] - entry_atr * 0.1:
                            old_sl = pos["sl"]
                            try:
                                cancel_all_orders(sym)
                                place_stop_market(sym, "BUY", new_sl)
                                place_take_profit_market(sym, "BUY", pos["tp"])
                                pos["sl"] = new_sl
                                print(f"  📉 TRAIL [{sym}]: SL {old_sl} → {new_sl} (best={round(new_best,4)})")
                                _notify_trail(sym, old_sl, new_sl, entry, entry_atr, "SHORT")
                            except Exception as e:
                                _log_open(f"{sym}: trail SL hatası: {e}")
            except Exception:
                pass

    if is_new_15m:
        scan_start = datetime.now(timezone.utc)
        scan_set   = list(set(symbols) | set(state["positions"].keys()))
        results    = {}
        with ThreadPoolExecutor(max_workers=30) as ex:
            futures = {ex.submit(analyze, sym, "15m"): sym for sym in scan_set}
            for f in as_completed(futures):
                sym = futures[f]
                try:
                    results[sym] = f.result()
                except Exception:
                    results[sym] = None

        elapsed = round((datetime.now(timezone.utc) - scan_start).total_seconds(), 1)
        print(f"   🔍 Tarama tamamlandı: {elapsed}s")

        bias, bias_desc = get_market_bias()
        print(f"   {('🐂' if bias=='BULL' else '🐻' if bias=='BEAR' else '⚖️')} {bias} — {bias_desc}")

        if drawdown_hit and state["positions"]:
            tg_send(
                f"⛔ <b>DRAWDOWN CIRCUIT BREAKER</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"Peak: {peak:.2f} → Toplam: {total:.2f} USDT\n"
                f"Drawdown: %{drawdown:.1f} (limit %{DRAWDOWN_PCT})\n"
                f"Tüm pozisyonlar kapatılıyor.\n"
                f"🕐 {now_str()}"
            )
            for sym, pos in list(state["positions"].items()):
                pos_with_sym = dict(pos, symbol=sym)
                try:
                    bp    = binance_positions.get(sym)
                    price = float(bp.get("markPrice", pos["entry_price"])) if bp else (results.get(sym, {}).get("price", pos["entry_price"]))
                    close_position(state, pos_with_sym, price, "DRAWDOWN CIRCUIT BREAKER")
                except Exception as e:
                    print(f"   ❌ Circuit breaker kapatma {sym}: {e}")
        elif drawdown_hit:
            tg_send(
                f"⛔ <b>DRAWDOWN LİMİTİ AŞILDI</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"Peak: {peak:.2f} → Toplam: {total:.2f} USDT\n"
                f"Drawdown: %{drawdown:.1f} (limit %{DRAWDOWN_PCT})\n"
                f"Açık pozisyon yok.\n"
                f"🕐 {now_str()}"
            )

        def _exit_reason(direction, r):
            parts = []
            if direction == "LONG":
                if r["rsi"] > 75:            parts.append("RSI aşırı alım")
                if not r["macd_bull"]:       parts.append("MACD bear")
                if r["price"] < r["ema100"]: parts.append("EMA100 altı")
            else:
                if r["rsi"] < 25:            parts.append("RSI aşırı satım")
                if r["macd_bull"]:           parts.append("MACD bull")
                if r["price"] > r["ema100"]: parts.append("EMA100 üstü")
            label = "SATIŞ SİNYALİ" if direction == "LONG" else "KAPANIŞ SİNYALİ"
            return f"{label} — " + (", ".join(parts) if parts else "sinyal")

        # 15m bar SL/TP ve çıkış sinyali
        for sym, pos in list(state["positions"].items()):
            if sym not in state["positions"]:
                continue
            r = results.get(sym)
            if not r:
                continue
            b_high = r["bar_high"]
            b_low  = r["bar_low"]
            held   = cur_bar - pos.get("open_bar", cur_bar)

            if pos["direction"] == "LONG" and b_low <= pos["sl"]:
                close_position(state, pos, pos["sl"], "STOP LOSS")
                continue
            elif pos["direction"] == "SHORT" and b_high >= pos["sl"]:
                close_position(state, pos, pos["sl"], "STOP LOSS")
                continue

            if sym not in state["positions"]:
                continue
            entry_atr_15 = pos.get("entry_atr", 0)
            if pos["direction"] == "LONG" and b_high >= pos["tp"] and entry_atr_15 > 0:
                _extend_tp(state, sym, pos, entry_atr_15, pos["tp"])
                continue
            elif pos["direction"] == "SHORT" and b_low <= pos["tp"] and entry_atr_15 > 0:
                _extend_tp(state, sym, pos, entry_atr_15, pos["tp"])
                continue

            if sym not in state["positions"]:
                continue
            in_profit = (r["price"] > pos["entry_price"]) if pos["direction"] == "LONG" else (r["price"] < pos["entry_price"])
            if not in_profit:
                if held >= MAX_LOSS_BARS:
                    close_position(state, pos, r["price"], "ZAMAN AŞIMI (45dk zararda)")
                elif held >= MIN_HOLD_BARS:
                    exit_triggered = (pos["direction"] == "LONG" and r["exit_long"]) or (pos["direction"] == "SHORT" and r["exit_short"])
                    if exit_triggered:
                        close_position(state, pos, r["price"], _exit_reason(pos["direction"], r))
            else:
                # 45 dk geçti ve kârdaysa → SL'yi breakeven'a çek (bir kez)
                if held >= MAX_LOSS_BARS and not pos.get("breakeven_set"):
                    entry = pos["entry_price"]
                    be_sl = round_price(sym, entry)
                    if pos["direction"] == "LONG" and pos["sl"] < entry:
                        try:
                            cancel_all_orders(sym)
                            place_stop_market(sym, "SELL", be_sl)
                            place_take_profit_market(sym, "SELL", pos["tp"])
                        except Exception as e:
                            _log_open(f"{sym}: breakeven emir hatası: {e}")
                        pos["sl"] = be_sl
                        pos["breakeven_set"] = True
                        _log_open(f"{sym}: BREAKEVEN — SL giriş fiyatına çekildi ({be_sl})")
                        print(f"  🔒 BREAKEVEN [{sym}]: SL → {be_sl}")
                        tg_send(f"🔒 <b>Breakeven</b> | {sym}\n45dk+ kârda → SL giriş fiyatına çekildi: {be_sl}")
                    elif pos["direction"] == "SHORT" and pos["sl"] > entry:
                        try:
                            cancel_all_orders(sym)
                            place_stop_market(sym, "BUY", be_sl)
                            place_take_profit_market(sym, "BUY", pos["tp"])
                        except Exception as e:
                            _log_open(f"{sym}: breakeven emir hatası: {e}")
                        pos["sl"] = be_sl
                        pos["breakeven_set"] = True
                        _log_open(f"{sym}: BREAKEVEN — SL giriş fiyatına çekildi ({be_sl})")
                        print(f"  🔒 BREAKEVEN [{sym}]: SL → {be_sl}")
                        tg_send(f"🔒 <b>Breakeven</b> | {sym}\n45dk+ kârda → SL giriş fiyatına çekildi: {be_sl}")

        # Yeni giriş
        if daily_limit_hit:
            print(f"   ⛔ Günlük kayıp limiti ({daily_pnl:.2f} USDT) — yeni işlem açılmıyor")
        else:
            found = 0
            for symbol in symbols:
                if len(state["positions"]) >= MAX_OPEN:
                    print(f"   ℹ️  Max {MAX_OPEN} açık pozisyon — yeni giriş taraması durdu")
                    break
                r = results.get(symbol)
                if not r:
                    continue
                if r["strong_buy"]:
                    if open_position(state, symbol, "LONG", r["price"], r["atr"], r, "NEUTRAL"):
                        found += 1
                elif r["strong_sell"]:
                    if open_position(state, symbol, "SHORT", r["price"], r["atr"], r, "NEUTRAL"):
                        found += 1
            if found == 0:
                print(f"   ℹ️  Bu turda sinyal bulunamadı.")
            else:
                print(f"   ✅ Bu turda {found} yeni işlem açıldı.")
            if found == 0 and now_utc.minute == 0:
                msg = (
                    f"🔍 <b>Sinyal Taraması</b> | {now_str()}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"ℹ️ Bu saatte uygun işlem bulunamadı.\n"
                    f"💰 Bakiye : {avail:.2f} USDT\n"
                    f"🔓 Açık    : {len(state['positions'])} pozisyon\n"
                    f"🔢 Toplam  : {len(state.get('closed', []))} işlem"
                )
                if daily_limit_hit:
                    msg += f"\n⛔ Günlük limit: {daily_pnl:.2f} USDT"
                tg_send(msg)

    save_state(state)

    closed  = state.get("closed", [])
    cur_bar = state.get("total_bars", 0)
    if len(closed) % 100 == 0 and len(closed) > 0:
        print(f"\n🎯 {len(closed)} İŞLEM RAPORU GÖNDERİLİYOR...")
        analyze_performance(state)
        send_full_report(state)
    if is_new_15m and cur_bar % 288 == 0 and cur_bar > 0:
        send_status_report(state)
        send_win_prob_report(state)

    return state

# ========== RAPORLAR ==========

def analyze_performance(state):
    trades = state.get("closed", [])
    if not trades:
        return
    _, total   = get_balance()
    wins       = [t for t in trades if t["pnl_pct"] > 0]
    losses     = [t for t in trades if t["pnl_pct"] <= 0]
    longs      = [t for t in trades if t.get("direction") == "LONG"]
    shorts     = [t for t in trades if t.get("direction") == "SHORT"]
    total_pnl  = sum(t["pnl_usdt"] for t in trades)
    win_rate   = round(len(wins) / len(trades) * 100, 1)
    avg_win    = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss   = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    print(f"""
{'='*50}
📊 BINANCE TRADER ANALİZİ — {len(trades)} İşlem
{'='*50}
💰 Bakiye   : {total:.2f} USDT
📈 Toplam PnL: {'+' if total_pnl>0 else ''}{total_pnl:.2f} USDT
🎯 Kazanma   : %{win_rate}
✅ Kârlı     : {len(wins)} | 🔴 Zararlı: {len(losses)}
📊 Ort. Kâr  : %{avg_win} | Ort. Zarar: %{avg_loss}
📈 Long      : {len(longs)} | 📉 Short: {len(shorts)}
{'='*50}""")
    report = {
        "summary": {
            "total_trades": len(trades), "win_rate_pct": win_rate,
            "total_pnl_usdt": round(total_pnl, 2),
            "balance": total,
            "avg_win_pct": avg_win, "avg_loss_pct": avg_loss,
            "long_count": len(longs), "short_count": len(shorts),
        },
        "trades": trades
    }
    with open(os.path.join(os.path.dirname(__file__), "binance_report.json"), "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def send_status_report(state):
    trades     = state.get("closed", [])
    if not trades:
        return
    _, total   = get_balance()
    wins       = [t for t in trades if t["pnl_pct"] > 0]
    losses     = [t for t in trades if t["pnl_pct"] < 0]
    stops      = [t for t in trades if t.get("reason") == "STOP LOSS"]
    tps        = [t for t in trades if t.get("reason") == "TAKE PROFIT"]
    longs      = [t for t in trades if t.get("direction") == "LONG"]
    shorts     = [t for t in trades if t.get("direction") == "SHORT"]
    total_pnl  = sum(t["pnl_usdt"] for t in trades)
    total_comm = round(sum(t.get("commission", 0) for t in trades), 4)
    win_rate   = round(len(wins) / len(trades) * 100, 1)
    avg_win    = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss   = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    roi        = round((total - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2)
    recent     = trades[-20:] if len(trades) >= 20 else trades
    rec_wr     = round(len([t for t in recent if t["pnl_pct"] > 0]) / len(recent) * 100, 1)
    trend      = "📈" if rec_wr > win_rate else "📉"
    cap_emoji  = "💚" if total >= INITIAL_CAPITAL else "🔴"
    daily_trades = trades[-288:] if len(trades) >= 288 else trades
    daily_comm   = round(sum(t.get("commission", 0) for t in daily_trades), 4)
    daily_pnl    = round(sum(t["pnl_usdt"] for t in daily_trades), 2)
    tg_send(
        f"📊 <b>Günlük Rapor (24s)</b> | {now_str()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{cap_emoji} Bakiye   : <b>{total:.2f} USDT</b> ({'+' if roi>=0 else ''}{roi}%)\n"
        f"📈 Toplam PnL: <b>{'+' if total_pnl>=0 else ''}{total_pnl:.2f} USDT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Win Rate  : <b>%{win_rate}</b> ({len(wins)}K / {len(losses)}Z)\n"
        f"{trend} Son 20 işlem: <b>%{rec_wr}</b>\n"
        f"📊 Ort. Kâr  : %{avg_win} | Ort. Zarar: %{avg_loss}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 Toplam    : {len(trades)} işlem\n"
        f"📈 Long      : {len(longs)} | 📉 Short: {len(shorts)}\n"
        f"✅ TP        : {len(tps)} | 🛑 SL: {len(stops)}\n"
        f"🔓 Açık      : {len(state.get('positions', {}))} pozisyon\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💸 <b>Komisyon (Son 288 işlem)</b>\n"
        f"   İşlem sayısı : {len(daily_trades)}\n"
        f"   Ödenen kom.  : <b>-{daily_comm:.4f} USDT</b>\n"
        f"   Net PnL      : {'+' if daily_pnl>=0 else ''}{daily_pnl:.2f} USDT\n"
        f"💸 <b>Toplam Ödenen Komisyon</b>: -{total_comm:.4f} USDT"
    )
    print(f"   📊 24 saatlik rapor gönderildi.")


def send_full_report(state):
    trades    = state.get("closed", [])
    if not trades:
        return
    _, total  = get_balance()
    wins      = [t for t in trades if t["pnl_pct"] > 0]
    losses    = [t for t in trades if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    win_rate  = round(len(wins) / len(trades) * 100, 1)
    avg_win   = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss  = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    tg_send(
        f"🏆 <b>100 İŞLEM TAMAMLANDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Başlangıç : {INITIAL_CAPITAL:.2f} USDT\n"
        f"💰 Bakiye    : {total:.2f} USDT\n"
        f"📈 Toplam PnL: <b>{'+' if total_pnl>0 else ''}{total_pnl:.2f} USDT</b>\n"
        f"🎯 Kazanma   : %{win_rate}\n"
        f"✅ Kârlı     : {len(wins)} | 🔴 Zararlı: {len(losses)}\n"
        f"📊 Ort. Kâr  : %{avg_win} | Ort. Zarar: %{avg_loss}"
    )
    chunk = "📋 <b>Tüm İşlemler:</b>\n━━━━━━━━━━━━━━\n"
    for i, t in enumerate(trades, 1):
        emoji  = "✅" if t["pnl_pct"] > 0 else "🔴"
        dir_e  = "📈" if t.get("direction") == "LONG" else "📉"
        reason = t.get("reason", "")[:8]
        chunk += f"{emoji}{dir_e} #{i} {t.get('symbol',''):12} {'+' if t['pnl_pct']>0 else ''}{t['pnl_pct']:.1f}% | {reason}\n"
        if i % 25 == 0:
            tg_send(chunk)
            chunk = ""
    if chunk:
        tg_send(chunk)


def send_win_prob_report(state):
    from datetime import timedelta
    trades   = state.get("closed", [])
    with_wp  = [t for t in trades if t.get("win_prob") is not None]
    if not with_wp:
        return

    now_ist   = datetime.now(timezone.utc) + timedelta(hours=3)
    yesterday = (now_ist - timedelta(days=1)).strftime("%d.%m.%Y")

    def _ist_date(s):
        try:    return s.split(" ")[0]
        except: return ""

    day_trades = [t for t in with_wp if _ist_date(t.get("exit_time", "")) == yesterday]

    def _build(trades, label):
        if not trades:
            return None
        wins      = [t for t in trades if t.get("pnl_pct", 0) > 0]
        wr        = len(wins) / len(trades) * 100
        total_pnl = sum(t.get("pnl_usdt", 0) for t in trades)
        avg_wp    = sum(t["win_prob"] for t in trades) / len(trades)

        wp_50 = [t for t in trades if t["win_prob"] >= 50]
        wp_55 = [t for t in trades if t["win_prob"] >= 55]
        wp_60 = [t for t in trades if t["win_prob"] >= 60]

        bands = {}
        for t in trades:
            wp  = t["win_prob"]
            low = max(35, min(85, (wp // 5) * 5))
            key = f"{int(low)}-{int(low+5)}"
            bands.setdefault(key, []).append(t)

        lines = [
            f"📊 <b>Win Prob Analiz — {label}</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"🔢 İşlem sayısı : {len(trades)}",
            f"📈 Ort. Tahmin  : %{avg_wp:.1f}",
            f"🎯 Gerçek WR    : %{wr:.1f} ({len(wins)}K / {len(trades)-len(wins)}Z)",
            f"💰 Toplam PnL   : {total_pnl:+.2f} USDT",
            f"━━━━━━━━━━━━━━━━━━━━",
        ]
        for thresh, lst in [(50, wp_50), (55, wp_55), (60, wp_60)]:
            if lst:
                w = len([t for t in lst if t.get("pnl_pct", 0) > 0])
                lines.append(f"📌 wp≥{thresh} ({len(lst)} işlem) → Gerçek WR: %{w/len(lst)*100:.1f}")

        band_stats = []
        for key, b in bands.items():
            if len(b) < 2:
                continue
            w = len([t for t in b if t.get("pnl_pct", 0) > 0])
            band_stats.append((key, len(b), w, w / len(b) * 100))
        band_stats.sort(key=lambda x: -x[3])

        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🏆 <b>En Başarılı Aralıklar (Gerçek WR)</b>")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        for key, cnt, w, wr_b in band_stats[:6]:
            lines.append(f"  %{key} → {w}K/{cnt} işlem (WR %{wr_b:.0f})")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    msg = _build(with_wp, "Tüm Zamanlar")
    if msg:
        tg_send(msg)
    if day_trades:
        msg_day = _build(day_trades, f"Dün ({yesterday})")
        if msg_day:
            tg_send(msg_day)
    print(f"   📊 Win prob raporu gönderildi (tüm: {len(with_wp)}, dün: {len(day_trades)})")


if __name__ == "__main__":
    from crypto_futures_list import FUTURES_SYMBOLS
    pairs = [s + "USDT" for s in FUTURES_SYMBOLS]
    run_scan(pairs)

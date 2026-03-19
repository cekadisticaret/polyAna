#!/usr/bin/env python3
"""
Kripto Paper Trading Sistemi — 15 Dakika
OKX/Binance 15 dakikalık verilerle sanal Long + Short işlem yapar.
Gerçek para kullanılmaz. Her 100 işlemde bir rapor gönderilir, sistem duraksız çalışır.

Strateji:
  EMA 21 / EMA 100
  MACD 8/21/5 — trend dönüşü teyidi
  RSI 14, ADX 22, Hacim x1.5 (spike) + x1.2 (son 12 bar maks)
  ATR SL x2.0 (max %0.8), TP x4.5  →  R:R ≈ 1:2.25
  10x kaldıraç, %8 margin per işlem, max 7 eş zamanlı pozisyon
  Çıkış: SL hit | TP hit | Sinyal tersine döndü
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from telegram_config import BOT_TOKEN, CHAT_ID

def tg_send(text):
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception:
        pass

TRADES_FILE     = os.path.join(os.path.dirname(__file__), "paper_trades.json")
VIRTUAL_CAPITAL = 200.0
LEVERAGE        = 10
STOP_ATR_MULT   = 2.0      # SL = ATR × 2.0 — 15m wick'lerine yeterli alan
TAKE_ATR_MULT   = 4.5      # TP = ATR × 4.5  →  R:R ≈ 1:2.25
MAX_SL_PCT      = 0.8      # Max stop %0.8 fiyat hareketi (10x ile = %8 margin)
MAX_OPEN        = 8        # Aynı anda max 8 pozisyon
COOLDOWN_BARS   = 4        # Kapanış sonrası 4 bar (60 dk) bekleme
MIN_HOLD_BARS   = 2        # Sinyal çıkışı için min 2 bar tutma
POS_SIZE_PCT    = 0.10     # Her işlem: sermayenin %10'u margin
COMMISSION_PCT  = 0.001    # %0.05 giriş + %0.05 çıkış = %0.1 notional
ADX_MIN         = 18   # v3: 22 → 18 (daha fazla sinyal)
USE_HTF_FILTER  = False    # False yapınca 1h EMA21 filtresi devre dışı (eski davranış)
STRUCT_LEN      = 5        # Pivot swing uzunluğu (swing varsa SL/TP swing, yoksa ATR)
MIN_RR_RATIO    = 2.0      # Min R:R — grafikteki gibi, 0.55 gibi kötü R:R'da işlem açma

# Piyasa yönüne göre dinamik kaldıraç
BULL_LONG_LEV   = 12       # Boğa: LONG 12x, SHORT 8x
BULL_SHORT_LEV  = 8
BEAR_LONG_LEV   = 8        # Ayı: LONG 8x, SHORT 12x
BEAR_SHORT_LEV  = 12
NEUT_LONG_LEV   = 10       # Nötr: LONG 10x, SHORT 10x
NEUT_SHORT_LEV  = 10

# Piyasa yönüne göre yön başına max açık pozisyon limiti
# Boğa : 5 LONG, 3 SHORT
# Ayı  : 3 LONG, 5 SHORT
# Nötr : 4 LONG, 4 SHORT (toplam 8)
BULL_MAX_LONG   = 5
BULL_MAX_SHORT  = 3
BEAR_MAX_LONG   = 3
BEAR_MAX_SHORT  = 5
NEUT_MAX_LONG   = 4
NEUT_MAX_SHORT  = 4

# ========== VERİ ==========

def get_klines(symbol, interval="15m", limit=250):
    # Binance önce — paper_trader ve binance_trader aynı veriyi kullansın (borsa farkı = farklı sinyal)
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

    # Fallback: OKX (Binance erişilemezse)
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

# ========== PİYASA YÖN ANALİZİ ==========

def get_market_bias():
    """
    BTC 1h verisiyle genel piyasa yönünü belirler.
    EMA21 > EMA100 ve fiyat > EMA21 → BULL
    EMA21 < EMA100 ve fiyat < EMA21 → BEAR
    Aksi halde → NEUTRAL
    Döner: ("BULL"|"BEAR"|"NEUTRAL", açıklama_str)
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
    gains    = [max(d, 0)    for d in deltas]
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
    last_sl = pl_list[-1][1] if pl_list else None
    return last_sh, last_sl

# ========== ANALİZ ==========

def get_htf_bias(symbol):
    """
    Coin'in kendi 1h verisine göre HTF yön belirler.
    Fiyat > EMA21(1h) → BULL
    Fiyat < EMA21(1h) → BEAR
    """
    try:
        closes_1h, _, _, _ = get_klines(symbol, "1h", 60)
        if not closes_1h or len(closes_1h) < 25:
            return "NEUTRAL"
        ema21_1h = ema(closes_1h, 21)
        if not ema21_1h:
            return "NEUTRAL"
        price_1h = closes_1h[-2]
        e21_1h   = ema21_1h[-1]
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

    rsi_val           = calc_rsi(closes[-20:], 14)
    rsi_prev          = calc_rsi(closes[-21:-1], 14)
    macd_val, sig_val = calc_macd(closes)
    macd_prev, sig_prev = calc_macd(closes[:-1])
    adx_val           = calc_adx(highs, lows, closes)
    atr_val           = calc_atr(highs, lows, closes)

    if any(v is None for v in [rsi_val, rsi_prev, macd_val, sig_val, adx_val, atr_val]):
        return None

    ema21_s  = ema(closes, 21)
    ema100_s = ema(closes, 100)
    if not ema21_s or not ema100_s:
        return None

    ema21  = ema21_s[-1]
    ema100 = ema100_s[-1]
    price  = closes[-2]

    vol_avg     = sum(volumes[-20:]) / 20
    vol_spike   = volumes[-2] > vol_avg * 1.5
    vol_confirm = volumes[-2] > max(volumes[-12:-2]) * 1.2

    dist_pct   = abs((price - ema100) / ema100) * 100
    is_not_far = dist_pct < 5.0   # v2: 3.5 → 5 (daha geniş mesafe)
    is_hot_vol = calc_atr_pct_hot(highs, lows, closes)

    trend_up   = price > ema100
    trend_down = price < ema100

    rsi_rising  = rsi_val > rsi_prev
    rsi_falling = rsi_val < rsi_prev

    # MACD histogram momentum
    hist_now  = macd_val - sig_val
    hist_prev = (macd_prev - sig_prev) if (macd_prev is not None and sig_prev is not None) else hist_now
    macd_hist_growing = hist_now > hist_prev
    macd_hist_falling = hist_now < hist_prev

    # Per-coin HTF bias (1h) — USE_HTF_FILTER=False ise devre dışı
    if USE_HTF_FILTER:
        htf_bias = get_htf_bias(symbol)
        htf_bull = htf_bias in ("BULL", "NEUTRAL")
        htf_bear = htf_bias in ("BEAR", "NEUTRAL")
    else:
        htf_bias = "OFF"
        htf_bull = htf_bear = True

    # v3: MACD histogram şartı kaldırıldı (sadece macd > signal), hacim OR
    vol_ok = vol_spike or vol_confirm
    strong_buy = (
        not is_hot_vol and
        htf_bull and
        trend_up and price > ema21 and
        rsi_val >= 50 and rsi_val <= 65 and rsi_rising and
        macd_val > sig_val and
        adx_val > ADX_MIN and
        vol_ok and
        is_not_far
    )
    strong_sell = (
        not is_hot_vol and
        htf_bear and
        trend_down and price < ema21 and
        rsi_val >= 35 and rsi_val <= 50 and rsi_falling and
        macd_val < sig_val and
        adx_val > ADX_MIN and
        vol_ok and
        is_not_far
    )

    # Çıkış sinyalleri — MACD tek başına değil, RSI onayı da gerekli
    exit_long  = rsi_val > 75 or price < ema100 or (macd_val < sig_val and rsi_val < rsi_prev)
    exit_short = rsi_val < 25 or price > ema100 or (macd_val > sig_val and rsi_val > rsi_prev)

    # Swing pivot (SL/TP için: swing varsa swing, yoksa ATR)
    last_sh, last_sl = get_pivots(highs, lows, STRUCT_LEN, STRUCT_LEN)

    return {
        "symbol":      symbol,
        "price":       round(price, 6),
        "bar_high":    round(highs[-2], 6),
        "bar_low":     round(lows[-2], 6),
        "atr":         round(atr_val, 6),
        "rsi":         rsi_val,
        "adx":         adx_val,
        "ema21":       round(ema21, 6),
        "ema100":      round(ema100, 6),
        "macd_bull":   macd_val > sig_val,
        "vol_spike":   vol_spike,
        "strong_buy":  strong_buy,
        "strong_sell": strong_sell,
        "exit_long":   exit_long,
        "exit_short":  exit_short,
        "is_hot_vol":  is_hot_vol,
        "htf_bias":    htf_bias,
        "last_sh":     round(last_sh, 6) if last_sh else None,
        "last_sl":     round(last_sl, 6) if last_sl else None,
    }

# ========== TRADE YÖNETİMİ ==========

def load_trades():
    for path in [TRADES_FILE, TRADES_FILE + ".bak"]:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("closed") or data.get("open"):
                    return data
            except Exception:
                continue
    return {"open": [], "closed": [], "capital": VIRTUAL_CAPITAL, "bar_counter": {}}

def save_trades(data):
    import shutil
    if os.path.exists(TRADES_FILE):
        shutil.copy2(TRADES_FILE, TRADES_FILE + ".bak")
    with open(TRADES_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def now_str():
    now   = datetime.now(timezone.utc)
    ist_h = (now.hour + 3) % 24
    return f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')} İST"

def build_entry_reason(result, direction):
    """İşlem açılma gerekçesini indikatör değerlerinden üretir."""
    rsi   = result.get("rsi", 0)
    adx   = result.get("adx", 0)
    price = result.get("price", 1)
    ema21 = result.get("ema21", price)
    ema100= result.get("ema100", price)

    parts = []

    # Trend
    if direction == "LONG":
        parts.append(f"EMA21/100 üstünde (trend ↑)")
    else:
        parts.append(f"EMA21/100 altında (trend ↓)")

    # RSI
    if direction == "LONG":
        rsi_label = "güçlü momentum" if rsi >= 63 else "yükselen momentum"
        parts.append(f"RSI {round(rsi,1)} — {rsi_label}")
    else:
        rsi_label = "güçlü baskı" if rsi <= 37 else "düşen momentum"
        parts.append(f"RSI {round(rsi,1)} — {rsi_label}")

    # ADX
    adx_label = "çok güçlü trend" if adx >= 40 else "güçlü trend" if adx >= 30 else "trend başlangıcı"
    parts.append(f"ADX {round(adx,1)} — {adx_label}")

    # MACD
    if result.get("macd_bull"):
        parts.append("MACD sinyal üstünde")
    else:
        parts.append("MACD sinyal altında")

    # Hacim
    if result.get("vol_spike"):
        parts.append("hacim patlaması ✅")

    return parts


def calc_win_prob(result, direction, sl_pct, tp_pct):
    """
    0-100 arası tahmini başarı olasılığı.
    RSI gücü, ADX, MACD mesafesi, hacim ve R:R oranına göre hesaplanır.
    Minimum break-even probability = 1 / (1 + R:R) — bu tabanın üstüne eklenir.
    """
    rsi   = result.get("rsi", 50)
    adx   = result.get("adx", 0)
    price = result.get("price", 1)
    ema21 = result.get("ema21", price)
    ema100= result.get("ema100", price)

    # Break-even probability: R:R oranından türetilir
    rr = tp_pct / sl_pct if sl_pct > 0 else 1.0
    base_prob = round(1 / (1 + rr) * 100, 1)  # örn. R:R=2 → %33.3 base

    bonus = 0

    # RSI gücü (ideal bölge: 58-68 LONG, 32-42 SHORT)
    if direction == "LONG":
        if 58 <= rsi <= 68:   bonus += 15
        elif 55 <= rsi < 58:  bonus += 8
        elif rsi > 68:        bonus += 4   # aşırı alım bölgesi, daha riskli
    else:
        if 32 <= rsi <= 42:   bonus += 15
        elif 42 < rsi <= 45:  bonus += 8
        elif rsi < 32:        bonus += 4

    # ADX trend gücü
    if adx >= 40:   bonus += 15
    elif adx >= 30: bonus += 10
    elif adx >= 22: bonus += 5

    # EMA21 mesafesi — fiyat EMA21'e yakınsa daha temiz giriş
    ema21_dist = abs(price - ema21) / ema21 * 100 if ema21 else 99
    if ema21_dist < 0.5:   bonus += 10
    elif ema21_dist < 1.5: bonus += 6
    elif ema21_dist < 3.0: bonus += 3

    # EMA100 mesafesi — makro trende ne kadar yakın
    ema100_dist = abs(price - ema100) / ema100 * 100 if ema100 else 99
    if ema100_dist < 1.0:   bonus += 8
    elif ema100_dist < 2.5: bonus += 4

    # Hacim onayı
    if result.get("vol_spike"):  bonus += 7

    prob = min(round(base_prob + bonus), 89)   # max %89 — kesinlik yok
    prob = max(prob, 35)                        # min %35 — zaten filtreden geçti
    return prob, round(rr, 2)


def open_position(data, symbol, direction, price, atr, result=None, bias="NEUTRAL"):
    if any(p["symbol"] == symbol for p in data["open"]):
        return False
    if len(data["open"]) >= MAX_OPEN:
        return False
    last_bar = data.get("bar_counter", {}).get(symbol, -999)
    if data.get("total_bars", 0) - last_bar < COOLDOWN_BARS:
        return False

    # Piyasa yönüne göre kaldıraç ve yön limiti kontrolü
    if bias == "BULL":
        lev       = BULL_LONG_LEV  if direction == "LONG" else BULL_SHORT_LEV
        max_long  = BULL_MAX_LONG
        max_short = BULL_MAX_SHORT
    elif bias == "BEAR":
        lev       = BEAR_LONG_LEV  if direction == "LONG" else BEAR_SHORT_LEV
        max_long  = BEAR_MAX_LONG
        max_short = BEAR_MAX_SHORT
    else:
        lev       = NEUT_LONG_LEV if direction == "LONG" else NEUT_SHORT_LEV
        max_long  = NEUT_MAX_LONG
        max_short = NEUT_MAX_SHORT

    # Yön limitini aş → pozisyon açma
    open_longs  = sum(1 for p in data["open"] if p["direction"] == "LONG")
    open_shorts = sum(1 for p in data["open"] if p["direction"] == "SHORT")
    if direction == "LONG"  and open_longs  >= max_long:
        return False
    if direction == "SHORT" and open_shorts >= max_short:
        return False

    # Margin her zaman toplam sermayenin %10'u (kalan değil) — 170$ → 17$, binance_trader ile uyumlu
    size = round(data["capital"] * POS_SIZE_PCT, 2)

    # Swing varsa swing, yoksa ATR
    last_sh = (result or {}).get("last_sh")
    last_sl = (result or {}).get("last_sl")

    if direction == "LONG":
        atr_sl = max(price - atr * STOP_ATR_MULT, price * (1 - MAX_SL_PCT/100))
        atr_tp = price + atr * TAKE_ATR_MULT
        if last_sl and last_sl < price:
            sl = round(max(last_sl, price * (1 - MAX_SL_PCT/100)), 6)
        else:
            sl = round(atr_sl, 6)
        if last_sh and last_sh > price:
            tp = round(last_sh, 6)
        else:
            tp = round(atr_tp, 6)
    else:
        atr_sl = min(price + atr * STOP_ATR_MULT, price * (1 + MAX_SL_PCT/100))
        atr_tp = price - atr * TAKE_ATR_MULT
        if last_sh and last_sh > price:
            sl = round(min(last_sh, price * (1 + MAX_SL_PCT/100)), 6)
        else:
            sl = round(atr_sl, 6)
        if last_sl and last_sl < price:
            tp = round(last_sl, 6)
        else:
            tp = round(atr_tp, 6)

    # Binance ile uyumlu: geçersiz SL/TP'de işlem açma (düşük coinlerde negatif olabiliyor)
    if sl <= 0 or tp <= 0:
        return False

    atr_pct = round((atr / price) * 100, 3) if price else 0
    sl_pct  = round(abs(price - sl) / price * 100, 3)
    tp_pct  = round(abs(tp - price) / price * 100, 3)

    win_prob, rr_ratio = calc_win_prob(result or {}, direction, sl_pct, tp_pct)
    if rr_ratio < MIN_RR_RATIO:
        return False  # R:R kötüyse (örn. spike tepesinde) işlem açma
    prob_filled = min(6, max(0, round(win_prob * 6 / 100)))
    prob_bar    = "⬜️" * prob_filled + "⬛️" * (6 - prob_filled)
    prob_emoji  = "🟢" if win_prob >= 60 else "🟡" if win_prob >= 45 else "🔴"
    reasons    = build_entry_reason(result or {}, direction)
    reason_str = "\n".join(f"   • {r}" for r in reasons)

    htf_bias_val = (result or {}).get("htf_bias", bias)
    bias_emoji = "🐂" if htf_bias_val == "BULL" else "🐻" if htf_bias_val == "BEAR" else "⚖️"
    bias_label = "Boğa (1h)" if htf_bias_val == "BULL" else "Ayı (1h)" if htf_bias_val == "BEAR" else ("HTF kapalı" if htf_bias_val == "OFF" else "Nötr (1h)")

    data["open"].append({
        "symbol":       symbol,
        "direction":    direction,
        "entry_price":  price,
        "size_usdt":    size,
        "sl":           sl,
        "tp":           tp,
        "open_time":    now_str(),
        "open_bar":     data.get("total_bars", 0),
        "entry_atr":    round(atr, 6),
        "leverage":     lev,
        "win_prob":     win_prob,
        "entry_reason": reasons,
        "market_bias":  bias,
    })
    emoji = "📈" if direction == "LONG" else "📉"
    print(f"  {emoji} {direction}: {symbol} @ {price} | SL:{sl} ({sl_pct}%) | TP:{tp} ({tp_pct}%) | Başarı:%{win_prob} | {bias_label} {lev}x")
    tg_send(
        f"{emoji} <b>Yeni İşlem Açıldı #{len(data['open'])}</b>\n"
        f"<b>{direction}</b> | <b>{symbol}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎯 Giriş : {price}\n"
        f"🛑 SL : {sl} (-%{sl_pct})\n"
        f"✅ TP : {tp} (+%{tp_pct})\n"
        f"📉 ATR : {atr} (%{atr_pct})\n"
        f"━━━━━━━━━━━━━━\n"
        f"{prob_emoji} <b>Başarı Tahmini : %{win_prob}</b>\n"
        f"{prob_bar} R:R = 1:{rr_ratio}\n"
        f"━━━━━━━━━━━━━━\n"
        f"⚖️ Piyasa: {bias_label} -> {lev}x kaldıraç\n"
        f"Margin: {size} USDT (Max: {max_long}L / {max_short}S)\n"
        f"━━━━━━━━━━━━━━\n"
        f"📋 <b>Neden açtım?</b>\n"
        f"{reason_str}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Sermaye: {data['capital']:.2f} USDT\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    )
    save_trades(data)
    return True

def close_position(data, pos, price, reason):
    if pos["direction"] == "LONG":
        price_chg_pct = (price - pos["entry_price"]) / pos["entry_price"] * 100
    else:
        price_chg_pct = (pos["entry_price"] - price) / pos["entry_price"] * 100

    lev        = pos.get("leverage", LEVERAGE)
    pnl_pct    = round(price_chg_pct * lev, 2)
    notional   = pos["size_usdt"] * lev
    commission = round(notional * COMMISSION_PCT, 4)
    pnl_usdt   = round(pos["size_usdt"] * pnl_pct / 100 - commission, 2)
    data["capital"] = round(data["capital"] + pnl_usdt, 2)

    trade = {
        **pos,
        "exit_price": price,
        "exit_time":  now_str(),
        "reason":     reason,
        "pnl_pct":    pnl_pct,
        "pnl_usdt":   pnl_usdt,
        "commission":  commission,
        "trade_no":   len(data["closed"]) + 1,
    }
    data["closed"].append(trade)
    data["open"]     = [p for p in data["open"] if p["symbol"] != pos["symbol"]]
    data.setdefault("bar_counter", {})[pos["symbol"]] = data.get("total_bars", 0)

    emoji     = "✅" if pnl_pct > 0 else "🔴"
    dir_emoji = "📈" if pos["direction"] == "LONG" else "📉"
    print(f"  {emoji} KAPANDI [{pos['direction']}]: {pos['symbol']} @ {price} | {'+' if pnl_pct>0 else ''}{pnl_pct}% | {reason}")

    entry_atr = pos.get("entry_atr")
    atr_line  = ""
    if entry_atr and pos["entry_price"]:
        atr_pct  = round((entry_atr / pos["entry_price"]) * 100, 3)
        atr_line = f"📉 ATR     : {entry_atr} (%{atr_pct})\n"

    held_bars = data.get("total_bars", 0) - pos.get("open_bar", data.get("total_bars", 0))
    held_min  = held_bars * 15
    if held_min < 60:
        duration_str = f"{held_min} dk"
    else:
        duration_str = f"{held_min // 60}s {held_min % 60}dk" if held_min % 60 else f"{held_min // 60} saat"

    tg_send(
        f"{emoji} <b>İşlem Kapandı #{trade['trade_no']}</b>\n"
        f"{dir_emoji} {pos['direction']} | <b>{pos['symbol']}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🕐 Açılış : {pos.get('open_time', '-')}\n"
        f"⏱ Süre   : {duration_str}\n"
        f"🎯 Giriş  : {pos['entry_price']}\n"
        f"🏁 Çıkış  : {price}\n"
        f"📊 Sonuç  : <b>{'+' if pnl_pct>0 else ''}{pnl_pct}%</b> ({'+' if pnl_usdt>0 else ''}{pnl_usdt:.3f} USDT) — {lev}x\n"
        f"💸 Komisyon: -{commission:.3f} USDT\n"
        f"{atr_line}"
        f"💡 Neden  : {reason}\n"
        f"💰 Sermaye: {data['capital']:.2f} USDT\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    )
    save_trades(data)
    return trade

# ========== ANA DÖNGÜ ==========

def run_scan(symbols):
    data = load_trades()
    data.setdefault("total_bars", 0)

    now_utc    = datetime.now(timezone.utc)
    is_new_15m = now_utc.minute % 15 <= 4

    if is_new_15m:
        data["total_bars"] += 1

    cur_bar = data["total_bars"]
    print(f"\n🤖 Paper Trader 15m | {now_str()}")
    print(f"   İşlem: {len(data['closed'])} | Sermaye: {data['capital']:.2f} USDT | Açık: {len(data['open'])}")

    if is_new_15m:
        scan_start = datetime.now(timezone.utc)

        # Açık pozisyonlar dahil tüm sembolleri tek seferde tara
        scan_set = list(set(symbols) | {p["symbol"] for p in data["open"]})
        with ThreadPoolExecutor(max_workers=30) as ex:
            futures = {ex.submit(analyze, sym, "15m"): sym for sym in scan_set}
            results = {}
            for f in as_completed(futures):
                sym = futures[f]
                try:
                    results[sym] = f.result()
                except Exception:
                    results[sym] = None

        elapsed = round((datetime.now(timezone.utc) - scan_start).total_seconds(), 1)
        print(f"   🔍 Tarama tamamlandı: {elapsed}s")

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

        # ── Pozisyon Yönetimi: SL / TP / Çıkış Sinyali ──
        for pos in list(data["open"]):
            pd = results.get(pos["symbol"])
            if not pd:
                continue

            b_high    = pd["bar_high"]
            b_low     = pd["bar_low"]
            held      = cur_bar - pos.get("open_bar", cur_bar)
            entry_atr = pos.get("entry_atr", pd["atr"])

            open_set = {p["symbol"] for p in data["open"]}
            if pos["symbol"] not in open_set:
                continue

            # ── SL Kontrolü ──
            if pos["direction"] == "LONG" and b_low <= pos["sl"]:
                close_position(data, pos, pos["sl"], "STOP LOSS")
                continue
            elif pos["direction"] == "SHORT" and b_high >= pos["sl"]:
                close_position(data, pos, pos["sl"], "STOP LOSS")
                continue

            # ── TP Kontrolü ──
            open_set = {p["symbol"] for p in data["open"]}
            if pos["symbol"] in open_set:
                if pos["direction"] == "LONG" and b_high >= pos["tp"]:
                    close_position(data, pos, pos["tp"], "TAKE PROFIT")
                    continue
                elif pos["direction"] == "SHORT" and b_low <= pos["tp"]:
                    close_position(data, pos, pos["tp"], "TAKE PROFIT")
                    continue

            # ── Çıkış Sinyali ──
            # Kârdaysa → sadece SL/TP kapatır, sinyal yoksayılır (ATR'ye bırak)
            # Zarardaysa → sinyal gelince anında kapat
            open_set = {p["symbol"] for p in data["open"]}
            if pos["symbol"] in open_set:
                in_profit = (pd["price"] > pos["entry_price"]) if pos["direction"] == "LONG" \
                            else (pd["price"] < pos["entry_price"])
                if not in_profit and held >= MIN_HOLD_BARS:
                    exit_triggered = (pos["direction"] == "LONG" and pd["exit_long"]) or \
                                     (pos["direction"] == "SHORT" and pd["exit_short"])
                    if exit_triggered:
                        close_position(data, pos, pd["price"], _exit_reason(pos["direction"], pd))

        # ── Yeni Giriş Sinyali ──
        if len(data["open"]) < MAX_OPEN:
            found = 0
            for symbol in symbols:
                if len(data["open"]) >= MAX_OPEN:
                    break
                result = results.get(symbol)
                if not result:
                    continue
                # HTF bias zaten analyze() içinde kontrol ediliyor; open_position'a NEUTRAL geçiyoruz
                if result["strong_buy"]:
                    if open_position(data, symbol, "LONG", result["price"], result["atr"], result, "NEUTRAL"):
                        found += 1
                elif result["strong_sell"]:
                    if open_position(data, symbol, "SHORT", result["price"], result["atr"], result, "NEUTRAL"):
                        found += 1
            if found == 0:
                print(f"   ℹ️  Bu turda sinyal bulunamadı.")
                # Saat başı (xx:00) Telegram bildirimi
                if now_utc.minute == 0:
                    tg_send(
                        f"🔍 <b>Sinyal Taraması</b> | {now_str()}\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"ℹ️ Bu saatte uygun işlem bulunamadı.\n"
                        f"💰 Sermaye : {data['capital']:.2f} USDT\n"
                        f"🔓 Açık    : {len(data['open'])} pozisyon\n"
                        f"🔢 Toplam  : {len(data['closed'])} işlem"
                    )

    save_trades(data)

    if len(data["closed"]) % 100 == 0 and len(data["closed"]) > 0:
        print(f"\n🎯 {len(data['closed'])} İŞLEM RAPORU GÖNDERİLİYOR...")
        analyze_performance(data)
        send_full_report(data)

    if is_new_15m and cur_bar % 288 == 0 and cur_bar > 0:
        send_status_report(data)

    return data

# ========== RAPORLAR ==========

def analyze_performance(data):
    trades    = data["closed"]
    if not trades:
        return
    wins      = [t for t in trades if t["pnl_pct"] > 0]
    losses    = [t for t in trades if t["pnl_pct"] <= 0]
    longs     = [t for t in trades if t.get("direction") == "LONG"]
    shorts    = [t for t in trades if t.get("direction") == "SHORT"]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    win_rate  = round(len(wins) / len(trades) * 100, 1)
    avg_win   = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss  = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    print(f"""
{'='*50}
📊 PAPER TRADING ANALİZİ — {len(trades)} İşlem
{'='*50}
💰 Başlangıç : {VIRTUAL_CAPITAL} USDT
💰 Son Durum : {data['capital']:.2f} USDT
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
            "starting_capital": VIRTUAL_CAPITAL, "final_capital": data["capital"],
            "avg_win_pct": avg_win, "avg_loss_pct": avg_loss,
            "long_count": len(longs), "short_count": len(shorts),
        },
        "trades": trades
    }
    with open(os.path.join(os.path.dirname(__file__), "paper_report.json"), "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

def send_status_report(data):
    trades = data["closed"]
    if not trades:
        return
    wins       = [t for t in trades if t["pnl_pct"] > 0]
    losses     = [t for t in trades if t["pnl_pct"] < 0]
    stops      = [t for t in trades if t["reason"] == "STOP LOSS"]
    tps        = [t for t in trades if t["reason"] == "TAKE PROFIT"]
    longs      = [t for t in trades if t.get("direction") == "LONG"]
    shorts     = [t for t in trades if t.get("direction") == "SHORT"]
    total_pnl  = sum(t["pnl_usdt"] for t in trades)
    total_comm = round(sum(t.get("commission", 0) for t in trades), 4)
    win_rate   = round(len(wins) / len(trades) * 100, 1)
    avg_win    = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss   = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    roi        = round((data["capital"] - VIRTUAL_CAPITAL) / VIRTUAL_CAPITAL * 100, 2)
    recent     = trades[-20:] if len(trades) >= 20 else trades
    rec_wr     = round(len([t for t in recent if t["pnl_pct"] > 0]) / len(recent) * 100, 1)
    trend      = "📈" if rec_wr > win_rate else "📉"
    cap_emoji  = "💚" if data["capital"] >= VIRTUAL_CAPITAL else "🔴"
    # Son 24 saatte kapanan işlemler (288 bar = 24 saat × 12 bar/saat)
    daily_trades = trades[-288:] if len(trades) >= 288 else trades
    daily_comm   = round(sum(t.get("commission", 0) for t in daily_trades), 4)
    daily_pnl    = round(sum(t["pnl_usdt"] for t in daily_trades), 2)
    tg_send(
        f"📊 <b>Günlük Rapor (24s)</b> | {now_str()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{cap_emoji} Sermaye  : <b>{data['capital']:.2f} USDT</b> ({'+' if roi>=0 else ''}{roi}%)\n"
        f"📈 Toplam PnL: <b>{'+' if total_pnl>=0 else ''}{total_pnl:.2f} USDT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Win Rate  : <b>%{win_rate}</b> ({len(wins)}K / {len(losses)}Z)\n"
        f"{trend} Son 20 işlem: <b>%{rec_wr}</b>\n"
        f"📊 Ort. Kâr  : %{avg_win} | Ort. Zarar: %{avg_loss}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 Toplam    : {len(trades)} işlem\n"
        f"📈 Long      : {len(longs)} | 📉 Short: {len(shorts)}\n"
        f"✅ TP        : {len(tps)} | 🛑 SL: {len(stops)}\n"
        f"🔓 Açık      : {len(data['open'])} pozisyon\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💸 <b>Komisyon (Son 24s)</b>\n"
        f"   İşlem sayısı : {len(daily_trades)}\n"
        f"   Ödenen kom.  : <b>-{daily_comm:.4f} USDT</b>\n"
        f"   Net PnL (24s) : {'+' if daily_pnl>=0 else ''}{daily_pnl:.2f} USDT\n"
        f"💸 <b>Toplam Ödenen Komisyon</b>: -{total_comm:.4f} USDT"
    )
    print(f"   📊 24 saatlik rapor gönderildi.")

def send_full_report(data):
    trades    = data["closed"]
    wins      = [t for t in trades if t["pnl_pct"] > 0]
    losses    = [t for t in trades if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    win_rate  = round(len(wins) / len(trades) * 100, 1)
    avg_win   = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss  = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    tg_send(
        f"🏆 <b>100 İŞLEM TAMAMLANDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Başlangıç : {VIRTUAL_CAPITAL:.2f} USDT\n"
        f"💰 Son Durum : {data['capital']:.2f} USDT\n"
        f"📈 Toplam PnL: <b>{'+' if total_pnl>0 else ''}{total_pnl:.2f} USDT</b>\n"
        f"🎯 Kazanma   : %{win_rate}\n"
        f"✅ Kârlı     : {len(wins)} | 🔴 Zararlı: {len(losses)}\n"
        f"📊 Ort. Kâr  : %{avg_win} | Ort. Zarar: %{avg_loss}"
    )
    chunk = "📋 <b>Tüm İşlemler:</b>\n━━━━━━━━━━━━━━\n"
    for i, t in enumerate(trades, 1):
        emoji = "✅" if t["pnl_pct"] > 0 else "🔴"
        dir_e = "📈" if t.get("direction") == "LONG" else "📉"
        chunk += f"{emoji}{dir_e} #{i} {t['symbol']:12} {'+' if t['pnl_pct']>0 else ''}{t['pnl_pct']:.1f}% | {t['reason'][:8]}\n"
        if i % 25 == 0:
            tg_send(chunk)
            chunk = ""
    if chunk:
        tg_send(chunk)


if __name__ == "__main__":
    from crypto_futures_list import FUTURES_SYMBOLS
    pairs = [s + "USDT" for s in FUTURES_SYMBOLS]
    run_scan(pairs)

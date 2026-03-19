#!/usr/bin/env python3
"""
Kripto Scalp Paper Trading — 5m Sinyal + 15m Çıkış Yönetimi
5 dakikalık barlarla giriş sinyali üretir, 15 dakikalık barlarla çıkış kararı verir.
Gerçek para kullanılmaz.

Strateji:
  EMA 21 / 55 (5m trend filtresi: ~105dk hızlı, ~275dk yavaş)
  MACD 8/21/5 — çıkış için RSI yön onayı zorunlu
  RSI 14, ADX 22, Hacim x1.2
  ATR SL x3.5, TP x8.5, Max SL %0.7
  Cooldown: 20 bar (100 dk) | Min tutma: 6 bar (30 dk)
  Giriş: 5m analiz | Çıkış sinyali: 15m analiz
  Max 1 yeni pozisyon/tarama | Min skor: 62
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

BOT_TOKEN = "8251344465:AAH_72cBn4wfZ302iiAw8L0Tn1-3BPlkHE0"
CHAT_ID   = "830754964"

def tg_send(text):
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception:
        pass

TRADES_FILE     = os.path.join(os.path.dirname(__file__), "scalp_trades.json")
VIRTUAL_CAPITAL = 200.0
LEVERAGE        = 10
STOP_ATR_MULT    = 3.5      # 5m barlarda daha geniş tolerans
TAKE_ATR_MULT    = 8.5      # R:R = 1:2.4 korunuyor
MAX_SL_PCT       = 0.7      # Max %0.7 stop (10x ile = %7 margin)
MAX_OPEN         = 3        # Senkronize kayıpları önlemek için azaltıldı
COOLDOWN_BARS    = 20       # 20 × 5m = 100 dk soğuma süresi
MIN_HOLD_BARS    = 6        # 6 × 5m = 30 dk min tutma
POS_SIZE_PCT     = 0.10
TRAIL_ATR_MULT   = 3.5      # SL erken sıkışmasın — ATR×1.0'a değil ATR×3.5'e yakın kalsın
COMMISSION_PCT   = 0.001    # %0.05 giriş + %0.05 çıkış
ADX_MIN          = 22       # Daha güçlü trend kalitesi
MIN_ENTRY_SCORE  = 62       # Düşük kalite girişleri engelle
MAX_NEW_PER_SCAN = 1        # Her taramada max 1 yeni pozisyon (senkronize giriş önlenir)

SCALP_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "MATICUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT",
    "XLMUSDT", "NEARUSDT", "FTMUSDT", "SANDUSDT", "MANAUSDT",
    "AAVEUSDT", "TRXUSDT", "OPUSDT", "ARBUSDT", "APTUSDT",
    "SUIUSDT", "INJUSDT", "SEIUSDT", "WLDUSDT", "FETUSDT",
    "GRTUSDT", "MKRUSDT", "LDOUSDT", "STXUSDT", "GALAUSDT",
    "APEUSDT", "IMXUSDT", "RUNEUSDT", "THETAUSDT", "FILUSDT",
    "ICPUSDT", "HBARUSDT", "TIAUSDT", "RENDERUSDT", "SNXUSDT",
    "ENAUSDT", "JUPUSDT", "PYTHUSDT", "ONDOUSDT", "JTOUSDT",
]

# ========== VERİ ==========

def get_klines(symbol, interval="1m", limit=200):
    base       = symbol.replace("USDT", "")
    okx_symbol = f"{base}-USDT-SWAP"
    okx_bar    = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H"}.get(interval, interval)
    okx_url    = (f"https://www.okx.com/api/v5/market/candles"
                  f"?instId={okx_symbol}&bar={okx_bar}&limit={limit}")
    try:
        req = urllib.request.Request(okx_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("code") != "0" or not data.get("data"):
            raise Exception("OKX no data")
        candles = list(reversed(data["data"]))
        closes  = [float(d[4]) for d in candles]
        volumes = [float(d[5]) for d in candles]
        highs   = [float(d[2]) for d in candles]
        lows    = [float(d[3]) for d in candles]
        return closes, volumes, highs, lows
    except Exception:
        pass

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
        return None, None, None, None

def get_price_data(symbol):
    """5m barlarda son kapanmış barın high/low/close + ATR — SL/TP kontrolü için"""
    closes, volumes, highs, lows = get_klines(symbol, "5m", 30)
    if not closes or len(closes) < 15:
        return None
    atr = calc_atr(highs, lows, closes)
    return {
        "price":    closes[-2],
        "bar_high": highs[-2],
        "bar_low":  lows[-2],
        "atr":      round(atr, 6) if atr else None,
    }

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

def calc_atr_pct_hot(highs, lows, closes, ref_len=60, hot_mult=1.8):
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

# ========== SKOR ==========

def calc_entry_score(r, direction):
    """0-100 sinyal uyum skoru: RSI gücü, ADX gücü, EMA55 mesafesi, hacim."""
    if direction == "LONG":
        rsi_pts = min(30, max(0, (r["rsi"] - 57) / 23 * 30))
    else:
        rsi_pts = min(30, max(0, (43 - r["rsi"]) / 23 * 30))
    adx_pts  = min(30, max(0, (r["adx"] - ADX_MIN) / 30 * 30))
    dist_pct = abs((r["price"] - r["ema55"]) / r["ema55"]) * 100
    dist_pts = max(0, (5.0 - dist_pct) / 5.0 * 20)
    vol_pts  = 20 if r["vol_spike"] else 0
    return round(rsi_pts + adx_pts + dist_pts + vol_pts)

# ========== ANALİZ ==========

def analyze(symbol, interval="1m"):
    closes, volumes, highs, lows = get_klines(symbol, interval, 200)
    if not closes or len(closes) < 80:
        return None

    rsi_val        = calc_rsi(closes[-20:], 14)
    rsi_prev       = calc_rsi(closes[-21:-1], 14)
    macd_val, sig_val = calc_macd(closes)
    adx_val        = calc_adx(highs, lows, closes)
    atr_val        = calc_atr(highs, lows, closes)

    if any(v is None for v in [rsi_val, rsi_prev, macd_val, sig_val, adx_val, atr_val]):
        return None

    ema21_s  = ema(closes, 21)
    ema55_s  = ema(closes, 55)
    ema100_s = ema(closes, 100)
    if not ema21_s or not ema55_s or not ema100_s:
        return None

    ema21  = ema21_s[-1]
    ema55  = ema55_s[-1]
    ema100 = ema100_s[-1]
    price  = closes[-2]

    vol_avg   = sum(volumes[-20:]) / 20
    vol_spike = volumes[-2] > vol_avg * 1.2

    dist_pct   = abs((price - ema55) / ema55) * 100
    is_not_far = dist_pct < 5.0
    is_hot_vol = calc_atr_pct_hot(highs, lows, closes)

    # EMA100 makro trend filtresi: LONG için fiyat EMA100 üstünde olmalı
    macro_bull = price > ema100
    macro_bear = price < ema100

    trend_up   = price > ema55
    trend_down = price < ema55

    rsi_rising  = rsi_val > rsi_prev
    rsi_falling = rsi_val < rsi_prev

    # 5m'de 30 bar = 150 dk referans
    vol_confirm = (volumes[-2] > max(volumes[-30:-2]) * 1.2
                   if len(volumes) >= 30 else False)

    strong_buy = (
        not is_hot_vol and macro_bull and trend_up and price > ema21 and
        rsi_val > 58 and rsi_rising and
        vol_spike and vol_confirm and adx_val > ADX_MIN and macd_val > sig_val and is_not_far
    )
    strong_sell = (
        not is_hot_vol and macro_bear and trend_down and price < ema21 and
        rsi_val < 42 and rsi_falling and
        vol_spike and vol_confirm and adx_val > ADX_MIN and macd_val < sig_val and is_not_far
    )

    exit_long  = rsi_val > 75 or not trend_up  or (macd_val < sig_val and rsi_val < rsi_prev)
    exit_short = rsi_val < 25 or not trend_down or (macd_val > sig_val and rsi_val > rsi_prev)

    return {
        "symbol":      symbol,
        "price":       round(price, 6),
        "bar_high":    round(highs[-2], 6),
        "bar_low":     round(lows[-2], 6),
        "atr":         round(atr_val, 6),
        "rsi":         rsi_val,
        "adx":         adx_val,
        "ema21":       round(ema21, 6),
        "ema55":       round(ema55, 6),
        "ema100":      round(ema100, 6),
        "macd_bull":   macd_val > sig_val,
        "vol_spike":   vol_spike,
        "strong_buy":  strong_buy,
        "strong_sell": strong_sell,
        "exit_long":   exit_long,
        "exit_short":  exit_short,
        "is_hot_vol":  is_hot_vol,
    }

# ========== TRADE YÖNETİMİ ==========

def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            return json.load(f)
    return {"open": [], "closed": [], "capital": VIRTUAL_CAPITAL, "bar_counter": {}}

def save_trades(data):
    with open(TRADES_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def now_str():
    now   = datetime.now(timezone.utc)
    ist_h = (now.hour + 3) % 24
    return f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')} İST"

def open_position(data, symbol, direction, price, atr, result=None):
    if any(p["symbol"] == symbol for p in data["open"]):
        return False
    if len(data["open"]) >= MAX_OPEN:
        return False
    last_bar = data.get("bar_counter", {}).get(symbol, -999)
    if data.get("total_bars", 0) - last_bar < COOLDOWN_BARS:
        return False

    size = round(data["capital"] * POS_SIZE_PCT, 2)
    if direction == "LONG":
        sl = round(max(price - atr * STOP_ATR_MULT, price * (1 - MAX_SL_PCT/100)), 6)
        tp = round(price + atr * TAKE_ATR_MULT, 6)
    else:
        sl = round(min(price + atr * STOP_ATR_MULT, price * (1 + MAX_SL_PCT/100)), 6)
        tp = round(price - atr * TAKE_ATR_MULT, 6)

    atr_pct     = round((atr / price) * 100, 3) if price else 0
    score       = calc_entry_score(result, direction) if result else 0
    score_bar   = "█" * (score // 10) + "░" * (10 - score // 10)
    score_label = "🔥 Güçlü" if score >= 75 else "✅ İyi" if score >= 55 else "⚠️ Orta"
    lev         = 15 if score >= 60 else LEVERAGE
    lev_tag     = "🚀 15x" if lev == 15 else "10x"

    data["open"].append({
        "symbol":      symbol,
        "direction":   direction,
        "entry_price": price,
        "size_usdt":   size,
        "sl":          sl,
        "tp":          tp,
        "open_time":   now_str(),
        "open_bar":    data.get("total_bars", 0),
        "best_price":  price,
        "entry_atr":   round(atr, 6),
        "entry_score": score,
        "leverage":    lev,
    })
    emoji     = "📈" if direction == "LONG" else "📉"
    dir_label = "alıma" if direction == "LONG" else "satışa"
    print(f"  {emoji} {direction}: {symbol} @ {price} | SL:{sl} | TP:{tp} | Skor:%{score} | {lev}x")
    tg_send(
        f"{emoji} <b>Scalp İşlem Açıldı #{len(data['open'])}</b>\n"
        f"{'📈' if direction == 'LONG' else '📉'} <b>{direction}</b> | <b>{symbol}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎯 Giriş  : {price}\n"
        f"🛑 SL     : {sl}\n"
        f"✅ TP     : {tp}\n"
        f"📉 ATR    : {atr} (%{atr_pct})\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 Sinyal : {score_bar} %{score} {dir_label} uygun {score_label}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Margin : {size} USDT (%{round(POS_SIZE_PCT*100)} × {lev_tag})\n"
        f"💰 Sermaye: {data['capital']:.2f} USDT\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    )
    return True

def close_position(data, pos, price, reason, cur_atr=None):
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
        "trade_no":   len(data["closed"]) + 1,
    }
    data["closed"].append(trade)
    data["open"]     = [p for p in data["open"] if p["symbol"] != pos["symbol"]]
    data.setdefault("bar_counter", {})[pos["symbol"]] = data.get("total_bars", 0)

    emoji     = "✅" if pnl_pct > 0 else "🔴"
    dir_emoji = "📈" if pos["direction"] == "LONG" else "📉"
    lev_tag   = f"🚀{lev}x" if lev > LEVERAGE else f"{lev}x"
    print(f"  {emoji} KAPANDI [{pos['direction']}]: {pos['symbol']} @ {price} | {'+' if pnl_pct>0 else ''}{pnl_pct}% ({lev_tag}) | {reason}")

    entry_atr   = pos.get("entry_atr", cur_atr)
    trail_level = pos.get("trail_level", 0)

    atr_line   = ""
    if entry_atr:
        atr_pct  = round((entry_atr / pos["entry_price"]) * 100, 3) if pos["entry_price"] else 0
        cur_line = f" → {cur_atr}" if cur_atr and cur_atr != entry_atr else ""
        atr_line = f"📉 ATR     : {entry_atr}{cur_line} (%{atr_pct})\n"

    best_line  = ""
    if pos.get("best_price") and pos["best_price"] != pos["entry_price"]:
        best_label = "En Yüksek" if pos["direction"] == "LONG" else "En Düşük"
        best_line  = f"🏆 {best_label}: {pos['best_price']}\n"

    trail_line = ""
    if reason == "STOP LOSS":
        if trail_level == 0:
            trail_line = "🔴 ATR Trail: Seviye 0 — kâra geçmeden stop\n"
        else:
            trail_line = f"🛡 ATR Trail: <b>Seviye {trail_level}'de stop</b>\n"

    tg_send(
        f"{emoji} <b>Scalp Kapandı #{trade['trade_no']}</b>\n"
        f"{dir_emoji} {pos['direction']} | <b>{pos['symbol']}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎯 Giriş  : {pos['entry_price']}\n"
        f"🏁 Çıkış  : {price}\n"
        f"{best_line}"
        f"📊 Sonuç  : <b>{'+' if pnl_pct>0 else ''}{pnl_pct}%</b> ({'+' if pnl_usdt>0 else ''}{pnl_usdt:.3f} USDT) — {lev}x\n"
        f"💸 Komisyon: -{commission:.3f} USDT\n"
        f"{atr_line}"
        f"{trail_line}"
        f"💡 Neden  : {reason}\n"
        f"💰 Sermaye: {data['capital']:.2f} USDT\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    )
    return trade

# ========== ANA DÖNGÜ ==========

def run_scan():
    data = load_trades()
    data.setdefault("total_bars", 0)
    data["total_bars"] += 1   # Cron * * * * * → her dakika yeni 1m bar kapandı
    cur_bar = data["total_bars"]

    print(f"\n⚡ Scalp Trader 5m+15m | {now_str()}")
    print(f"   İşlem: {len(data['closed'])} | Sermaye: {data['capital']:.2f} USDT | Açık: {len(data['open'])}")

    def _exit_reason(direction, r):
        parts = []
        if direction == "LONG":
            if r["rsi"] > 75:            parts.append("RSI aşırı alım")
            if not r["macd_bull"]:       parts.append("MACD çapraz")
            if r["price"] < r["ema55"]:  parts.append("EMA55 altına düştü")
        else:
            if r["rsi"] < 25:            parts.append("RSI aşırı satım")
            if r["macd_bull"]:           parts.append("MACD çapraz")
            if r["price"] > r["ema55"]:  parts.append("EMA55 üstüne çıktı")
        label = "SATIŞ SİNYALİ" if direction == "LONG" else "KAPANIŞ SİNYALİ"
        return f"{label} — " + (", ".join(parts) if parts else "5m sinyal")

    # ── 1m: Trailing Stop + SL + TP sıkılaştırma + 5m Çıkış Sinyali ──
    for pos in list(data["open"]):
        pd = get_price_data(pos["symbol"])
        if not pd:
            continue

        b_high    = pd["bar_high"]
        b_low     = pd["bar_low"]
        price     = pd["price"]
        entry_atr = pos.get("entry_atr") or pd["atr"] or 0
        if not entry_atr:
            continue

        trail_mult = pos.get("trail_mult", TRAIL_ATR_MULT)
        held       = cur_bar - pos.get("open_bar", cur_bar)
        in_profit  = (price > pos["entry_price"]) if pos["direction"] == "LONG" \
                     else (price < pos["entry_price"])

        # ── Trailing Stop Güncelle ──
        if pos["direction"] == "LONG":
            best = max(pos.get("best_price", pos["entry_price"]), b_high)
            pos["best_price"] = best
            new_trail_sl = round(best - entry_atr * trail_mult, 6)
            if new_trail_sl > pos["sl"]:
                old_level  = pos.get("trail_level", 0)
                pos["sl"]  = new_trail_sl
                new_level  = max(0, int((new_trail_sl - pos["entry_price"]) / entry_atr) + 1) \
                             if new_trail_sl >= pos["entry_price"] else 0
                pos["trail_level"] = new_level
                if new_level > old_level and new_level >= 1:
                    profit_atr = round((best - pos["entry_price"]) / entry_atr, 1)
                    label = "Breakeven — Kâr Garantilendi! 🔒" if new_level == 1 else f"Seviye {new_level} — +{profit_atr} ATR kârda! 🚀"
                    print(f"  🟢 ATR-{new_level}: {pos['symbol']} SL → {new_trail_sl} ({label})")
                    tg_send(
                        f"🟢🟢 <b>ATR Seviye {new_level} — {label}</b>\n"
                        f"📈 LONG | <b>{pos['symbol']}</b>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"🎯 Giriş      : <code>{pos['entry_price']}</code>\n"
                        f"📈 En Yüksek  : <code>{best}</code>\n"
                        f"🛡 Yeni SL    : <b><code>{new_trail_sl}</code></b>\n"
                        f"📊 ATR        : <code>{entry_atr}</code>\n"
                        f"💰 Kâr mesafe : <b>+{profit_atr} ATR</b>"
                    )
                else:
                    print(f"  📈 TRAIL: {pos['symbol']} SL → {new_trail_sl}")
        else:
            best = min(pos.get("best_price", pos["entry_price"]), b_low)
            pos["best_price"] = best
            new_trail_sl = round(best + entry_atr * trail_mult, 6)
            if new_trail_sl < pos["sl"]:
                old_level  = pos.get("trail_level", 0)
                pos["sl"]  = new_trail_sl
                new_level  = max(0, int((pos["entry_price"] - new_trail_sl) / entry_atr) + 1) \
                             if new_trail_sl <= pos["entry_price"] else 0
                pos["trail_level"] = new_level
                if new_level > old_level and new_level >= 1:
                    profit_atr = round((pos["entry_price"] - best) / entry_atr, 1)
                    label = "Breakeven — Kâr Garantilendi! 🔒" if new_level == 1 else f"Seviye {new_level} — +{profit_atr} ATR kârda! 🚀"
                    print(f"  🟢 ATR-{new_level}: {pos['symbol']} SL → {new_trail_sl} ({label})")
                    tg_send(
                        f"🟢🟢 <b>ATR Seviye {new_level} — {label}</b>\n"
                        f"📉 SHORT | <b>{pos['symbol']}</b>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"🎯 Giriş      : <code>{pos['entry_price']}</code>\n"
                        f"📉 En Düşük   : <code>{best}</code>\n"
                        f"🛡 Yeni SL    : <b><code>{new_trail_sl}</code></b>\n"
                        f"📊 ATR        : <code>{entry_atr}</code>\n"
                        f"💰 Kâr mesafe : <b>+{profit_atr} ATR</b>"
                    )
                else:
                    print(f"  📉 TRAIL: {pos['symbol']} SL → {new_trail_sl}")

        open_set = {p["symbol"] for p in data["open"]}

        # ── TP Aşıldı → Pozisyonu Kapat ──
        if pos["symbol"] in open_set:
            tp_hit = (b_high >= pos["tp"]) if pos["direction"] == "LONG" else (b_low <= pos["tp"])
            if tp_hit:
                close_position(data, pos, pos["tp"], "TAKE PROFIT", entry_atr)

        # ── SL Kontrol ──
        open_set = {p["symbol"] for p in data["open"]}
        if pos["symbol"] in open_set:
            if pos["direction"] == "LONG" and b_low <= pos["sl"]:
                close_position(data, pos, pos["sl"], "STOP LOSS", entry_atr)
            elif pos["direction"] == "SHORT" and b_high >= pos["sl"]:
                close_position(data, pos, pos["sl"], "STOP LOSS", entry_atr)

        # ── Çıkış Sinyali: 15m analiz (5m gürültüsünü filtreler) ──
        open_set = {p["symbol"] for p in data["open"]}
        if pos["symbol"] in open_set and held >= MIN_HOLD_BARS:
            r5m = analyze(pos["symbol"], "15m")
            if r5m:
                exit_triggered = (pos["direction"] == "LONG" and r5m["exit_long"]) or \
                                 (pos["direction"] == "SHORT" and r5m["exit_short"])
                if exit_triggered:
                    if not in_profit:
                        close_position(data, pos, r5m["price"], _exit_reason(pos["direction"], r5m), entry_atr)
                    else:
                        new_mult = max(0.4, pos.get("trail_mult", TRAIL_ATR_MULT) - 0.2)
                        pos["trail_mult"] = new_mult
                        print(f"  ⚠️  5m çıkış sinyali — kârda, trail sıkılaştı → {new_mult}×ATR: {pos['symbol']}")

    # ── 5m: Giriş Sinyali Tarama — Her 5 Dakikada Bir ──
    if len(data["open"]) < MAX_OPEN:
        found      = 0
        scan_start = datetime.now(timezone.utc)

        with ThreadPoolExecutor(max_workers=25) as ex:
            futures = {ex.submit(analyze, sym, "5m"): sym for sym in SCALP_SYMBOLS}
            results = {}
            for f in as_completed(futures):
                sym = futures[f]
                try:
                    results[sym] = f.result()
                except Exception:
                    results[sym] = None

        elapsed = round((datetime.now(timezone.utc) - scan_start).total_seconds(), 1)
        print(f"   🔍 Tarama tamamlandı: {elapsed}s")

        new_this_scan = 0
        for symbol in SCALP_SYMBOLS:
            if len(data["open"]) >= MAX_OPEN:
                break
            if new_this_scan >= MAX_NEW_PER_SCAN:
                break
            result = results.get(symbol)
            if not result:
                continue
            score = result.get("entry_score") or 0
            if result["strong_buy"] and score >= MIN_ENTRY_SCORE:
                if open_position(data, symbol, "LONG", result["price"], result["atr"], result):
                    found += 1
                    new_this_scan += 1
            elif result["strong_sell"] and score >= MIN_ENTRY_SCORE:
                if open_position(data, symbol, "SHORT", result["price"], result["atr"], result):
                    found += 1
                    new_this_scan += 1

        if found == 0:
            print(f"   ℹ️  Bu turda sinyal bulunamadı.")

    save_trades(data)

    if len(data["closed"]) % 100 == 0 and len(data["closed"]) > 0:
        print(f"\n🎯 {len(data['closed'])} İŞLEM RAPORU GÖNDERİLİYOR (devam ediyor...)")
        _analyze_performance(data)
        _send_full_report(data)

    # Her 12 barda bir saatlik rapor (12 × 5m = 60 dk)
    if cur_bar % 12 == 0 and cur_bar > 0:
        _send_status_report(data)

    # İlk çalışmada başlangıç bildirimi
    if cur_bar == 1:
        tg_send(
            f"⚡ <b>Scalp Trader Başladı</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"📊 50 coin | 5m sinyal + 15m çıkış\n"
            f"💰 Sermaye: {data['capital']:.2f} USDT\n"
            f"🔔 Sinyal bulunduğunda bildirim gelecek."
        )

    # Her 3 barda bir (15 dk) kısa durum mesajı — sinyal yoksa
    if cur_bar % 3 == 0 and cur_bar > 0 and len(data["open"]) == 0:
        tg_send(
            f"🔍 <b>Tarama devam ediyor</b> | {now_str()}\n"
            f"💰 Sermaye: {data['capital']:.2f} USDT | Açık: {len(data['open'])}\n"
            f"ℹ️ Henüz uygun sinyal bulunamadı."
        )

    return data

# ========== RAPORLAR ==========

def _analyze_performance(data):
    trades   = data["closed"]
    wins     = [t for t in trades if t["pnl_pct"] > 0]
    losses   = [t for t in trades if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    win_rate  = round(len(wins) / len(trades) * 100, 1)
    avg_win   = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss  = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    print(f"\n{'='*50}\n📊 SCALP ANALİZİ — {len(trades)} İşlem\n{'='*50}")
    print(f"💰 Başlangıç: {VIRTUAL_CAPITAL} | Son: {data['capital']:.2f} USDT")
    print(f"🎯 Win Rate : %{win_rate} | PnL: {total_pnl:+.2f} USDT")
    print(f"✅ Ort. Kâr : %{avg_win} | 🔴 Ort. Zarar: %{avg_loss}")

def _send_status_report(data):
    trades    = data["closed"]
    if not trades:
        return
    wins      = [t for t in trades if t["pnl_pct"] > 0]
    losses    = [t for t in trades if t["pnl_pct"] < 0]
    stops     = [t for t in trades if t["reason"] == "STOP LOSS"]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    win_rate  = round(len(wins) / len(trades) * 100, 1)
    avg_win   = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss  = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    roi       = round((data["capital"] - VIRTUAL_CAPITAL) / VIRTUAL_CAPITAL * 100, 2)
    recent    = trades[-20:] if len(trades) >= 20 else trades
    rec_wr    = round(len([t for t in recent if t["pnl_pct"] > 0]) / len(recent) * 100, 1)
    trend     = "📈" if rec_wr > win_rate else "📉"
    cap_emoji = "💚" if data["capital"] >= VIRTUAL_CAPITAL else "🔴"
    tg_send(
        f"⚡ <b>Saatlik Scalp Raporu</b> | {now_str()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{cap_emoji} Sermaye  : <b>{data['capital']:.2f} USDT</b> ({'+' if roi>=0 else ''}{roi}%)\n"
        f"📈 Toplam PnL: <b>{'+' if total_pnl>=0 else ''}{total_pnl:.2f} USDT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Win Rate  : <b>%{win_rate}</b> ({len(wins)}K / {len(losses)}Z)\n"
        f"{trend} Son 20 işlem: <b>%{rec_wr}</b>\n"
        f"📊 Ort. Kâr  : %{avg_win} | Ort. Zarar: %{avg_loss}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 Toplam    : {len(trades)} işlem | 🛑 SL: {len(stops)}\n"
        f"🔓 Açık      : {len(data['open'])} pozisyon"
    )
    print(f"   ⚡ Saatlik rapor gönderildi.")

def _send_full_report(data):
    trades    = data["closed"]
    wins      = [t for t in trades if t["pnl_pct"] > 0]
    losses    = [t for t in trades if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    win_rate  = round(len(wins) / len(trades) * 100, 1)
    avg_win   = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss  = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    tg_send(
        f"🏆 <b>100 SCALP İŞLEM TAMAMLANDI!</b>\n"
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
    run_scan()

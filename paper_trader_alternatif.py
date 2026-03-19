#!/usr/bin/env python3
"""
Paper Trader Alternatif — Confluence Stratejisi (Pine → Python)
Scalping Confluence BİST mantığı, kripto için uyarlanmış.

Farklar (BİST → Kripto):
- Seans filtresi YOK (7/24)
- Hacim çarpanı 1.5
- Swing uzunluğu 5
- Aynı coin listesi, ayrı state, ayrı Telegram
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from paper_trader_alt_config import BOT_TOKEN, CHAT_ID
except ImportError:
    BOT_TOKEN = ""
    CHAT_ID = ""

# ========== AYARLAR ==========

TRADES_FILE    = os.path.join(os.path.dirname(__file__), "paper_trades_alt.json")
VIRTUAL_CAPITAL= 200.0
LEVERAGE       = 10
MAX_OPEN       = 8
COOLDOWN_BARS  = 4
POS_SIZE_PCT   = 0.10
COMMISSION_PCT = 0.001

# Confluence (Pine'dan)
MIN_CONF       = 3
ATR_MULT_SL    = 1.5
RR_RATIO       = 2.0
MIN_RR         = 1.5      # Kripto: 2.0 çok sıkı, 1.5 deneyelim
STRUCT_LEN     = 5
VOL_MULT       = 1.5
EMA_FAST       = 9
EMA_SLOW       = 21
EMA_TREND      = 50
RSI_LEN        = 14
RSI_OB         = 70
RSI_OS         = 30
MACD_FAST      = 12
MACD_SLOW      = 26
MACD_SIG       = 9

# ========== TELEGRAM ==========

def tg_send(text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception:
        pass

def now_str():
    now = datetime.now(timezone.utc)
    ist_h = (now.hour + 3) % 24
    return f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')} İST"

# ========== VERİ ==========

def get_klines(symbol, interval="15m", limit=250):
    # Binance önce — paper_trader ve binance_trader ile aynı veri kaynağı
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return [float(d[4]) for d in data], [float(d[5]) for d in data], [float(d[2]) for d in data], [float(d[3]) for d in data]
    except Exception:
        pass
    base = symbol.replace("USDT", "")
    okx_bar = {"15m": "15m", "1h": "1H", "4h": "4H"}.get(interval, interval)
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

# ========== İNDİKATÖRLER ==========

def ema(data, period):
    if not data or len(data) < period:
        return None
    k = 2 / (period + 1)
    result = [sum(data[:period]) / period]
    for i in range(period, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result

def rsi(closes, period=14):
    if not closes or len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i - 1]
        gains.append(chg if chg > 0 else 0)
        losses.append(-chg if chg < 0 else 0)
    rs_list = []
    for i in range(period, len(gains) + 1):
        avg_gain = sum(gains[i - period:i]) / period
        avg_loss = sum(losses[i - period:i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 99
        rs_list.append(100 - 100 / (1 + rs))
    return rs_list[-1] if rs_list else None

def macd(closes, fast=12, slow=26, sig=9):
    if not closes or len(closes) < slow + sig:
        return None, None, None
    ema_f = ema(closes, fast)
    ema_s = ema(closes, slow)
    if not ema_f or not ema_s:
        return None, None, None
    offset = slow - fast
    macd_line = [ema_f[i + offset] - ema_s[i] for i in range(len(ema_s))]
    sig_ema = ema(macd_line, sig)
    if not sig_ema:
        return None, None, None
    sig_offset = len(macd_line) - len(sig_ema)
    return macd_line[-1], sig_ema[-1], macd_line[-1] - sig_ema[-1]

def atr(highs, lows, closes, period=14):
    if not closes or len(closes) < period + 1:
        return None
    tr_list = []
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hc, lc))
    return sum(tr_list[-period:]) / period if len(tr_list) >= period else None

def get_pivots(highs, lows, left, right):
    """Son iki pivot high ve low döndür (Pine ta.pivothigh/pivotlow uyumlu)."""
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

# ========== CONFLUENCE ANALİZ ==========

def analyze_confluence(symbol):
    """Pine Scalping Confluence mantığı — kripto uyarlı."""
    closes, volumes, highs, lows = get_klines(symbol, "15m", 150)
    if not closes or len(closes) < 100:
        return None

    # 15m
    ema_f = ema(closes, EMA_FAST)
    ema_s = ema(closes, EMA_SLOW)
    ema_t = ema(closes, EMA_TREND)
    if not ema_f or not ema_s or not ema_t:
        return None
    ema_fast = ema_f[-1]
    ema_slow = ema_s[-1]
    ema_trend = ema_t[-1]
    price = closes[-2]

    rsi_val = rsi(closes, RSI_LEN)
    macd_line, sig_line, hist = macd(closes, MACD_FAST, MACD_SLOW, MACD_SIG)
    atr_val = atr(highs, lows, closes, 14)
    if rsi_val is None or macd_line is None or atr_val is None:
        return None

    # Hacim
    vol_ma = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1]
    high_vol = volumes[-2] >= vol_ma * VOL_MULT

    # HTF trend (1h, 4h)
    c1h, _, h1h, l1h = get_klines(symbol, "1h", 60)
    c4h, _, h4h, l4h = get_klines(symbol, "4h", 60)
    if not c1h or len(c1h) < 55:
        htf_bull = htf_bear = False
    else:
        ema50_1h = ema(c1h, 50)
        ema50_4h = ema(c4h, 50) if c4h and len(c4h) >= 55 else None
        htf_close_1h = c1h[-2]
        htf_close_4h = c4h[-2] if c4h and len(c4h) >= 2 else htf_close_1h
        htf_ema50_1h = ema50_1h[-1] if ema50_1h else htf_close_1h
        htf_ema50_4h = ema50_4h[-1] if ema50_4h else htf_close_4h
        htf_bull = htf_close_1h > htf_ema50_1h and htf_close_4h > htf_ema50_4h
        htf_bear = htf_close_1h < htf_ema50_1h and htf_close_4h < htf_ema50_4h

    # Yapı (pivot)
    last_sh, prev_sh, last_sl, prev_sl = get_pivots(highs, lows, STRUCT_LEN, STRUCT_LEN)

    struct_bull = (last_sh and prev_sh and last_sl and prev_sl and
                   last_sh > prev_sh and last_sl > prev_sl)
    struct_bear = (last_sh and prev_sh and last_sl and prev_sl and
                   last_sh < prev_sh and last_sl < prev_sl)

    near_support = last_sl and abs(price - last_sl) / price < 0.005
    near_resist = last_sh and abs(price - last_sh) / price < 0.005

    # Confluence
    c_trend_bull = htf_bull
    c_struct_bull = struct_bull
    c_ema_bull = ema_fast > ema_slow and price > ema_trend
    c_rsi_bull = 50 < rsi_val < RSI_OB
    c_macd_bull = macd_line > sig_line and hist > 0
    c_vol_bull = high_vol

    c_trend_bear = htf_bear
    c_struct_bear = struct_bear
    c_ema_bear = ema_fast < ema_slow and price < ema_trend
    c_rsi_bear = RSI_OS < rsi_val < 50
    c_macd_bear = macd_line < sig_line and hist < 0
    c_vol_bear = high_vol

    long_score = sum([c_trend_bull, c_struct_bull, c_ema_bull, c_rsi_bull, c_macd_bull, c_vol_bull])
    short_score = sum([c_trend_bear, c_struct_bear, c_ema_bear, c_rsi_bear, c_macd_bear, c_vol_bear])

    # R:R (swing bazlı)
    long_risk = (price - last_sl) if (last_sl and last_sl < price) else atr_val * ATR_MULT_SL
    long_reward = (last_sh - price) if (last_sh and last_sh > price) else atr_val * ATR_MULT_SL * RR_RATIO
    real_rr_long = long_reward / long_risk if long_risk > 0 else 0

    short_risk = (last_sh - price) if (last_sh and last_sh > price) else atr_val * ATR_MULT_SL
    short_reward = (price - last_sl) if (last_sl and last_sl < price) else atr_val * ATR_MULT_SL * RR_RATIO
    real_rr_short = short_reward / short_risk if short_risk > 0 else 0

    rr_ok_long = real_rr_long >= MIN_RR
    rr_ok_short = real_rr_short >= MIN_RR

    # EMA crossover (tetikleyici)
    ema_cross_up = len(ema_f) >= 2 and ema_f[-2] <= ema_s[-2] and ema_f[-1] > ema_s[-1]
    ema_cross_down = len(ema_f) >= 2 and ema_f[-2] >= ema_s[-2] and ema_f[-1] < ema_s[-1]

    # Sinyal (kripto: seans yok)
    long_signal = long_score >= MIN_CONF and not near_resist and rr_ok_long
    short_signal = short_score >= MIN_CONF and not near_support and rr_ok_short

    long_entry = long_signal and ema_cross_up
    short_entry = short_signal and ema_cross_down

    # SL/TP (giriş yapılırsa kullanılacak)
    sl_long = price - atr_val * ATR_MULT_SL
    tp_long = price + (price - sl_long) * RR_RATIO
    sl_short = price + atr_val * ATR_MULT_SL
    tp_short = price - (sl_short - price) * RR_RATIO

    return {
        "symbol": symbol,
        "price": price,
        "bar_high": highs[-2],
        "bar_low": lows[-2],
        "atr": atr_val,
        "rsi": rsi_val,
        "ema21": ema_slow,
        "ema50": ema_trend,
        "long_score": long_score,
        "short_score": short_score,
        "real_rr_long": round(real_rr_long, 2),
        "real_rr_short": round(real_rr_short, 2),
        "strong_buy": long_entry,
        "strong_sell": short_entry,
        "sl_long": round(sl_long, 6),
        "tp_long": round(tp_long, 6),
        "sl_short": round(sl_short, 6),
        "tp_short": round(tp_short, 6),
    }

# ========== STATE ==========

def load_state():
    for path in [TRADES_FILE, TRADES_FILE + ".bak"]:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("closed") or data.get("open"):
                    return data
            except Exception:
                continue
    return {"open": [], "closed": [], "capital": VIRTUAL_CAPITAL, "bar_counter": {}, "total_bars": 0}

def save_state(data):
    import shutil
    if os.path.exists(TRADES_FILE):
        shutil.copy2(TRADES_FILE, TRADES_FILE + ".bak")
    with open(TRADES_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ========== POZİSYON ==========

def open_position(data, symbol, direction, price, sl, tp, atr_val, result):
    if any(p["symbol"] == symbol for p in data["open"]):
        return False
    if len(data["open"]) >= MAX_OPEN:
        return False
    last_bar = data.get("bar_counter", {}).get(symbol, -999)
    if data.get("total_bars", 0) - last_bar < COOLDOWN_BARS:
        return False

    # Binance ile uyumlu: geçersiz SL/TP'de işlem açma (düşük coinlerde negatif olabiliyor)
    if sl <= 0 or tp <= 0:
        return False

    # Margin her zaman toplam sermayenin %10'u (kalan değil) — 170$ → 17$, binance_trader ile uyumlu
    size = round(data["capital"] * POS_SIZE_PCT, 2)
    data["open"].append({
        "symbol": symbol,
        "direction": direction,
        "entry_price": price,
        "size_usdt": size,
        "sl": sl,
        "tp": tp,
        "open_time": now_str(),
        "open_bar": data.get("total_bars", 0),
        "entry_atr": atr_val,
        "leverage": LEVERAGE,
    })
    data.setdefault("bar_counter", {})[symbol] = data["total_bars"]

    sl_pct = round(abs(price - sl) / price * 100, 3)
    tp_pct = round(abs(tp - price) / price * 100, 3)
    rr = result.get("real_rr_long" if direction == "LONG" else "real_rr_short", 0)
    score = result.get("long_score" if direction == "LONG" else "short_score", 0)
    atr_pct = round((atr_val / price) * 100, 3) if price else 0

    win_prob = round(score / 6 * 100) if score else 0
    prob_filled = min(6, max(0, round(win_prob * 6 / 100)))
    prob_bar = "⬜️" * prob_filled + "⬛️" * (6 - prob_filled)
    prob_emoji = "🟢" if win_prob >= 60 else "🟡" if win_prob >= 45 else "🔴"

    emoji = "📈" if direction == "LONG" else "📉"
    print(f"  {emoji} {direction}: {symbol} @ {price} | SL:{sl} ({sl_pct}%) | TP:{tp} ({tp_pct}%) | R:R {rr} | Conf {score}/6")
    tg_send(
        f"{emoji} <b>Yeni İşlem Açıldı #{len(data['open'])}</b>\n"
        f"<b>{direction}</b> | <b>{symbol}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎯 Giriş : {price}\n"
        f"🛑 SL : {sl} (-%{sl_pct})\n"
        f"✅ TP : {tp} (+%{tp_pct})\n"
        f"📉 ATR : {atr_val} (%{atr_pct})\n"
        f"━━━━━━━━━━━━━━\n"
        f"{prob_emoji} <b>Başarı Tahmini : %{win_prob}</b>\n"
        f"{prob_bar} R:R = 1:{rr}\n"
        f"━━━━━━━━━━━━━━\n"
        f"⚖️ Piyasa: Confluence {score}/6 -> {LEVERAGE}x kaldıraç\n"
        f"Margin: {size} USDT (Max: 4L / 4S)\n"
        f"━━━━━━━━━━━━━━\n"
        f"📋 <b>Neden açtım?</b>\n"
        f"   • Confluence: {score}/6 uyum\n"
        f"   • R:R = 1:{rr}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Sermaye: {data['capital']:.2f} USDT\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    )
    return True

def close_position(data, pos, price, reason):
    symbol = pos["symbol"]
    direction = pos["direction"]
    entry = pos["entry_price"]
    lev = pos.get("leverage", LEVERAGE)
    margin = pos.get("size_usdt", 10)
    if direction == "LONG":
        pnl_pct = (price - entry) / entry * 100 * lev
    else:
        pnl_pct = (entry - price) / entry * 100 * lev
    notional = margin * lev
    commission = notional * COMMISSION_PCT
    pnl_usdt = margin * pnl_pct / 100 - commission
    data["capital"] += pnl_usdt

    trade = {**pos, "exit_price": price, "exit_time": now_str(), "reason": reason,
             "pnl_pct": round(pnl_pct, 2), "pnl_usdt": round(pnl_usdt, 2),
             "commission": commission, "trade_no": len(data["closed"]) + 1}
    data["closed"].append(trade)
    data["open"] = [p for p in data["open"] if p["symbol"] != symbol]
    data.setdefault("bar_counter", {})[symbol] = data["total_bars"]

    emoji = "✅" if pnl_pct > 0 else "🔴"
    print(f"  {emoji} KAPANDI [{direction}]: {symbol} @ {price} | {'+' if pnl_pct>0 else ''}{pnl_pct}% | {reason}")
    tg_send(
        f"{emoji} <b>Alternatif — İşlem Kapandı #{trade['trade_no']}</b>\n"
        f"{'📈' if direction=='LONG' else '📉'} {direction} | <b>{symbol}</b>\n"
        f"Sonuç: {'+' if pnl_pct>0 else ''}{pnl_pct}% ({'+' if pnl_usdt>0 else ''}{pnl_usdt:.2f} USDT)\n"
        f"Neden: {reason}\n"
        f"💰 Sermaye: {data['capital']:.2f} USDT"
    )

# ========== ANA DÖNGÜ ==========

def run_scan(symbols):
    data = load_state()
    data.setdefault("total_bars", 0)
    now_utc = datetime.now(timezone.utc)
    is_new_15m = now_utc.minute % 15 <= 4

    if is_new_15m:
        data["total_bars"] = data.get("total_bars", 0) + 1

    print(f"\n🤖 Paper Trader ALTERNATİF | {now_str()}")
    print(f"   İşlem: {len(data['closed'])} | Sermaye: {data['capital']:.2f} USDT | Açık: {len(data['open'])}")

    if is_new_15m:
        scan_start = datetime.now(timezone.utc)
        scan_set = list(set(symbols) | {p["symbol"] for p in data["open"]})
        results = {}
        with ThreadPoolExecutor(max_workers=30) as ex:
            futures = {ex.submit(analyze_confluence, sym): sym for sym in scan_set}
            for f in as_completed(futures):
                sym = futures[f]
                try:
                    results[sym] = f.result()
                except Exception:
                    results[sym] = None
        elapsed = round((datetime.now(timezone.utc) - scan_start).total_seconds(), 1)
        print(f"   🔍 Tarama tamamlandı: {elapsed}s")

        # SL/TP / çıkış
        for pos in list(data["open"]):
            r = results.get(pos["symbol"])
            if not r:
                continue
            bh, bl = r["bar_high"], r["bar_low"]
            if pos["direction"] == "LONG":
                if bl <= pos["sl"]:
                    close_position(data, pos, pos["sl"], "STOP LOSS")
                    continue
                if bh >= pos["tp"]:
                    close_position(data, pos, pos["tp"], "TAKE PROFIT")
                    continue
            else:
                if bh >= pos["sl"]:
                    close_position(data, pos, pos["sl"], "STOP LOSS")
                    continue
                if bl <= pos["tp"]:
                    close_position(data, pos, pos["tp"], "TAKE PROFIT")
                    continue

        # Yeni giriş
        if len(data["open"]) < MAX_OPEN:
            found = 0
            for symbol in symbols:
                if len(data["open"]) >= MAX_OPEN:
                    break
                r = results.get(symbol)
                if not r:
                    continue
                if r["strong_buy"]:
                    if open_position(data, symbol, "LONG", r["price"], r["sl_long"], r["tp_long"], r["atr"], r):
                        found += 1
                elif r["strong_sell"]:
                    if open_position(data, symbol, "SHORT", r["price"], r["sl_short"], r["tp_short"], r["atr"], r):
                        found += 1
            if found == 0:
                print(f"   ℹ️  Bu turda sinyal bulunamadı.")
                if now_utc.minute == 0:
                    tg_send(
                        f"🔍 <b>Alternatif Tarama</b> | {now_str()}\n"
                        f"ℹ️ Bu saatte uygun işlem bulunamadı.\n"
                        f"💰 Sermaye: {data['capital']:.2f} USDT\n"
                        f"🔓 Açık: {len(data['open'])} | Toplam: {len(data['closed'])}"
                    )

    save_state(data)
    return data

# ========== MAIN ==========

if __name__ == "__main__":
    from crypto_futures_list import FUTURES_SYMBOLS
    pairs = [s + "USDT" for s in FUTURES_SYMBOLS]
    run_scan(pairs)

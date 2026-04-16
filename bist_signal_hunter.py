#!/usr/bin/env python3
"""
BIST Güçlü AL + Boğa Onayı Tarayıcı
İki indikatörün aynı anda sağlandığı hisseleri 15m ve 1h'de tarar, Telegram bildirimi atar.

İndikatör 1 — Güçlü AL (RSI+Vol+EMA v5.4):
  strongBuyCondition:
    - RSI 50 crossover VEYA RSI>55 ve yükseliyor
    - Hacim > ort×1.5 VE hacim > son 10 bar maks×1.2
    - Fiyat > EMA50
    - ADX > 25
    - MACD(12/26/9) bull
    - Fiyat/EMA200 mesafesi < %5

İndikatör 2 — Bull Onayı (MACD Pro):
  macdCrossUp AND RSI > 55 AND ADX > 20 AND hacim spike

Çalışma: Pazartesi–Cuma, 10:00–18:00 İST
"""

import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

from bist_scanner import BIST_TICKERS, ema as ema_series, rsi as rsi_calc

try:
    from bist_scalping_config import BOT_TOKEN, CHAT_ID
except ImportError:
    try:
        from telegram_config import BOT_TOKEN, CHAT_ID
    except ImportError:
        BOT_TOKEN = ""
        CHAT_ID = ""

# ========== AYARLAR ==========

IST         = ZoneInfo("Europe/Istanbul")
SESS_START  = 1000
SESS_END    = 1800
MAX_WORKERS = 30

# İndikatör 1 parametreleri
EMA_SHORT        = 50
EMA_LONG         = 200
RSI_LEN          = 14
VOL_MA_LEN       = 20
VOL_MULT         = 1.5      # hacim spike çarpanı
VOL_CONFIRM_MULT = 1.2      # son 10 bar maks çarpanı
ADX_MIN_STRONG   = 25       # güçlü AL için ADX eşiği
DIST_MAX_PCT     = 5.0      # EMA200'e max uzaklık %
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIG         = 9

# İndikatör 2 parametreleri
RSI_MIN_BULL = 55       # bull onay için RSI eşiği
ADX_MIN_BULL = 20       # bull onay için ADX eşiği

# SL/TP (Pine stratejisinden)
SL_PCT  = 5.0
TP1_PCT = 10.0
TP2_PCT = 15.0

# Son 2 gün içinde aynı hisse + aynı zaman dilimi için kaçıncı bildirim (Telegram başlığında N.kez)
HISTORY_FILE      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bist_signal_hunter_history.json")
NOTIFY_WINDOW_SEC = 2 * 24 * 3600
# ACIL: son 2 günde 15m en az bu kadar + aynı pencerede en az 1 adet 1h bildirimi (geçmiş veya bu tur)
MIN_15M_COUNT_ACIL = 3

# ========== TELEGRAM ==========

def tg_send(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        ).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15)
    except Exception:
        pass

# ========== ZAMAN ==========

def in_session() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return SESS_START <= t < SESS_END

# ========== İNDİKATÖRLER ==========

def macd_calc(close: pd.Series):
    ema_f  = ema_series(close, MACD_FAST)
    ema_s  = ema_series(close, MACD_SLOW)
    macd   = ema_f - ema_s
    signal = ema_series(macd, MACD_SIG)
    return macd, signal

def adx_calc(high, low, close, n=14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    dm_p = high.diff()
    dm_m = -low.diff()
    dm_p = dm_p.where((dm_p > dm_m) & (dm_p > 0), 0.0)
    dm_m = dm_m.where((dm_m > dm_p) & (dm_m > 0), 0.0)
    atr14 = tr.ewm(span=n, adjust=False).mean()
    di_p  = 100 * dm_p.ewm(span=n, adjust=False).mean() / atr14
    di_m  = 100 * dm_m.ewm(span=n, adjust=False).mean() / atr14
    dx    = (abs(di_p - di_m) / (di_p + di_m).replace(0, float("nan"))) * 100
    return dx.ewm(span=n, adjust=False).mean()

# ========== TEK TF ANALİZİ ==========

def analyze_tf(ticker: str, interval: str) -> dict | None:
    """
    Belirtilen zaman diliminde güçlü AL + bull onayı kontrol eder.
    İki koşul aynı anda sağlanırsa sonuç döner, yoksa None.
    """
    sym    = f"{ticker}.IS"
    period = "60d" if interval == "15m" else "120d"
    try:
        df = yf.Ticker(sym).history(period=period, interval=interval, auto_adjust=True)
        if df is None or len(df) < 120:
            return None
        df = df.dropna()
        if len(df) < 120:
            return None

        h, l, c, v = df["High"], df["Low"], df["Close"], df["Volume"]
        i = -2   # son kapanmış bar

        # ── İndikatörler ──
        ema50_s       = ema_series(c, EMA_SHORT)
        ema200_s      = ema_series(c, EMA_LONG)
        rsi_s         = rsi_calc(c, RSI_LEN)
        macd_s, sig_s = macd_calc(c)
        adx_s         = adx_calc(h, l, c, 14)
        vol_ma        = v.rolling(VOL_MA_LEN).mean()

        price      = float(c.iloc[i])
        rsi_val    = float(rsi_s.iloc[i])
        rsi_prev   = float(rsi_s.iloc[i - 1])
        macd_val   = float(macd_s.iloc[i])
        sig_val    = float(sig_s.iloc[i])
        macd_prev  = float(macd_s.iloc[i - 1])
        sig_prev   = float(sig_s.iloc[i - 1])
        adx_val    = float(adx_s.iloc[i])
        ema50_val  = float(ema50_s.iloc[i])
        ema200_val = float(ema200_s.iloc[i])
        vol_val    = float(v.iloc[i])
        vol_avg    = float(vol_ma.iloc[i])

        # Hacim
        vol_spike   = vol_val > vol_avg * VOL_MULT
        vol_confirm = vol_val > float(v.iloc[-12:-2].max()) * VOL_CONFIRM_MULT

        # ── İNDİKATÖR 1: strongBuyCondition ──
        rsi_cond   = (rsi_prev <= 50 and rsi_val > 50) or (rsi_val > 55 and rsi_val > rsi_prev)
        above_ema50 = price > ema50_val
        adx_ok      = adx_val > ADX_MIN_STRONG
        macd_bull   = macd_val > sig_val
        dist_pct    = abs((price - ema200_val) / ema200_val) * 100
        is_not_far  = dist_pct < DIST_MAX_PCT

        buy_condition = (rsi_cond and vol_spike and above_ema50
                         and adx_ok and macd_bull and is_not_far)
        strong_buy    = buy_condition and rsi_val > 55 and vol_confirm

        # ── İNDİKATÖR 2: bull_onay ──
        macd_cross_up = macd_prev <= sig_prev and macd_val > sig_val
        bull_onay     = (macd_cross_up
                         and rsi_val > RSI_MIN_BULL
                         and adx_val > ADX_MIN_BULL
                         and vol_spike)

        # ── Birleşik sinyal ──
        if not (strong_buy and bull_onay):
            return None

        sl_price  = round(price * (1 - SL_PCT  / 100), 2)
        tp1_price = round(price * (1 + TP1_PCT / 100), 2)
        tp2_price = round(price * (1 + TP2_PCT / 100), 2)

        return {
            "ticker":    ticker,
            "interval":  interval,
            "price":     round(price, 2),
            "rsi":       round(rsi_val, 1),
            "adx":       round(adx_val, 1),
            "dist_pct":  round(dist_pct, 2),
            "sl":        sl_price,
            "tp1":       tp1_price,
            "tp2":       tp2_price,
            "vol_spike": vol_spike,
        }
    except Exception:
        return None

# ========== TARAMA ==========

def scan_ticker(ticker: str) -> list[dict]:
    """15m ve 1h'yi sırayla tarar, sinyalleri döner."""
    signals = []
    for tf in ("15m", "1h"):
        r = analyze_tf(ticker, tf)
        if r:
            signals.append(r)
    return signals

# ========== BİLDİRİM SAYACI (2 gün penceresi) ==========

def _history_key(ticker: str, interval: str) -> str:
    return f"{ticker}|{interval}"


def _load_history() -> dict:
    if not os.path.isfile(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_history(history: dict) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _prune_history(history: dict) -> None:
    cutoff = time.time() - NOTIFY_WINDOW_SEC
    for k in list(history.keys()):
        lst = [ts for ts in history[k] if ts >= cutoff]
        if lst:
            history[k] = lst
        else:
            del history[k]


def next_occurrence_number(history: dict, ticker: str, interval: str) -> int:
    """Bu gönderim, pencere içinde bu (hisse, TF) için kaçıncı bildirim olacak (1 tabanlı)."""
    key = _history_key(ticker, interval)
    return len(history.get(key, [])) + 1


def record_notification_sent(history: dict, ticker: str, interval: str) -> None:
    key = _history_key(ticker, interval)
    history.setdefault(key, []).append(time.time())


def has_1h_support(ticker: str, history: dict, batch: list[dict]) -> bool:
    """Son 2 günde bu hisse için 1h bildirimi var mı veya bu turda 1h sinyali var mı?"""
    if len(history.get(_history_key(ticker, "1h"), [])) >= 1:
        return True
    return any(x.get("ticker") == ticker and x.get("interval") == "1h" for x in batch)


def style_15m_alert(history: dict, ticker: str, n_15m: int, batch: list[dict]) -> str:
    """15m satırı: çoklu tekrar + 1h onayı → ACIL; aksi ODAKLAN BUNA formatı."""
    if n_15m >= MIN_15M_COUNT_ACIL and has_1h_support(ticker, history, batch):
        return "acil"
    return "odaklan"


# ========== BİLDİRİM ==========

def build_message(r: dict, repeat_n: int = 1, style_15m: str | None = None) -> str:
    """Tek TF sinyali için mesaj (sadece 15m veya sadece 1h)."""
    sl_pct  = round(abs(r["price"] - r["sl"])  / r["price"] * 100, 2)
    tp1_pct = round(abs(r["tp1"]  - r["price"]) / r["price"] * 100, 2)
    tp2_pct = round(abs(r["tp2"]  - r["price"]) / r["price"] * 100, 2)
    vol_lbl = "✅ Spike" if r["vol_spike"] else "➖ Normal"

    if r["interval"] == "15m":
        st = style_15m or "odaklan"
        if st == "acil":
            header = (
                f"🟢 <b>GÜÇLÜ AL — {r['ticker']} [15 Dakika - {repeat_n}.kez] - ACIL</b>\n"
            )
        else:
            b15 = f"[15 Dakika - {repeat_n}.kez]" if repeat_n >= 2 else "[15 Dakika]"
            header = (
                f"🟢 <b>GÜÇLÜ AL — {r['ticker']} {b15} - ODAKLAN BUNA</b>\n"
            )
    else:
        repeat_part = f" ({repeat_n}.kez)" if repeat_n >= 2 else ""
        header = f"🟢 <b>GÜÇLÜ AL — {r['ticker']}{repeat_part}</b>  [1 Saat]\n"

    return (
        header +
        f"━━━━━━━━━━━━━━\n"
        f"💵 Fiyat   : <b>{r['price']} ₺</b>\n"
        f"🛑 SL      : {r['sl']} ₺  (-%{sl_pct})\n"
        f"🎯 TP1     : {r['tp1']} ₺  (+%{tp1_pct})\n"
        f"🎯 TP2     : {r['tp2']} ₺  (+%{tp2_pct})\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 RSI     : {r['rsi']}  |  ADX: {r['adx']}\n"
        f"📏 EMA200  : %{r['dist_pct']} uzakta\n"
        f"📦 Hacim   : {vol_lbl}\n"
        f"✅ MACD Bull onayı var\n"
        f"━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(IST).strftime('%d.%m.%Y %H:%M')} İST"
    )


def build_combined_message(r15: dict, r1h: dict, n15: int, n1h: int, style_15m: str | None = None) -> str:
    """15m + 1h aynı anda tetiklendiğinde tek birleşik mesaj."""
    sl_pct  = round(abs(r15["price"] - r15["sl"])  / r15["price"] * 100, 2)
    tp1_pct = round(abs(r15["tp1"]  - r15["price"]) / r15["price"] * 100, 2)
    tp2_pct = round(abs(r15["tp2"]  - r15["price"]) / r15["price"] * 100, 2)
    vol_lbl = "✅ Spike" if r15["vol_spike"] else "➖ Normal"

    st  = style_15m or "odaklan"
    b15 = f"[15 Dakika - {n15}.kez]" if n15 >= 2 else "[15 Dakika]"
    b1h_repeat = f"  (1h: {n1h}.kez)" if n1h >= 2 else ""

    if st == "acil":
        header = f"🔴 <b>GÜÇLÜ AL — {r15['ticker']} {b15} + [1 Saat] - ACIL</b>\n"
    else:
        header = f"🟢 <b>GÜÇLÜ AL — {r15['ticker']} {b15} + [1 Saat] - ODAKLAN BUNA</b>\n"

    return (
        header +
        f"━━━━━━━━━━━━━━\n"
        f"⚡ <b>HEM 15m HEM 1h SİNYAL VERDİ{b1h_repeat}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 Fiyat   : <b>{r15['price']} ₺</b>\n"
        f"🛑 SL      : {r15['sl']} ₺  (-%{sl_pct})\n"
        f"🎯 TP1     : {r15['tp1']} ₺  (+%{tp1_pct})\n"
        f"🎯 TP2     : {r15['tp2']} ₺  (+%{tp2_pct})\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 15m RSI : {r15['rsi']}  |  ADX: {r15['adx']}\n"
        f"📊 1h  RSI : {r1h['rsi']}  |  ADX: {r1h['adx']}\n"
        f"📏 EMA200  : %{r15['dist_pct']} uzakta\n"
        f"📦 Hacim   : {vol_lbl}\n"
        f"✅ MACD Bull onayı var (her iki TF)\n"
        f"━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(IST).strftime('%d.%m.%Y %H:%M')} İST"
    )


# ========== ANA DÖNGÜ ==========

def run():
    if not in_session():
        print("BIST Signal Hunter: Seans dışı — çalışmıyor.")
        return

    now = datetime.now(IST).strftime("%d.%m.%Y %H:%M")
    print(f"\n🔍 BIST Signal Hunter | {now} İST")
    print(f"   {len(BIST_TICKERS)} hisse × 2 TF taranıyor (15m + 1h)...")

    all_signals: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fut = {ex.submit(scan_ticker, t): t for t in BIST_TICKERS}
        for f in as_completed(fut):
            try:
                signals = f.result()
                if signals:
                    all_signals.extend(signals)
            except Exception:
                pass

    if not all_signals:
        print("   ℹ️  Bu turda sinyal bulunamadı.")
        return

    history = _load_history()
    _prune_history(history)

    # Sinyalleri hisseye göre grupla
    signals_by_ticker: dict[str, dict] = {}
    for r in all_signals:
        t = r["ticker"]
        signals_by_ticker.setdefault(t, {})
        signals_by_ticker[t][r["interval"]] = r

    print(f"   ✅ {len(all_signals)} sinyal ({len(signals_by_ticker)} hisse):")
    for ticker, tf_map in sorted(signals_by_ticker.items()):
        r15 = tf_map.get("15m")
        r1h = tf_map.get("1h")

        if r15 and r1h:
            # ── Her iki TF de tetiklendi → birleşik mesaj ──
            n15  = next_occurrence_number(history, ticker, "15m")
            n1h  = next_occurrence_number(history, ticker, "1h")
            st15 = style_15m_alert(history, ticker, n15, all_signals)
            extra = " | ACIL" if st15 == "acil" else " | ODAKLAN"
            print(f"      [15m+1h] {ticker:8s} | {r15['price']:>8} ₺ | RSI:{r15['rsi']:>5} | ADX:{r15['adx']:>5}"
                  f" | 15m:{n15}.bildirim  1h:{n1h}.bildirim{extra}")
            tg_send(build_combined_message(r15, r1h, n15, n1h, st15))
            record_notification_sent(history, ticker, "15m")
            record_notification_sent(history, ticker, "1h")

        else:
            # ── Sadece tek TF tetiklendi → normal mesaj ──
            r      = r15 or r1h
            tf_lbl = "15m" if r["interval"] == "15m" else " 1h"
            n      = next_occurrence_number(history, ticker, r["interval"])
            st15   = None
            extra  = ""
            if r["interval"] == "15m":
                st15  = style_15m_alert(history, ticker, n, all_signals)
                extra = " | ACIL" if st15 == "acil" else " | ODAKLAN"
            print(f"      [{tf_lbl}]    {ticker:8s} | {r['price']:>8} ₺ | RSI:{r['rsi']:>5} | ADX:{r['adx']:>5}"
                  f" | {n}.bildirim (son 2 gün){extra}")
            tg_send(build_message(r, repeat_n=n, style_15m=st15))
            record_notification_sent(history, ticker, r["interval"])

        _save_history(history)


if __name__ == "__main__":
    run()

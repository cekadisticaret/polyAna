#!/usr/bin/env python3
"""
BIST Scalping Confluence [15M] — Pine ile uyumlu tarama + Telegram.
427 hisse, 15m AL sinyali ve TP1 takibi.

Çalışma: Pazartesi–Cuma, 10:00–18:00 İST (bu pencere dışında script çıkar).

Pine: Scalping Confluence [BİST 15M] v1.1 ile aynı mantık (long_entry + TP1).
"""

import json
import os
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

IST = ZoneInfo("Europe/Istanbul")
STATE_FILE = os.path.join(os.path.dirname(__file__), "bist_scalping_state.json")

# Pine varsayılanları
HTF_1 = "1h"
HTF_2 = "4h"
EMA_FAST, EMA_SLOW, EMA_TREND = 9, 21, 50
RSI_LEN, RSI_OB, RSI_OS = 14, 70, 30
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9
VOL_MA_LEN = 20
VOL_MULT = 2.0
STRUCT_LEN = 8
SESS_START, SESS_END = 1000, 1800  # 10:00 ≤ t < 18:00 İST
MIN_CONF = 3
ATR_MULT_SL = 1.5
RR_RATIO = 2.0
MIN_RR = 2.0
FILTER_OPEN = True
AVOID_CLOSE = True


def tg_send(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        ).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15)
    except Exception:
        pass


def _hhmm_ist() -> int:
    now = datetime.now(IST)
    return now.hour * 100 + now.minute


def in_service_window():
    """Pazartesi–Cuma, 10:00–18:00 İST — tüm bildirimler bu pencerede."""
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Cmt=5, Paz=6
        return False
    t = now.hour * 100 + now.minute
    return SESS_START <= t < SESS_END


def valid_session_flags():
    """AL sinyali için: seans içi + açılış rush yok + kapanışa 30 dk kala yok (17:30+)."""
    t = _hhmm_ist()
    in_session = t >= SESS_START and t < SESS_END
    is_open_rush = FILTER_OPEN and 930 <= t < 1000
    near_close = AVOID_CLOSE and t >= 1730
    valid = in_session and not is_open_rush and not near_close
    return valid, in_session, is_open_rush, near_close


def macd_line_sig_hist(close: pd.Series):
    ema_f = ema_series(close, MACD_FAST)
    ema_s = ema_series(close, MACD_SLOW)
    macd = ema_f - ema_s
    sig = ema_series(macd, MACD_SIG)
    hist = macd - sig
    return macd, sig, hist


def atr_series(high, low, close, n=14):
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def get_pivots(highs, lows, left, right):
    def ph(arr, i):
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

    def pl(arr, i):
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
        if ph(highs, i):
            ph_list.append((i, highs[i]))
        if pl(lows, i):
            pl_list.append((i, lows[i]))
    last_sh = ph_list[-1][1] if ph_list else None
    prev_sh = ph_list[-2][1] if len(ph_list) >= 2 else None
    last_sl = pl_list[-1][1] if pl_list else None
    prev_sl = pl_list[-2][1] if len(pl_list) >= 2 else None
    return last_sh, prev_sh, last_sl, prev_sl


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"positions": {}}


def save_state(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def analyze_ticker(ticker: str, ignore_time_filters: bool = False):
    """
    Son kapanmış 15m mumda long_entry var mı?
    Pine: barstate — son tam kapanan mum = -2 (yfinance son satır sıklıkla açık mum).
    ignore_time_filters: True ise seans saati filtresi uygulanmaz (tek seferlik tarama için).
    """
    sym = f"{ticker}.IS"
    try:
        df = yf.Ticker(sym).history(period="60d", interval="15m", auto_adjust=True)
        if df is None or len(df) < 120:
            return None
        df = df.dropna()
        h, l, c, v = df["High"], df["Low"], df["Close"], df["Volume"]
        i = -2  # son kapanmış mum

        # HTF
        df1 = yf.Ticker(sym).history(period="120d", interval="1h", auto_adjust=True)
        df4 = yf.Ticker(sym).history(period="365d", interval="4h", auto_adjust=True)
        if df1 is None or len(df1) < 55 or df4 is None or len(df4) < 55:
            return None
        c1 = df1["Close"]
        c4 = df4["Close"]
        e50_1 = ema_series(c1, 50)
        e50_4 = ema_series(c4, 50)
        htf_close = c1.iloc[-2]
        htf2_close = c4.iloc[-2]
        htf_ema50 = e50_1.iloc[-2]
        htf2_ema50 = e50_4.iloc[-2]
        htf_bull = htf_close > htf_ema50
        htf2_bull = htf2_close > htf2_ema50
        trend_bull = htf_bull and htf2_bull
        htf_bear = htf_close < htf_ema50
        htf2_bear = htf2_close < htf2_ema50
        trend_bear = htf_bear and htf2_bear

        ema_f = ema_series(c, EMA_FAST)
        ema_s = ema_series(c, EMA_SLOW)
        ema_t = ema_series(c, EMA_TREND)
        rsi_v = rsi_calc(c, RSI_LEN)
        macd, sig, hist = macd_line_sig_hist(c)
        atr14 = atr_series(h, l, c, 14)

        vol_ma = v.rolling(VOL_MA_LEN).mean()
        high_vol = v.iloc[i] >= vol_ma.iloc[i] * VOL_MULT

        high_arr = h.values
        low_arr = l.values
        last_sh, prev_sh, last_sl, prev_sl = get_pivots(high_arr, low_arr, STRUCT_LEN, STRUCT_LEN)

        struct_bull = (
            last_sh is not None
            and prev_sh is not None
            and last_sl is not None
            and prev_sl is not None
            and last_sh > prev_sh
            and last_sl > prev_sl
        )
        struct_bear = (
            last_sh is not None
            and prev_sh is not None
            and last_sl is not None
            and prev_sl is not None
            and last_sh < prev_sh
            and last_sl < prev_sl
        )

        close_px = c.iloc[i]
        last_sh_f = float(last_sh) if last_sh is not None else np.nan
        last_sl_f = float(last_sl) if last_sl is not None else np.nan
        near_support = (
            not np.isnan(last_sl_f) and abs(close_px - last_sl_f) / close_px < 0.005
        )
        near_resist = (
            not np.isnan(last_sh_f) and abs(close_px - last_sh_f) / close_px < 0.005
        )

        rsi_i = rsi_v.iloc[i]
        macd_i = macd.iloc[i]
        sig_i = sig.iloc[i]
        hist_i = hist.iloc[i]

        c_trend_bull = trend_bull
        c_struct_bull = struct_bull
        c_ema_bull = ema_f.iloc[i] > ema_s.iloc[i] and close_px > ema_t.iloc[i]
        c_rsi_bull = rsi_i > 50 and rsi_i < RSI_OB
        c_macd_bull = macd_i > sig_i and hist_i > 0
        c_vol_bull = high_vol

        long_score = sum(
            [c_trend_bull, c_struct_bull, c_ema_bull, c_rsi_bull, c_macd_bull, c_vol_bull]
        )

        atr_i = atr14.iloc[i]
        lrisk = (
            (close_px - last_sl_f)
            if (last_sl is not None and last_sl_f < close_px)
            else atr_i * ATR_MULT_SL
        )
        lrew = (
            (last_sh_f - close_px)
            if (last_sh is not None and last_sh_f > close_px)
            else atr_i * ATR_MULT_SL * RR_RATIO
        )
        real_rr_long = (lrew / lrisk) if lrisk and lrisk > 0 else 0.0
        rr_ok_long = real_rr_long >= MIN_RR

        valid_sess, _, _, _ = valid_session_flags()
        if ignore_time_filters:
            valid_sess = True
        long_signal = (
            long_score >= MIN_CONF
            and not near_resist
            and valid_sess
            and rr_ok_long
        )

        # EMA crossover (Pine: ta.crossover) — i mumunda
        ema_cross_up = (
            ema_f.iloc[i - 1] <= ema_s.iloc[i - 1] and ema_f.iloc[i] > ema_s.iloc[i]
        )

        long_entry = long_signal and ema_cross_up

        entry_price = float(close_px)
        sl_price = entry_price - atr_i * ATR_MULT_SL
        tp1_price = entry_price + (entry_price - sl_price) * RR_RATIO
        tp2_price = entry_price + (entry_price - sl_price) * RR_RATIO * 1.5

        return {
            "ticker": ticker,
            "long_entry": long_entry,
            "entry": round(entry_price, 4),
            "sl": round(sl_price, 4),
            "tp1": round(tp1_price, 4),
            "tp2": round(tp2_price, 4),
            "long_score": long_score,
            "real_rr": round(real_rr_long, 2),
            "high_last": float(h.iloc[-1]),
        }
    except Exception:
        return None


def check_tp1_hit(ticker: str, tp1: float) -> bool:
    try:
        sym = f"{ticker}.IS"
        df = yf.Ticker(sym).history(period="5d", interval="15m", auto_adjust=True)
        if df is None or len(df) < 2:
            return False
        hi = df["High"].tail(96)
        return bool((hi >= float(tp1)).any())
    except Exception:
        return False


def run():
    if not in_service_window():
        print(
            "BIST Scalping: Pazartesi–Cuma 10:00–18:00 İST dışında — çalışmıyor."
        )
        return

    state = load_state()
    positions = state.setdefault("positions", {})

    # 1) TP1 takibi
    for sym, pos in list(positions.items()):
        if pos.get("tp1_sent"):
            continue
        tp1 = pos.get("tp1")
        if not tp1:
            continue
        if check_tp1_hit(sym, tp1):
            tg_send(f"<b>{sym}</b> TP1'e ulaştı ({tp1} ₺)")
            pos["tp1_sent"] = True
            pos["tp1_hit_time"] = datetime.now(IST).strftime("%d.%m.%Y %H:%M İST")
    # Tamamlananları temizle (TP1 bildirildi)
    state["positions"] = {
        k: v for k, v in positions.items() if not v.get("tp1_sent")
    }
    # tp1_sent olanları dosyada tutmak istemiyorsak yukarıda sildik — yeniden AL için yer açılır
    save_state(state)
    positions = state["positions"]

    valid_sess, _, _, _ = valid_session_flags()
    if not valid_sess:
        print(
            f"BIST Scalping: yeni AL taranmıyor (İST {_hhmm_ist()} — kapanış/ek filtre)."
        )
        return

    # 2) Tüm hisselerde AL taraması
    results = {}
    with ThreadPoolExecutor(max_workers=30) as ex:
        fut = {ex.submit(analyze_ticker, t): t for t in BIST_TICKERS}
        for f in as_completed(fut):
            t = fut[f]
            try:
                r = f.result()
                if r:
                    results[t] = r
            except Exception:
                pass

    new_al = []
    for t, r in results.items():
        if not r.get("long_entry"):
            continue
        if t in positions:
            continue
        entry = r["entry"]
        tp1 = r["tp1"]
        tp2 = r["tp2"]
        sl = r["sl"]
        positions[t] = {
            "entry": entry,
            "tp1": tp1,
            "tp2": tp2,
            "sl": sl,
            "tp1_sent": False,
            "al_time": datetime.now(IST).strftime("%d.%m.%Y %H:%M İST"),
        }
        new_al.append((t, entry, tp1, r.get("long_score"), r.get("real_rr")))
        tg_send(
            f"<b>{t}</b> AL verdi, önerilen alış fiyatı <b>{entry}</b> ₺\n"
            f"TP1: {tp1} | TP2: {tp2} | SL: {sl} ₺ · Skor {r.get('long_score')}/6"
        )

    if new_al:
        state["positions"] = positions
        save_state(state)
        print(f"BIST Scalping: {len(new_al)} yeni AL bildirimi.")
    else:
        save_state(state)
        print("BIST Scalping: yeni AL yok.")


if __name__ == "__main__":
    run()

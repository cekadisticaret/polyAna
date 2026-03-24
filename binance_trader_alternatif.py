#!/usr/bin/env python3
"""
Binance Alternatif Trader — Confluence Stratejisi
paper_trader_alternatif.py sinyal mantığı, gerçek Binance işlemleriyle.
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
STATE_FILE      = os.path.join(os.path.dirname(__file__), "binance_alt_state.json")

LEVERAGE       = 10
MAX_OPEN       = 5
COOLDOWN_BARS  = 4
POS_SIZE_PCT   = 0.20
COMMISSION_PCT = 0.001

# Confluence (paper_trader_alternatif ile birebir)
MIN_CONF       = 4
ATR_MULT_SL    = 2.0
RR_RATIO       = 2.0
MIN_RR         = 1.5

# Dinamik Trailing Stop
TRAIL_ATR_MULT = 1.5
TRAIL_TIGHTEN  = 0.4
TRAIL_MIN_MULT = 0.6
STRUCT_LEN     = 5
CROSS_LOOKBACK = 3
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

# Risk limitleri kaldırıldı — paper_trader_alternatif ile birebir uyum

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
        return [float(d[4]) for d in data], [float(d[5]) for d in data], [float(d[2]) for d in data], [float(d[3]) for d in data]
    except Exception:
        pass
    base    = symbol.replace("USDT", "")
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
    offset    = slow - fast
    macd_line = [ema_f[i + offset] - ema_s[i] for i in range(len(ema_s))]
    sig_ema   = ema(macd_line, sig)
    if not sig_ema:
        return None, None, None
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
    """paper_trader_alternatif ile birebir aynı sinyal mantığı."""
    closes, volumes, highs, lows = get_klines(symbol, "15m", 150)
    if not closes or len(closes) < 100:
        return None

    ema_f = ema(closes, EMA_FAST)
    ema_s = ema(closes, EMA_SLOW)
    ema_t = ema(closes, EMA_TREND)
    if not ema_f or not ema_s or not ema_t:
        return None
    ema_fast  = ema_f[-1]
    ema_slow  = ema_s[-1]
    ema_trend = ema_t[-1]
    price     = closes[-2]

    rsi_val              = rsi(closes, RSI_LEN)
    macd_line, sig_line, hist = macd(closes, MACD_FAST, MACD_SLOW, MACD_SIG)
    atr_val              = atr(highs, lows, closes, 14)
    if rsi_val is None or macd_line is None or atr_val is None:
        return None

    vol_ma   = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1]
    high_vol = volumes[-2] >= vol_ma * VOL_MULT

    c1h, _, h1h, l1h = get_klines(symbol, "1h", 60)
    c4h, _, h4h, l4h = get_klines(symbol, "4h", 60)
    if not c1h or len(c1h) < 55:
        htf_bull = htf_bear = False
    else:
        ema50_1h     = ema(c1h, 50)
        ema50_4h     = ema(c4h, 50) if c4h and len(c4h) >= 55 else None
        htf_close_1h = c1h[-2]
        htf_close_4h = c4h[-2] if c4h and len(c4h) >= 2 else htf_close_1h
        htf_ema50_1h = ema50_1h[-1] if ema50_1h else htf_close_1h
        htf_ema50_4h = ema50_4h[-1] if ema50_4h else htf_close_4h
        htf_bull     = htf_close_1h > htf_ema50_1h and htf_close_4h > htf_ema50_4h
        htf_bear     = htf_close_1h < htf_ema50_1h and htf_close_4h < htf_ema50_4h

    last_sh, prev_sh, last_sl, prev_sl = get_pivots(highs, lows, STRUCT_LEN, STRUCT_LEN)

    struct_bull = (last_sh and prev_sh and last_sl and prev_sl and
                   last_sh > prev_sh and last_sl > prev_sl)
    struct_bear = (last_sh and prev_sh and last_sl and prev_sl and
                   last_sh < prev_sh and last_sl < prev_sl)

    near_support = last_sl and abs(price - last_sl) / price < 0.005
    near_resist  = last_sh and abs(price - last_sh) / price < 0.005

    c_trend_bull  = htf_bull
    c_struct_bull = struct_bull
    c_ema_bull    = ema_fast > ema_slow and price > ema_trend
    c_rsi_bull    = 50 < rsi_val < RSI_OB
    c_macd_bull   = macd_line > sig_line and hist > 0
    c_vol_bull    = high_vol

    c_trend_bear  = htf_bear
    c_struct_bear = struct_bear
    c_ema_bear    = ema_fast < ema_slow and price < ema_trend
    c_rsi_bear    = RSI_OS < rsi_val < 45
    c_macd_bear   = macd_line < sig_line and hist < 0
    c_vol_bear    = high_vol

    long_score  = sum([c_trend_bull, c_struct_bull, c_ema_bull, c_rsi_bull, c_macd_bull, c_vol_bull])
    short_score = sum([c_trend_bear, c_struct_bear, c_ema_bear, c_rsi_bear, c_macd_bear, c_vol_bear])

    long_risk    = (price - last_sl) if (last_sl and last_sl < price) else atr_val * ATR_MULT_SL
    long_reward  = (last_sh - price) if (last_sh and last_sh > price) else atr_val * ATR_MULT_SL * RR_RATIO
    real_rr_long = long_reward / long_risk if long_risk > 0 else 0

    short_risk    = (last_sh - price) if (last_sh and last_sh > price) else atr_val * ATR_MULT_SL
    short_reward  = (price - last_sl) if (last_sl and last_sl < price) else atr_val * ATR_MULT_SL * RR_RATIO
    real_rr_short = short_reward / short_risk if short_risk > 0 else 0

    rr_ok_long  = real_rr_long  >= MIN_RR
    rr_ok_short = real_rr_short >= MIN_RR

    ema_cross_up = any(
        ema_f[-(CROSS_LOOKBACK - i)] > ema_s[-(CROSS_LOOKBACK - i)] and
        ema_f[-(CROSS_LOOKBACK - i + 1)] <= ema_s[-(CROSS_LOOKBACK - i + 1)]
        for i in range(CROSS_LOOKBACK)
        if (CROSS_LOOKBACK - i + 1) <= len(ema_f)
    )
    ema_cross_down = any(
        ema_f[-(CROSS_LOOKBACK - i)] < ema_s[-(CROSS_LOOKBACK - i)] and
        ema_f[-(CROSS_LOOKBACK - i + 1)] >= ema_s[-(CROSS_LOOKBACK - i + 1)]
        for i in range(CROSS_LOOKBACK)
        if (CROSS_LOOKBACK - i + 1) <= len(ema_f)
    )

    long_signal  = long_score  >= MIN_CONF and not near_resist  and rr_ok_long
    short_signal = short_score >= MIN_CONF and not near_support and rr_ok_short

    long_entry  = long_signal  and ema_cross_up
    short_entry = short_signal and ema_cross_down

    sl_long  = price - atr_val * ATR_MULT_SL
    tp_long  = price + (price - sl_long) * RR_RATIO
    sl_short = price + atr_val * ATR_MULT_SL
    tp_short = price - (sl_short - price) * RR_RATIO

    return {
        "symbol":        symbol,
        "price":         price,
        "bar_high":      highs[-2],
        "bar_low":       lows[-2],
        "atr":           atr_val,
        "rsi":           rsi_val,
        "ema21":         ema_slow,
        "ema50":         ema_trend,
        "long_score":    long_score,
        "short_score":   short_score,
        "real_rr_long":  round(real_rr_long, 2),
        "real_rr_short": round(real_rr_short, 2),
        "strong_buy":    long_entry,
        "strong_sell":   short_entry,
        "sl_long":       round(sl_long, 6),
        "tp_long":       round(tp_long, 6),
        "sl_short":      round(sl_short, 6),
        "tp_short":      round(tp_short, 6),
    }

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


def _binance_close_fill_summary(symbol):
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
        exit_px     = (
            sum(float(t.get("price", 0)) * float(t.get("qty", 0)) for t in close_fills) / qty_sum
            if qty_sum > 0 else float(close_fills[0].get("price", 0))
        )
        return exit_px, round(rpnl + comm_signed, 4), abs(comm_signed)
    except Exception:
        return None

# ========== TP UZATMA ==========

def _extend_tp(state, sym, pos, entry_atr, hit_tp):
    direction   = pos["direction"]
    trail_mult  = pos.get("trail_mult", TRAIL_ATR_MULT)
    trail_level = pos.get("trail_level", 0)
    new_mult    = max(TRAIL_MIN_MULT, trail_mult - TRAIL_TIGHTEN)
    new_level   = trail_level + 1
    old_tp      = pos["tp"]

    if direction == "LONG":
        new_tp = round_price(sym, old_tp + entry_atr * RR_RATIO, "up")
        new_sl = round_price(sym, hit_tp - entry_atr * new_mult, "down")
    else:
        new_tp = round_price(sym, old_tp - entry_atr * RR_RATIO, "down")
        new_sl = round_price(sym, hit_tp + entry_atr * new_mult, "up")

    if direction == "LONG"  and new_sl <= pos["sl"]:
        new_sl = pos["sl"]
    if direction == "SHORT" and new_sl >= pos["sl"]:
        new_sl = pos["sl"]

    pos["tp"]          = new_tp
    pos["sl"]          = new_sl
    pos["trail_mult"]  = new_mult
    pos["trail_level"] = new_level
    pos["best_price"]  = hit_tp

    try:
        cancel_all_orders(sym)
        side = "SELL" if direction == "LONG" else "BUY"
        place_stop_market(sym, side, new_sl)
        place_take_profit_market(sym, side, new_tp)
    except Exception as e:
        print(f"   {sym}: _extend_tp order hatası: {e}")

    entry   = pos["entry_price"]
    best    = pos.get("best_price", entry)
    pnl_atr = ((best - entry) / entry_atr) if direction == "LONG" else ((entry - best) / entry_atr)
    emoji   = "📈" if direction == "LONG" else "📉"
    stars   = "🟢" * min(new_level, 5)
    print(f"  {stars} TP EXT [{sym}] Sev.{new_level}: TP {old_tp} → {new_tp} | SL → {new_sl} | Trail x{new_mult}")
    tg_send(
        f"{stars} <b>ALT — TP Aşıldı Uzatıldı #{new_level}</b> | {sym}\n"
        f"{emoji} {direction}\n"
        f"━━━━━━━━━━━━━━\n"
        f"✅ Geçilen TP : {old_tp}\n"
        f"🎯 Yeni TP   : {new_tp}\n"
        f"🛑 Yeni SL   : {new_sl} (trail x{new_mult})\n"
        f"📊 Anlık kâr : ~+{round(pnl_atr, 1)} ATR"
    )

# ========== POZİSYON AÇMA ==========

def open_position(state, symbol, direction, price, atr_val, result):
    positions = state["positions"]
    if symbol in positions:
        return False
    if len(positions) >= MAX_OPEN:
        return False

    last_bar = state.get("bar_counter", {}).get(symbol, -999)
    if state.get("total_bars", 0) - last_bar < COOLDOWN_BARS:
        return False

    avail, total = get_balance()
    desired = total * POS_SIZE_PCT
    if avail < desired * 0.5:   # avail'in en az %50'si varsa aç (yarı boy ile de gir)
        print(f"   {symbol}: yetersiz bakiye — avail={avail:.2f} < {desired * 0.5:.2f}")
        return False
    margin = min(desired, avail)  # hiçbir zaman available bakiyeyi aşmaz

    if direction == "LONG":
        sl = round_price(symbol, price - atr_val * ATR_MULT_SL, "down")
        tp = round_price(symbol, price + (price - sl) * RR_RATIO, "up")
    else:
        sl = round_price(symbol, price + atr_val * ATR_MULT_SL, "up")
        tp = round_price(symbol, price - (sl - price) * RR_RATIO, "down")

    if sl <= 0 or tp <= 0:
        return False

    notional = margin * LEVERAGE
    qty      = round_quantity(symbol, notional / price)
    if qty <= 0 or qty * price < 5:
        return False

    score    = result.get("long_score" if direction == "LONG" else "short_score", 0)
    win_prob = round(score / 6 * 100)
    rr       = result.get("real_rr_long" if direction == "LONG" else "real_rr_short", RR_RATIO)
    sl_pct   = round(abs(price - sl) / price * 100, 3)
    tp_pct   = round(abs(tp - price) / price * 100, 3)
    atr_pct  = round((atr_val / price) * 100, 3)
    atr_lvl  = round(price + atr_val, 6) if direction == "LONG" else round(price - atr_val, 6)

    prob_filled = min(6, max(0, round(win_prob * 6 / 100)))
    prob_bar    = "⬜️" * prob_filled + "⬛️" * (6 - prob_filled)
    prob_emoji  = "🟢" if win_prob >= 60 else "🟡" if win_prob >= 45 else "🔴"

    try:
        set_leverage(symbol, LEVERAGE)
        if direction == "LONG":
            place_market_order(symbol, "BUY", qty)
            place_stop_market(symbol, "SELL", sl)
            place_take_profit_market(symbol, "SELL", tp)
        else:
            place_market_order(symbol, "SELL", qty)
            place_stop_market(symbol, "BUY", sl)
            place_take_profit_market(symbol, "BUY", tp)

        fill_price = price
        try:
            import time as _time
            _time.sleep(1.0)
            bpos = get_positions()
            for p in bpos:
                if p.get("symbol") == symbol:
                    ep = float(p.get("entryPrice", 0))
                    if ep > 0:
                        fill_price = ep
                    break
        except Exception:
            pass

        state["positions"][symbol] = {
            "symbol":      symbol,
            "direction":   direction,
            "entry_price": fill_price,
            "sl":          sl,
            "tp":          tp,
            "open_bar":    state.get("total_bars", 0),
            "open_time":   now_str(),
            "leverage":    LEVERAGE,
            "margin":      margin,
            "entry_atr":   round(atr_val, 6),
            "win_prob":    win_prob,
            "best_price":  fill_price,
            "trail_mult":  TRAIL_ATR_MULT,
            "trail_level": 0,
        }
        state.setdefault("bar_counter", {})[symbol] = state.get("total_bars", 0)

        emoji  = "📈" if direction == "LONG" else "📉"
        n_open = len(state["positions"])
        print(f"  {emoji} {direction}: {symbol} @ {fill_price} | SL:{sl} ({sl_pct}%) | TP:{tp} ({tp_pct}%) | Conf {score}/6 R:R {rr}")
        tg_send(
            f"{emoji} <b>ALT — Yeni İşlem Açıldı #{n_open}</b>\n"
            f"<b>{direction}</b> | <b>{symbol}</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎯 Giriş : {fill_price}\n"
            f"🛑 SL    : {sl} (-%{sl_pct})\n"
            f"✅ TP    : {tp} (+%{tp_pct})\n"
            f"📉 ATR   : {atr_val} (%{atr_pct}) → {atr_lvl}\n"
            f"━━━━━━━━━━━━━━\n"
            f"{prob_emoji} <b>Başarı Tahmini : %{win_prob}</b>\n"
            f"{prob_bar} R:R = 1:{rr}\n"
            f"━━━━━━━━━━━━━━\n"
            f"⚖️ Confluence {score}/6 → {LEVERAGE}x kaldıraç\n"
            f"Margin: {margin:.2f} USDT\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 Bakiye: {avail:.2f} USDT\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
        )
        return True
    except Exception as e:
        print(f"   ❌ {symbol} emir hatası: {e}")
        tg_send(f"❌ <b>ALT Binance Emir Hatası</b>\n{symbol}: {str(e)}")
        return False

# ========== POZİSYON KAPATMA ==========

def close_position(
    state, pos, price, reason,
    already_closed=False,
    binance_net_pnl_usdt=None,
    binance_commission_usdt=None,
):
    symbol = pos["symbol"]
    if not already_closed:
        try:
            cancel_all_orders(symbol)
            bpos = get_positions()
            for p in bpos:
                if p["symbol"] == symbol:
                    amt  = float(p["positionAmt"])
                    side = "SELL" if amt > 0 else "BUY"
                    place_market_order(symbol, side, abs(amt))
                    break
        except Exception as e:
            print(f"   ❌ Kapatma hatası {symbol}: {e}")
            tg_send(f"❌ ALT Kapatma hatası {symbol}: {e}")
            return

    direction = pos["direction"]
    entry     = pos["entry_price"]
    lev       = pos.get("leverage", LEVERAGE)
    margin    = pos.get("margin", 10)
    notional  = margin * lev

    if binance_net_pnl_usdt is not None:
        pnl_usdt   = round(float(binance_net_pnl_usdt), 2)
        pnl_pct    = round((pnl_usdt / margin) * 100, 2) if margin else 0.0
        commission = round(float(binance_commission_usdt), 4) if binance_commission_usdt is not None else round(notional * COMMISSION_PCT, 4)
    else:
        price_chg_pct = (price - entry) / entry * 100 if direction == "LONG" else (entry - price) / entry * 100
        pnl_pct       = round(price_chg_pct * lev, 2)
        commission    = round(notional * COMMISSION_PCT, 4)
        pnl_usdt      = round(margin * pnl_pct / 100 - commission, 2)

    close_time = now_str()
    trade = {
        **pos,
        "exit_price":       price,
        "exit_time":        close_time,
        "reason":           reason,
        "pnl_pct":          pnl_pct,
        "pnl_usdt":         pnl_usdt,
        "commission":       commission,
        "trade_no":         len(state.get("closed", [])) + 1,
        "pnl_from_binance": binance_net_pnl_usdt is not None,
    }
    state["closed"] = state.get("closed", []) + [trade]
    if symbol in state.get("positions", {}):
        del state["positions"][symbol]
    state.setdefault("bar_counter", {})[symbol] = state.get("total_bars", 0)

    held_bars    = state.get("total_bars", 0) - pos.get("open_bar", 0)
    held_min     = held_bars * 15
    duration_str = (f"{held_min} dk" if held_min < 60
                    else (f"{held_min // 60}s {held_min % 60}dk" if held_min % 60 else f"{held_min // 60} saat"))

    entry_atr = pos.get("entry_atr")
    atr_line  = ""
    if entry_atr and entry:
        atr_pct  = round(entry_atr / entry * 100, 3)
        atr_lvl  = round(entry + entry_atr, 6) if direction == "LONG" else round(entry - entry_atr, 6)
        atr_line = f"📉 ATR     : {entry_atr} (%{atr_pct}) → {atr_lvl}\n"

    avail, _  = get_balance()
    emoji     = "✅" if pnl_pct > 0 else "🔴"
    dir_emoji = "📈" if direction == "LONG" else "📉"
    bn_note   = "📌 <i>Net PnL borsa realized.</i>\n" if trade.get("pnl_from_binance") else ""

    print(f"  {emoji} KAPANDI [{direction}]: {symbol} @ {price} | {'+' if pnl_pct>0 else ''}{pnl_pct}% | {reason}")
    tg_send(
        f"{emoji} <b>ALT — İşlem Kapandı #{trade['trade_no']}</b>\n"
        f"{dir_emoji} {direction} | <b>{symbol}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🕐 Açılış  : {pos.get('open_time', '-')}\n"
        f"🏁 Kapanış : {close_time}\n"
        f"⏱ Süre    : {duration_str}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎯 Giriş   : {entry}\n"
        f"🚪 Çıkış   : {price}\n"
        f"📊 Sonuç   : <b>{'+' if pnl_pct>0 else ''}{pnl_pct}%</b> ({'+' if pnl_usdt>0 else ''}{pnl_usdt:.2f} USDT) — {lev}x\n"
        f"💸 Komisyon: -{commission:.3f} USDT\n"
        f"{atr_line}"
        f"{bn_note}"
        f"💡 Neden   : {reason}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Bakiye  : {avail:.2f} USDT\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    )

# ========== ANA DÖNGÜ ==========

def run_scan(symbols, precomputed_results=None):
    state = load_state()
    state.setdefault("total_bars", 0)
    now_utc    = datetime.now(timezone.utc)
    is_new_15m = now_utc.minute % 15 <= 4

    if is_new_15m:
        state["total_bars"] = state.get("total_bars", 0) + 1

    avail, total      = get_balance()
    binance_positions = {p["symbol"]: p for p in get_positions()}

    print(f"\n🤖 Binance ALT Trader | {now_str()}")
    print(f"   İşlem: {len(state.get('closed', []))} | Bakiye: {avail:.2f} / {total:.2f} USDT | Açık: {len(state['positions'])}")

    # Binance sync — borsa tarafında kapanan pozisyonları tespit et
    for sym in list(state["positions"].keys()):
        if sym not in binance_positions:
            pos     = dict(state["positions"][sym], symbol=sym)
            summary = _binance_close_fill_summary(sym)
            if summary:
                exit_price, net_pnl, comm_fills = summary
                reason = ("STOP LOSS (Binance)" if abs(exit_price - pos["sl"]) < abs(exit_price - pos["tp"])
                          else "TAKE PROFIT (Binance)")
                close_position(state, pos, exit_price, reason,
                               already_closed=True,
                               binance_net_pnl_usdt=net_pnl,
                               binance_commission_usdt=comm_fills)
            else:
                exit_price = pos["entry_price"]
                try:
                    trades = get_user_trades(sym, limit=5)
                    if trades:
                        by_t       = sorted(trades, key=lambda t: int(t.get("time", 0)), reverse=True)
                        exit_price = float(by_t[0].get("price", exit_price))
                except Exception:
                    pass
                close_position(state, pos, exit_price, "BINANCE SL/TP", already_closed=True)

    if is_new_15m:
        if precomputed_results is not None:
            results = precomputed_results
            print(f"   🔍 Paylaşımlı tarama kullanıldı ({len(results)} coin)")
        else:
            scan_start = datetime.now(timezone.utc)
            scan_set   = list(set(symbols) | set(state["positions"].keys()))
            results    = {}
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

        # SL/TP / Dinamik Trailing Stop (paper_trader_alternatif mantığı + Binance order güncelleme)
        for sym in list(state["positions"].keys()):
            if sym not in state["positions"]:
                continue
            pos         = state["positions"][sym]
            r           = results.get(sym)
            if not r:
                continue
            bh          = r["bar_high"]
            bl          = r["bar_low"]
            entry_atr   = pos.get("entry_atr", r["atr"])
            trail_mult  = pos.get("trail_mult", TRAIL_ATR_MULT)
            trail_level = pos.get("trail_level", 0)
            pos_sym     = dict(pos, symbol=sym)

            if pos["direction"] == "LONG":
                new_best          = max(pos.get("best_price", pos["entry_price"]), bh)
                pos["best_price"] = new_best

                trail_sl = new_best - entry_atr * trail_mult
                if trail_sl > pos["sl"]:
                    pos["sl"] = round_price(sym, trail_sl, "down")
                    try:
                        cancel_all_orders(sym)
                        place_stop_market(sym, "SELL", pos["sl"])
                        place_take_profit_market(sym, "SELL", pos["tp"])
                    except Exception as e:
                        print(f"   {sym}: trail SL güncelleme hatası: {e}")

                if bh >= pos["tp"]:
                    _extend_tp(state, sym, pos, entry_atr, pos["tp"])
                    continue

                if bl <= pos["sl"]:
                    in_profit = pos["sl"] > pos["entry_price"]
                    reason    = "TRAIL STOP" if (trail_level > 0 or in_profit) else "STOP LOSS"
                    close_position(state, pos_sym, pos["sl"], reason)
                    continue

            else:  # SHORT
                new_best          = min(pos.get("best_price", pos["entry_price"]), bl)
                pos["best_price"] = new_best

                trail_sl = new_best + entry_atr * trail_mult
                if trail_sl < pos["sl"]:
                    pos["sl"] = round_price(sym, trail_sl, "up")
                    try:
                        cancel_all_orders(sym)
                        place_stop_market(sym, "BUY", pos["sl"])
                        place_take_profit_market(sym, "BUY", pos["tp"])
                    except Exception as e:
                        print(f"   {sym}: trail SL güncelleme hatası: {e}")

                if bl <= pos["tp"]:
                    _extend_tp(state, sym, pos, entry_atr, pos["tp"])
                    continue

                if bh >= pos["sl"]:
                    in_profit = pos["sl"] < pos["entry_price"]
                    reason    = "TRAIL STOP" if (trail_level > 0 or in_profit) else "STOP LOSS"
                    close_position(state, pos_sym, pos["sl"], reason)
                    continue

        # Yeni giriş
        found = 0
        for symbol in symbols:
            if len(state["positions"]) >= MAX_OPEN:
                break
            r = results.get(symbol)
            if not r:
                continue
            if r["strong_buy"]:
                if open_position(state, symbol, "LONG", r["price"], r["atr"], r):
                    found += 1
            elif r["strong_sell"]:
                if open_position(state, symbol, "SHORT", r["price"], r["atr"], r):
                    found += 1
        if found == 0:
            print(f"   ℹ️  Bu turda sinyal bulunamadı.")
            if now_utc.minute == 0:
                tg_send(
                    f"🔍 <b>ALT Tarama</b> | {now_str()}\n"
                    f"ℹ️ Bu saatte uygun işlem bulunamadı.\n"
                    f"💰 Bakiye: {avail:.2f} USDT\n"
                    f"🔓 Açık: {len(state['positions'])} | Toplam: {len(state.get('closed', []))}"
                )
        else:
            print(f"   ✅ Bu turda {found} yeni işlem açıldı.")

    save_state(state)

    if is_new_15m and state.get("total_bars", 0) % 288 == 0 and state.get("total_bars", 0) > 0:
        send_status_report(state)

    return state

# ========== RAPORLAR ==========

def send_status_report(state):
    trades = state.get("closed", [])
    if not trades:
        return
    _, total   = get_balance()
    wins       = [t for t in trades if t["pnl_pct"] > 0]
    losses     = [t for t in trades if t["pnl_pct"] < 0]
    total_pnl  = sum(t["pnl_usdt"] for t in trades)
    win_rate   = round(len(wins) / len(trades) * 100, 1)
    avg_win    = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss   = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    roi        = round((total - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2)
    longs      = [t for t in trades if t.get("direction") == "LONG"]
    shorts     = [t for t in trades if t.get("direction") == "SHORT"]
    cap_emoji  = "💚" if total >= INITIAL_CAPITAL else "🔴"
    recent     = trades[-20:] if len(trades) >= 20 else trades
    rec_wr     = round(len([t for t in recent if t["pnl_pct"] > 0]) / len(recent) * 100, 1)
    trend      = "📈" if rec_wr > win_rate else "📉"
    tg_send(
        f"📊 <b>ALT — Günlük Rapor (24s)</b> | {now_str()}\n"
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
        f"🔓 Açık      : {len(state.get('positions', {}))} pozisyon"
    )
    print(f"   📊 Günlük rapor gönderildi.")


if __name__ == "__main__":
    from crypto_futures_list import FUTURES_SYMBOLS
    pairs = [s + "USDT" for s in FUTURES_SYMBOLS]
    run_scan(pairs)

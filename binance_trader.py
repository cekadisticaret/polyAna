#!/usr/bin/env python3
"""
Binance USDT-M Futures Gerçek Trader
paper_trader ile aynı sinyal, swing SL/TP ve margin: min(%10 hedef, serbest).
MAX_OPEN (paper ile aynı, 8) — yön kotası yok.
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# paper_trader ile birebir aynı
from paper_trader import (
    analyze, get_klines, get_market_bias,
    STOP_ATR_MULT, TAKE_ATR_MULT, MAX_SL_PCT, MIN_RR_RATIO,
    COOLDOWN_BARS, MIN_HOLD_BARS,
    BULL_LONG_LEV, BULL_SHORT_LEV, BEAR_LONG_LEV, BEAR_SHORT_LEV,
    NEUT_LONG_LEV, NEUT_SHORT_LEV,
    POS_SIZE_PCT, COMMISSION_PCT, LEVERAGE, MAX_OPEN,
    build_entry_reason, calc_win_prob,
)
from binance_config import TG_BOT_TOKEN, TG_CHAT_ID
from binance_api import (
    get_balance, get_positions, set_leverage,
    place_market_order, place_stop_market, place_take_profit_market,
    cancel_all_orders, round_quantity, round_price, get_user_trades,
)

# ========== AYARLAR (paper ile aynı) ==========

INITIAL_CAPITAL = 200.0   # paper VIRTUAL_CAPITAL
STATE_FILE     = os.path.join(os.path.dirname(__file__), "binance_state.json")

# Risk limitleri
DAILY_LOSS_LIMIT_USDT = 30   # Günlük bu kadar USDT zarar → yeni işlem açma
DRAWDOWN_PCT          = 20   # Peak'ten %20 düşüş → tüm pozisyonları kapat

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

def _log_open(msg):
    print(f"   [binance_open] {msg}")

# ========== POZİSYON AÇMA (paper ile aynı swing SL/TP) ==========

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
        lev = BULL_LONG_LEV if direction == "LONG" else BULL_SHORT_LEV
    elif bias == "BEAR":
        lev = BEAR_LONG_LEV if direction == "LONG" else BEAR_SHORT_LEV
    else:
        lev = NEUT_LONG_LEV if direction == "LONG" else NEUT_SHORT_LEV

    avail, total = get_balance()
    desired = total * POS_SIZE_PCT
    margin = min(desired, avail)
    if desired > avail:
        _log_open(f"{symbol}: margin hedef {desired:.2f} USDT → serbeste göre {margin:.2f} (avail={avail:.2f}, total={total:.2f})")
    if margin < 5 and avail < 5:
        _log_open(f"{symbol}: kullanılabilir margin çok düşük (avail={avail:.2f})")
        return False

    MIN_NOTIONAL = 100  # Binance Futures minimum
    notional = margin * lev
    qty = round_quantity(symbol, notional / price)
    if qty * price < MIN_NOTIONAL:
        need_m = max(margin, (MIN_NOTIONAL / lev) + 2)
        margin = min(need_m, avail)
        notional = margin * lev
        qty = round_quantity(symbol, notional / price)
    if qty <= 0 or qty * price < MIN_NOTIONAL:
        _log_open(
            f"{symbol}: min notional sağlanamıyor (notional≈{qty * price if qty else 0:.2f}, "
            f"min={MIN_NOTIONAL}, avail={avail:.2f})"
        )
        return False

    # Swing + ATR — paper_trader.open_position ile aynı; sonra tick yuvarlama
    last_sh = (result or {}).get("last_sh")
    last_sl = (result or {}).get("last_sl")
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

    atr_pct = round((atr / price) * 100, 3) if price else 0
    sl_pct  = round(abs(price - sl) / price * 100, 3)
    tp_pct  = round(abs(tp - price) / price * 100, 3)
    win_prob, rr_ratio = calc_win_prob(result or {}, direction, sl_pct, tp_pct)
    if rr_ratio < MIN_RR_RATIO:
        _log_open(f"{symbol}: R:R 1:{rr_ratio} < min {MIN_RR_RATIO} (sl%{sl_pct} tp%{tp_pct}) — atlandı")
        return False
    reasons = build_entry_reason(result or {}, direction)
    reason_str = "\n".join(f"   • {r}" for r in reasons)
    htf_bias_val = (result or {}).get("htf_bias", bias)
    bias_label = "Boğa (1h)" if htf_bias_val == "BULL" else "Ayı (1h)" if htf_bias_val == "BEAR" else ("HTF kapalı" if htf_bias_val == "OFF" else "Nötr (1h)")
    prob_filled = min(6, max(0, round(win_prob * 6 / 100)))
    prob_bar = "⬜️" * prob_filled + "⬛️" * (6 - prob_filled)
    prob_emoji = "🟢" if win_prob >= 60 else "🟡" if win_prob >= 45 else "🔴"

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

        state["positions"][symbol] = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": price,
            "sl": sl, "tp": tp,
            "open_bar": state.get("total_bars", 0),
            "open_time": now_str(),
            "leverage": lev,
            "margin": margin,
            "entry_atr": round(atr, 6),
            "win_prob": win_prob,
            "entry_reason": reasons,
            "htf_bias": htf_bias_val,
        }
        state.setdefault("bar_counter", {})[symbol] = state.get("total_bars", 0)

        emoji = "📈" if direction == "LONG" else "📉"
        n_open = len(state["positions"])
        _log_open(f"{symbol}: OK | {direction} margin={margin:.2f} R:R=1:{rr_ratio} açık={n_open}")
        print(f"  {emoji} {direction}: {symbol} @ {price} | SL:{sl} ({sl_pct}%) | TP:{tp} ({tp_pct}%) | Başarı:%{win_prob} | {bias_label} {lev}x")
        tg_send(
            f"{emoji} <b>Yeni İşlem Açıldı #{n_open}</b>\n"
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

# ========== POZİSYON KAPATMA (paper ile aynı) ==========

def close_position(state, pos, price, reason, already_closed=False):
    """paper_trader.close_position ile aynı format."""
    symbol = pos["symbol"]
    if not already_closed:
        try:
            cancel_all_orders(symbol)
            positions = get_positions()
            for p in positions:
                if p["symbol"] == symbol:
                    amt = float(p["positionAmt"])
                    side = "SELL" if amt > 0 else "BUY"
                    place_market_order(symbol, side, abs(amt))
                    break
        except Exception as e:
            print(f"   ❌ Kapatma hatası {symbol}: {e}")
            tg_send(f"❌ Kapatma hatası {symbol}: {e}")
            return

    direction = pos["direction"]
    entry = pos["entry_price"]
    lev = pos.get("leverage", LEVERAGE)
    margin = pos.get("margin", 10)
    if direction == "LONG":
        price_chg_pct = (price - entry) / entry * 100
    else:
        price_chg_pct = (entry - price) / entry * 100
    pnl_pct = round(price_chg_pct * lev, 2)
    notional = margin * lev
    commission = round(notional * COMMISSION_PCT, 4)
    pnl_usdt = round(margin * pnl_pct / 100 - commission, 2)

    trade = {
        **pos, "exit_price": price, "exit_time": now_str(),
        "reason": reason, "pnl_pct": pnl_pct, "pnl_usdt": pnl_usdt,
        "commission": commission, "trade_no": len(state.get("closed", [])) + 1,
        "win_prob": pos.get("win_prob"),  # Analiz için — 24h sonra tahmin vs gerçek karşılaştırma
    }
    state["closed"] = state.get("closed", []) + [trade]
    if symbol in state.get("positions", {}):
        del state["positions"][symbol]
    state.setdefault("bar_counter", {})[symbol] = state.get("total_bars", 0)

    emoji = "✅" if pnl_pct > 0 else "🔴"
    dir_emoji = "📈" if direction == "LONG" else "📉"
    entry_atr = pos.get("entry_atr")
    atr_line = f"📉 ATR     : {entry_atr} (%{round(entry_atr/entry*100, 3)})\n" if entry_atr and entry else ""
    held_bars = state.get("total_bars", 0) - pos.get("open_bar", 0)
    held_min = held_bars * 15
    duration_str = f"{held_min} dk" if held_min < 60 else (f"{held_min // 60}s {held_min % 60}dk" if held_min % 60 else f"{held_min // 60} saat")
    avail, _ = get_balance()

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
        f"💡 Neden  : {reason}\n"
        f"💰 Bakiye : {avail:.2f} USDT\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    )

# ========== ANA DÖNGÜ (paper ile aynı) ==========

def run_scan(symbols):
    state = load_state()
    state.setdefault("total_bars", 0)
    now_utc = datetime.now(timezone.utc)
    is_new_15m = now_utc.minute % 15 <= 4

    if is_new_15m:
        state["total_bars"] = state.get("total_bars", 0) + 1

    avail, total = get_balance()
    binance_positions = {p["symbol"]: p for p in get_positions()}
    cur_bar = state["total_bars"]

    # Drawdown için total (walletBalance) kullan — avail pozisyon açınca düşer (margin kilitlenir)
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
                pos = dict(state["positions"][sym], symbol=sym)
                exit_price = pos["entry_price"]
                reason = "BINANCE SL/TP"
                try:
                    trades = get_user_trades(sym, limit=5)
                    if trades:
                        last = trades[0]
                        exit_price = float(last.get("price", exit_price))
                        if abs(exit_price - pos["sl"]) < abs(exit_price - pos["tp"]):
                            reason = "STOP LOSS (Binance)"
                        else:
                            reason = "TAKE PROFIT (Binance)"
                except Exception:
                    pass
                close_position(state, pos, exit_price, reason, already_closed=True)

        # 5m bar ile SL/TP kontrolü (daha sık tepki)
        for sym, pos in list(state["positions"].items()):
            if sym not in state["positions"]:
                continue
            pos_with_sym = dict(pos, symbol=sym)
            try:
                _, _, highs, lows = get_klines(sym, "5m", 5)
                if not highs or len(highs) < 2:
                    continue
                b_high, b_low = highs[-2], lows[-2]
                if pos["direction"] == "LONG":
                    if b_low <= pos["sl"]:
                        close_position(state, pos_with_sym, pos["sl"], "STOP LOSS (5m)")
                        continue
                    if b_high >= pos["tp"]:
                        close_position(state, pos_with_sym, pos["tp"], "TAKE PROFIT (5m)")
                else:
                    if b_high >= pos["sl"]:
                        close_position(state, pos_with_sym, pos["sl"], "STOP LOSS (5m)")
                        continue
                    if b_low <= pos["tp"]:
                        close_position(state, pos_with_sym, pos["tp"], "TAKE PROFIT (5m)")
            except Exception:
                pass

    if is_new_15m:
        scan_start = datetime.now(timezone.utc)
        scan_set = list(set(symbols) | set(state["positions"].keys()))
        results = {}
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

        # Drawdown tetiklenince bildirim
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
                    bp = binance_positions.get(sym)
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
                if r["rsi"] > 75: parts.append("RSI aşırı alım")
                if not r["macd_bull"]: parts.append("MACD bear")
                if r["price"] < r["ema100"]: parts.append("EMA100 altı")
            else:
                if r["rsi"] < 25: parts.append("RSI aşırı satım")
                if r["macd_bull"]: parts.append("MACD bull")
                if r["price"] > r["ema100"]: parts.append("EMA100 üstü")
            label = "SATIŞ SİNYALİ" if direction == "LONG" else "KAPANIŞ SİNYALİ"
            return f"{label} — " + (", ".join(parts) if parts else "sinyal")

        # Bar-based SL/TP ve çıkış sinyali (15m bar — paper ile aynı)
        for sym, pos in list(state["positions"].items()):
            if sym not in state["positions"]:
                continue
            r = results.get(sym)
            if not r:
                continue
            b_high = r["bar_high"]
            b_low = r["bar_low"]
            held = cur_bar - pos.get("open_bar", cur_bar)

            # SL Kontrolü
            if pos["direction"] == "LONG" and b_low <= pos["sl"]:
                close_position(state, pos, pos["sl"], "STOP LOSS")
                continue
            elif pos["direction"] == "SHORT" and b_high >= pos["sl"]:
                close_position(state, pos, pos["sl"], "STOP LOSS")
                continue

            # TP Kontrolü
            if sym not in state["positions"]:
                continue
            if pos["direction"] == "LONG" and b_high >= pos["tp"]:
                close_position(state, pos, pos["tp"], "TAKE PROFIT")
                continue
            elif pos["direction"] == "SHORT" and b_low <= pos["tp"]:
                close_position(state, pos, pos["tp"], "TAKE PROFIT")
                continue

            # Çıkış sinyali (zararda + MIN_HOLD)
            if sym not in state["positions"]:
                continue
            in_profit = (r["price"] > pos["entry_price"]) if pos["direction"] == "LONG" else (r["price"] < pos["entry_price"])
            if not in_profit and held >= MIN_HOLD_BARS:
                exit_triggered = (pos["direction"] == "LONG" and r["exit_long"]) or (pos["direction"] == "SHORT" and r["exit_short"])
                if exit_triggered:
                    close_position(state, pos, r["price"], _exit_reason(pos["direction"], r))

        # Yeni giriş (paper ile aynı — NEUTRAL bias)
        # Günlük limit aşıldıysa yeni işlem açma
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

    # Raporlar (paper ile aynı)
    closed = state.get("closed", [])
    cur_bar = state.get("total_bars", 0)
    if len(closed) % 100 == 0 and len(closed) > 0:
        print(f"\n🎯 {len(closed)} İŞLEM RAPORU GÖNDERİLİYOR...")
        analyze_performance(state)
        send_full_report(state)
    if is_new_15m and cur_bar % 288 == 0 and cur_bar > 0:
        send_status_report(state)

    return state


# ========== RAPORLAR (paper ile aynı) ==========

def analyze_performance(state):
    trades = state.get("closed", [])
    if not trades:
        return
    _, total = get_balance()
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    longs = [t for t in trades if t.get("direction") == "LONG"]
    shorts = [t for t in trades if t.get("direction") == "SHORT"]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    win_rate = round(len(wins) / len(trades) * 100, 1)
    avg_win = round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
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
    trades = state.get("closed", [])
    if not trades:
        return
    _, total = get_balance()
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] < 0]
    stops = [t for t in trades if t.get("reason") == "STOP LOSS"]
    tps = [t for t in trades if t.get("reason") == "TAKE PROFIT"]
    longs = [t for t in trades if t.get("direction") == "LONG"]
    shorts = [t for t in trades if t.get("direction") == "SHORT"]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    total_comm = round(sum(t.get("commission", 0) for t in trades), 4)
    win_rate = round(len(wins) / len(trades) * 100, 1)
    avg_win = round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    roi = round((total - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2)
    recent = trades[-20:] if len(trades) >= 20 else trades
    rec_wr = round(len([t for t in recent if t["pnl_pct"] > 0]) / len(recent) * 100, 1)
    trend = "📈" if rec_wr > win_rate else "📉"
    cap_emoji = "💚" if total >= INITIAL_CAPITAL else "🔴"
    daily_trades = trades[-288:] if len(trades) >= 288 else trades
    daily_comm = round(sum(t.get("commission", 0) for t in daily_trades), 4)
    daily_pnl = round(sum(t["pnl_usdt"] for t in daily_trades), 2)
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
    trades = state.get("closed", [])
    if not trades:
        return
    _, total = get_balance()
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_usdt"] for t in trades)
    win_rate = round(len(wins) / len(trades) * 100, 1)
    avg_win = round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
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
        emoji = "✅" if t["pnl_pct"] > 0 else "🔴"
        dir_e = "📈" if t.get("direction") == "LONG" else "📉"
        reason = t.get("reason", "")[:8]
        chunk += f"{emoji}{dir_e} #{i} {t.get('symbol',''):12} {'+' if t['pnl_pct']>0 else ''}{t['pnl_pct']:.1f}% | {reason}\n"
        if i % 25 == 0:
            tg_send(chunk)
            chunk = ""
    if chunk:
        tg_send(chunk)


if __name__ == "__main__":
    from crypto_futures_list import FUTURES_SYMBOLS
    pairs = [s + "USDT" for s in FUTURES_SYMBOLS]
    run_scan(pairs)

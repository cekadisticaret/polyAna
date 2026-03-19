#!/usr/bin/env python3
"""
Test için örnek işlem açar. Gerçek para kullanır — minimal margin (10 USDT).
Kullanım: python3 binance_test_open.py [BTCUSDT|ETHUSDT] [LONG|SHORT]
"""

import sys
from binance_api import (
    set_leverage,
    place_market_order, place_stop_market, place_take_profit_market,
    round_quantity, round_price,
)
from paper_trader import analyze, STOP_ATR_MULT, TAKE_ATR_MULT, MAX_SL_PCT
from binance_config import TG_BOT_TOKEN, TG_CHAT_ID
import urllib.request
import urllib.parse
from datetime import datetime, timezone

def tg_send(text):
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception:
        pass

def now_str():
    now = datetime.now(timezone.utc)
    ist_h = (now.hour + 3) % 24
    return f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')} İST"

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    direction = (sys.argv[2] or "LONG").upper() if len(sys.argv) > 2 else "LONG"
    if direction not in ("LONG", "SHORT"):
        direction = "LONG"

    r = analyze(symbol, "15m")
    if not r:
        print(f"❌ {symbol} veri alınamadı")
        return

    price = r["price"]
    atr = r["atr"]
    lev = 10
    margin = 15.0  # Test: 15 USDT margin
    MIN_NOTIONAL = 100  # Binance minimum

    notional = margin * lev
    qty = round_quantity(symbol, notional / price)
    actual_notional = qty * price
    if actual_notional < MIN_NOTIONAL:
        # Yuvarlama sonrası notional düştüyse margin artır
        needed = MIN_NOTIONAL / lev
        margin = max(margin, needed + 5)
        notional = margin * lev
        qty = round_quantity(symbol, notional / price)
        actual_notional = qty * price
    if qty <= 0 or actual_notional < MIN_NOTIONAL:
        print(f"❌ Min notional {MIN_NOTIONAL} USDT — qty={qty} × price={price} = {actual_notional:.0f}")
        return

    if direction == "LONG":
        sl = round_price(symbol, max(price - atr * STOP_ATR_MULT, price * (1 - MAX_SL_PCT/100)))
        tp = round_price(symbol, price + atr * TAKE_ATR_MULT)
    else:
        sl = round_price(symbol, min(price + atr * STOP_ATR_MULT, price * (1 + MAX_SL_PCT/100)))
        tp = round_price(symbol, price - atr * TAKE_ATR_MULT)

    sl_pct = round(abs(price - sl) / price * 100, 2)
    tp_pct = round(abs(tp - price) / price * 100, 2)

    print(f"📌 Test işlem: {symbol} {direction}")
    print(f"   Fiyat: {price} | ATR: {atr}")
    print(f"   Margin: {margin} USDT | {lev}x | Qty: {qty}")
    print(f"   SL: {sl} (-{sl_pct}%) | TP: {tp} (+{tp_pct}%)")
    print("   Emir gönderiliyor...")

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

        emoji = "📈" if direction == "LONG" else "📉"
        tg_send(
            f"{emoji} <b>TEST İşlem Açıldı</b> | {symbol}\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎯 Giriş: {price} | SL: {sl} (-{sl_pct}%) | TP: {tp} (+{tp_pct}%)\n"
            f"💰 Margin: {margin} USDT | {lev}x\n"
            f"🕐 {now_str()}"
        )
        print("✅ İşlem açıldı. Telegram bildirimi gönderildi.")
    except Exception as e:
        print(f"❌ Hata: {e}")
        tg_send(f"❌ Test işlem hatası: {e}")

if __name__ == "__main__":
    main()

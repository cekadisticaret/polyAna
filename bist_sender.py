#!/usr/bin/env python3
"""
BIST Tarayıcı - Telegram Gönderici
Tarama sonuçlarını Bist Günlük Analiz grubuna gönderir.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import urllib.request
import urllib.parse
import json
from datetime import datetime
from bist_scanner import scan
from telegram_config import BOT_TOKEN, CHAT_ID


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def format_and_send(interval="1h"):
    now_utc = datetime.utcnow()
    # İstanbul saati = UTC+3
    istanbul_hour = (now_utc.hour + 3) % 24
    tarih = now_utc.strftime("%d.%m.%Y")
    saat = f"{istanbul_hour:02d}:{now_utc.minute:02d}"

    results = scan(interval)

    if not results:
        msg = (
            f"📊 <b>BIST Günlük Analiz</b>\n"
            f"🕐 {tarih} | {saat} (İST) | {interval.upper()}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 Bu taramada tüm kriterleri geçen hisse bulunamadı.\n\n"
            f"<i>Kriterler: EMA50/200 üstü, RSI momentum, ADX&gt;16, MACD Bull, Hacim Spike, Likidite</i>"
        )
    else:
        satirlar = ""
        for r in sorted(results, key=lambda x: x["rsi"], reverse=True):
            gc = "✅" if r.get("golden_cross") == "EVET" else "➖"
            satirlar += (
                f"\n🔹 <b>{r['ticker']}</b> | {r['price']} TL\n"
                f"   RSI: {r['rsi']} | ADX: {r['adx']} | Uzaklık: {r['dist_pct']}%\n"
                f"   Hacim: {r['tl_vol_sma_m']}M TL | GC: {gc}\n"
            )

        msg = (
            f"📊 <b>BIST Günlük Analiz</b>\n"
            f"🕐 {tarih} | {saat} (İST) | {interval.upper()}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>{len(results)} hisse tüm kriterleri geçti!</b>\n"
            f"{satirlar}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>⚠️ Bu paylaşım yatırım tavsiyesi değildir.</i>\n"
            f"<i>Kriterler: EMA50/200, RSI, ADX&gt;16, MACD Bull, Hacim Spike</i>"
        )

    result = send_message(msg)
    if result.get("ok"):
        print(f"✅ Mesaj gönderildi! ({len(results)} hisse)")
    else:
        print(f"❌ Hata: {result}")


if __name__ == "__main__":
    interval = sys.argv[1] if len(sys.argv) > 1 else "1h"
    format_and_send(interval)

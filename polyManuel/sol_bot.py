"""
SOL/USDT 5dk Tahmin Telegram Botu
─────────────────────────────────
Kurulum:
  pip install python-telegram-bot requests

Kullanım:
  1. @BotFather'dan yeni bot oluştur → TOKEN al
  2. Bota mesaj gönder, sonra:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     → chat_id'yi al
  3. TOKEN ve CHAT_ID'yi aşağıya yaz
  4. python sol_bot.py
"""

import requests
import time
import logging
from datetime import datetime

# ─── AYARLAR ────────────────────────────────────────────────
TELEGRAM_TOKEN = "8796782963:AAFArMaQH4rstEygo-RUnLOGiHd8Yr3moyE"
CHAT_ID        = "830754964"
SYMBOL         = "SOLUSDT"
INTERVAL       = "1m"
CANDLE_LIMIT   = 100
CHECK_INTERVAL = 60       # kaç saniyede bir kontrol (saniye)
MIN_CONFIDENCE = 35       # sinyal göndermek için minimum skor
ONLY_NEW       = True     # True: sadece yön değişiminde mesaj gönder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# ─── HESAPLAMALAR ────────────────────────────────────────────

def ema(values, period):
    k = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result

def rsi(closes, period=14):
    gains, losses = 0, 0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d > 0: gains += d
        else:     losses -= d
    avg_g = gains / period
    avg_l = losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0)) / period
    if avg_l == 0:
        return 100.0
    return 100 - (100 / (1 + avg_g / avg_l))

def macd(closes, fast=12, slow=26, signal=9):
    e_fast   = ema(closes, fast)
    e_slow   = ema(closes, slow)
    line     = [f - s for f, s in zip(e_fast, e_slow)]
    sig_line = ema(line[-18:], signal)
    hist     = line[-1] - sig_line[-1]
    return line[-1], sig_line[-1], hist

def analyze(closes, volumes):
    rsi_val = rsi(closes)
    ema9    = ema(closes, 9)
    ema21   = ema(closes, 21)
    ema55   = ema(closes, 55)
    _, _, hist = macd(closes)

    mom_pct = (closes[-1] - closes[-6]) / closes[-6] * 100
    avg_vol = sum(volumes[-20:]) / 20
    vol_ratio = sum(volumes[-5:]) / 5 / avg_vol

    # Skorlar
    rsi_score  = 20 if rsi_val < 35 else (-20 if rsi_val > 65 else 0)
    ema_bull   = ema9[-1] > ema21[-1] > ema55[-1]
    ema_bear   = ema9[-1] < ema21[-1] < ema55[-1]
    ema_score  = 25 if ema_bull else (-25 if ema_bear else 0)
    macd_score = 20 if hist > 0 else (-20 if hist < 0 else 0)
    mom_score  = 20 if mom_pct > 0.1 else (-20 if mom_pct < -0.1 else 0)
    vol_score  = 15 if (vol_ratio > 1.5 and mom_pct > 0) else \
                (-15 if (vol_ratio > 1.5 and mom_pct < 0) else 0)

    total = rsi_score + ema_score + macd_score + mom_score + vol_score

    return {
        "price":     closes[-1],
        "rsi":       rsi_val,
        "ema9":      ema9[-1],
        "ema21":     ema21[-1],
        "mom_pct":   mom_pct,
        "vol_ratio": vol_ratio,
        "hist":      hist,
        "total":     total,
        "bull":      max(total, 0),
        "bear":      max(-total, 0),
    }

# ─── BİNANCE VERİSİ ─────────────────────────────────────────

def fetch_klines():
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={SYMBOL}&interval={INTERVAL}&limit={CANDLE_LIMIT}")
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data    = r.json()
    closes  = [float(k[4]) for k in data]
    volumes = [float(k[5]) for k in data]
    return closes, volumes

# ─── TELEGRAM ────────────────────────────────────────────────

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.error(f"Telegram gönderim hatası: {e}")

def build_message(sig, conf, data):
    arrow  = "🟢 YUKARI ↑" if sig == "YUKARI" else "🔴 AŞAĞI ↓"
    bar_full  = "█" * (conf // 10)
    bar_empty = "░" * (10 - conf // 10)

    ema_trend = "YUKARI" if data["ema9"] > data["ema21"] else "AŞAĞI"
    rsi_note  = "aşırı satım" if data["rsi"] < 35 else ("aşırı alım" if data["rsi"] > 65 else "nötr")

    msg = (
        f"<b>SOL/USDT — 5dk TAHMİN</b>\n"
        f"{'─'*28}\n"
        f"{arrow}\n"
        f"Güven: {bar_full}{bar_empty} <b>{conf}%</b>\n"
        f"{'─'*28}\n"
        f"💲 Fiyat:   <b>${data['price']:.2f}</b>\n"
        f"📊 RSI:     {data['rsi']:.1f}  ({rsi_note})\n"
        f"📈 EMA:     {ema_trend}\n"
        f"⚡ Momentum: {data['mom_pct']:+.3f}%\n"
        f"🔊 Hacim:   {data['vol_ratio']:.2f}x ortalama\n"
        f"📉 MACD H:  {data['hist']:.5f}\n"
        f"{'─'*28}\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}  |  ⚠️ Yatırım tavsiyesi değildir"
    )
    return msg

# ─── ANA DÖNGÜ ───────────────────────────────────────────────

def main():
    log.info("SOL Tahmin Botu başlatıldı.")
    send_telegram("🤖 <b>SOL 5dk Tahmin Botu aktif!</b>\nHer dakika SOLUSDT analiz edilecek.")

    last_direction = None

    while True:
        try:
            closes, volumes = fetch_klines()
            data = analyze(closes, volumes)
            total = data["total"]

            if total >= MIN_CONFIDENCE:
                direction, conf = "YUKARI", data["bull"]
            elif total <= -MIN_CONFIDENCE:
                direction, conf = "AŞAĞI", data["bear"]
            else:
                direction, conf = "NÖTR", max(data["bull"], data["bear"])

            log.info(f"Fiyat={data['price']:.2f} | RSI={data['rsi']:.1f} | "
                     f"Toplam={total} | {direction} ({conf}%)")

            should_send = direction != "NÖTR"

            if should_send and direction != "NÖTR":
                msg = build_message(direction, conf, data)
                send_telegram(msg)
                last_direction = direction

        except Exception as e:
            log.error(f"Hata: {e}")
            send_telegram(f"⚠️ Hata oluştu: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

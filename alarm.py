#!/usr/bin/env python3
"""
Kripto Ani Hareket Alarmı
BTC ve majör coinleri 1 dakikada bir izler.
Ani fiyat hareketi tespit edince Telegram'a bildirim atar.
Cron: * * * * * cd /root/aiProject && python3 alarm.py >> /tmp/alarm.log 2>&1
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BOT_TOKEN = "8616178241:AAGAyz6FdPeRcnVEquV8vek0BjvNlUa2GSs"
CHAT_ID   = "830754964"

# ========== AYARLAR ==========

ALERT_1M_PCT  = 1.5   # 1 dakikalık mumda % eşik
ALERT_5M_PCT  = 3.0   # 5 dakikalık mumda % eşik
ALERT_15M_PCT = 5.0   # 15 dakikalık mumda % eşik

WATCH_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT",
]

STATE_FILE = "/tmp/alarm_state.json"

# ========== YARDIMCI ==========

def now_str():
    now   = datetime.now(timezone.utc)
    ist_h = (now.hour + 3) % 24
    return f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')} İST"

def tg_send(text):
    try:
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=data
            ), timeout=8
        )
    except Exception:
        pass

def get_klines(symbol, interval="1m", limit=20):
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={symbol}&interval={interval}&limit={limit}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        opens  = [float(d[1]) for d in data]
        closes = [float(d[4]) for d in data]
        return opens, closes
    except Exception:
        return None, None

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass

# ========== ALARM KONTROL ==========

def check_symbol(symbol, state):
    alerts = []

    opens_1m, closes_1m = get_klines(symbol, "1m", 3)
    if opens_1m and closes_1m:
        o, c = opens_1m[-2], closes_1m[-2]  # tamamlanmış son mum
        pct_1m = (c - o) / o * 100
        if abs(pct_1m) >= ALERT_1M_PCT:
            key = f"{symbol}_1m"
            last = state.get(key, 0)
            # Aynı yönde tekrar spam yapma
            if (pct_1m > 0 and last <= 0) or (pct_1m < 0 and last >= 0) or abs(pct_1m - last) >= ALERT_1M_PCT:
                alerts.append(("1m", pct_1m, c))
                state[key] = pct_1m

    opens_5m, closes_5m = get_klines(symbol, "5m", 3)
    if opens_5m and closes_5m:
        o, c = opens_5m[-2], closes_5m[-2]
        pct_5m = (c - o) / o * 100
        if abs(pct_5m) >= ALERT_5M_PCT:
            key = f"{symbol}_5m"
            last = state.get(key, 0)
            if (pct_5m > 0 and last <= 0) or (pct_5m < 0 and last >= 0) or abs(pct_5m - last) >= ALERT_5M_PCT:
                alerts.append(("5m", pct_5m, c))
                state[key] = pct_5m

    opens_15m, closes_15m = get_klines(symbol, "15m", 3)
    if opens_15m and closes_15m:
        o, c = opens_15m[-2], closes_15m[-2]
        pct_15m = (c - o) / o * 100
        if abs(pct_15m) >= ALERT_15M_PCT:
            key = f"{symbol}_15m"
            last = state.get(key, 0)
            if (pct_15m > 0 and last <= 0) or (pct_15m < 0 and last >= 0) or abs(pct_15m - last) >= ALERT_15M_PCT:
                alerts.append(("15m", pct_15m, c))
                state[key] = pct_15m

    return alerts

# ========== ANA DÖNGÜ ==========

def run():
    state = load_state()
    triggered = []

    for symbol in WATCH_SYMBOLS:
        alerts = check_symbol(symbol, state)
        for tf, pct, price in alerts:
            direction = "🚀 ANİ YÜKSELİŞ" if pct > 0 else "🔻 ANİ DÜŞÜŞ"
            sign      = "+" if pct > 0 else ""
            triggered.append(
                f"{direction} | <b>{symbol}</b>\n"
                f"   ⏱ Zaman dilimi : {tf}\n"
                f"   📊 Hareket     : <b>{sign}{pct:.2f}%</b>\n"
                f"   💲 Fiyat       : {price}"
            )

    if triggered:
        msg = f"⚠️ <b>Piyasa Alarmı</b> | {now_str()}\n━━━━━━━━━━━━━━\n"
        msg += "\n─────────────\n".join(triggered)
        tg_send(msg)
        print(f"[{now_str()}] {len(triggered)} alarm gönderildi.")
    else:
        print(f"[{now_str()}] Alarm yok.")

    save_state(state)

if __name__ == "__main__":
    run()

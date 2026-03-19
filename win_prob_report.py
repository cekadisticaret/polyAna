#!/usr/bin/env python3
"""
Win Prob Analiz Raporu — Binance Trader
Her gün 00:00 İST'de çalışır. win_prob tahminleri vs gerçek sonuçları karşılaştırır.
Cron: 0 21 * * * cd /root/aiProject && python3 win_prob_report.py >> /tmp/win_prob_report.log 2>&1
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

try:
    from binance_config import TG_BOT_TOKEN, TG_CHAT_ID
except ImportError:
    TG_BOT_TOKEN = TG_CHAT_ID = ""

STATE_FILE = os.path.join(os.path.dirname(__file__), "binance_state.json")

def tg_send(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("TG config yok")
        return
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception as e:
        print(f"TG hata: {e}")

def ist_date(time_str):
    try:
        return time_str.split(" ")[0]
    except Exception:
        return ""

def run():
    if not os.path.exists(STATE_FILE):
        print("binance_state.json bulunamadı")
        return

    with open(STATE_FILE) as f:
        state = json.load(f)

    closed = state.get("closed", [])
    # win_prob olan işlemler (eski işlemlerde olmayabilir)
    with_wp = [t for t in closed if t.get("win_prob") is not None]
    if not with_wp:
        tg_send(
            f"📊 <b>Win Prob Analiz — {datetime.now(timezone.utc).strftime('%d.%m.%Y')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"ℹ️ Henüz win_prob kayıtlı işlem yok.\n"
            f"Toplam kapanan: {len(closed)}"
        )
        print("win_prob kayıtlı işlem yok")
        return

    now_utc = datetime.now(timezone.utc)
    ist_now = now_utc + timedelta(hours=3)
    yesterday = (ist_now - timedelta(days=1)).strftime("%d.%m.%Y")
    day_trades = [t for t in with_wp if ist_date(t.get("exit_time", "")) == yesterday]

    # Tüm zamanlar + dün
    def analyze(trades, label):
        if not trades:
            return None
        wins = [t for t in trades if t.get("pnl_pct", 0) > 0]
        wr = len(wins) / len(trades) * 100
        total_pnl = sum(t.get("pnl_usdt", 0) for t in trades)
        avg_wp = sum(t["win_prob"] for t in trades) / len(trades)

        # Aralıklara göre (wp≥50, 55, 60)
        wp_50 = [t for t in trades if t["win_prob"] >= 50]
        wp_55 = [t for t in trades if t["win_prob"] >= 55]
        wp_60 = [t for t in trades if t["win_prob"] >= 60]

        # %5'lik band aralıkları (35-40, 40-45, ..., 80-85, 85-90)
        bands = {}
        for t in trades:
            wp = t["win_prob"]
            if wp is None:
                continue
            low = (wp // 5) * 5
            if low < 35:
                low = 35
            if low > 85:
                low = 85
            key = f"{int(low)}-{int(low+5)}"
            if key not in bands:
                bands[key] = []
            bands[key].append(t)

        lines = [
            f"📊 <b>Win Prob Analiz — {label}</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"🔢 İşlem sayısı : {len(trades)}",
            f"📈 Ort. Tahmin  : %{avg_wp:.1f}",
            f"🎯 Gerçek WR    : %{wr:.1f} ({len(wins)}K / {len(trades)-len(wins)}Z)",
            f"💰 Toplam PnL   : {total_pnl:+.2f} USDT",
            f"━━━━━━━━━━━━━━━━━━━━",
        ]
        if wp_50:
            wr50 = len([t for t in wp_50 if t.get("pnl_pct", 0) > 0]) / len(wp_50) * 100
            lines.append(f"📌 wp≥50 ({len(wp_50)} işlem) → Gerçek WR: %{wr50:.1f}")
        if wp_55:
            wr55 = len([t for t in wp_55 if t.get("pnl_pct", 0) > 0]) / len(wp_55) * 100
            lines.append(f"📌 wp≥55 ({len(wp_55)} işlem) → Gerçek WR: %{wr55:.1f}")
        if wp_60:
            wr60 = len([t for t in wp_60 if t.get("pnl_pct", 0) > 0]) / len(wp_60) * 100
            lines.append(f"📌 wp≥60 ({len(wp_60)} işlem) → Gerçek WR: %{wr60:.1f}")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🏆 <b>En Başarılı Aralıklar (Gerçek WR)</b>")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        band_stats = []
        for key, b in bands.items():
            if len(b) < 2:
                continue
            wins_b = len([t for t in b if t.get("pnl_pct", 0) > 0])
            wr_b = wins_b / len(b) * 100
            band_stats.append((key, len(b), wins_b, wr_b))
        band_stats.sort(key=lambda x: -x[3])  # Gerçek WR'a göre azalan
        for key, cnt, w, wr_b in band_stats[:6]:  # En iyi 6 aralık
            lines.append(f"  %{key} → {w}K/{cnt} işlem (WR %{wr_b:.0f})")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    msg_all = analyze(with_wp, "Tüm Zamanlar")
    if msg_all:
        tg_send(msg_all)

    if day_trades:
        msg_day = analyze(day_trades, f"Dün ({yesterday})")
        if msg_day:
            tg_send(msg_day)
        print(f"✅ Win prob raporu — Tüm: {len(with_wp)}, Dün: {len(day_trades)}")
    else:
        print(f"✅ Win prob raporu — Tüm: {len(with_wp)}, Dün: 0 işlem")

if __name__ == "__main__":
    run()

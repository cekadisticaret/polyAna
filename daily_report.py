#!/usr/bin/env python3
"""
Günlük Paper Trader Raporu
Her gün 00:00 İST'de çalışır, bir önceki günün işlemlerini analiz eder.
Cron: 0 21 * * * cd /root/aiProject && python3 daily_report.py >> /tmp/daily_report.log 2>&1
(21:00 UTC = 00:00 İST)
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

try:
    from crypto_telegram_config import BOT_TOKEN, CHAT_ID
except ImportError:
    BOT_TOKEN = ""
    CHAT_ID   = "830754964"
TRADES_FILE = os.path.join(os.path.dirname(__file__), "paper_trades.json")
INITIAL_CAPITAL = 149.78

# ========== YARDIMCI ==========

def tg_send(text):
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception as e:
        print(f"TG hata: {e}")

def ist_date(time_str):
    """'18.03.2026 20:15 İST' → '18.03.2026'"""
    try:
        return time_str.split(" ")[0]
    except Exception:
        return ""

def parse_ist_date(time_str):
    """'18.03.2026 20:15 İST' → datetime"""
    try:
        return datetime.strptime(time_str[:16], "%d.%m.%Y %H:%M")
    except Exception:
        return None

def loss_reason_analysis(losses):
    """Kayıplı işlemlerin neden kaybedildiğini analiz eder."""
    reasons = {}
    for t in losses:
        r = t.get("reason", "BİLİNMEYEN")
        reasons[r] = reasons.get(r, 0) + 1

    lines = []
    for reason, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
        pct = cnt / len(losses) * 100
        if "STOP LOSS" in reason:
            aciklama = "Fiyat stop seviyesine indi"
        elif "MACD" in reason:
            aciklama = "MACD tersine döndü"
        elif "RSI" in reason:
            aciklama = "RSI aşırı alım/satım"
        elif "EMA" in reason:
            aciklama = "Fiyat EMA altına/üstüne geçti"
        else:
            aciklama = reason
        lines.append(f"  • {aciklama}: {cnt} işlem (%{pct:.0f})")

    return "\n".join(lines)

# ========== ANA RAPOR ==========

def build_report(trades, capital_snapshot, tarih, is_sample=False):
    if not trades:
        return f"📊 <b>Günlük Rapor — {tarih}</b>\n━━━━━━━━━━━━━━━━━━━━\nℹ️ Bu gün hiç işlem kapanmadı."

    wins   = [t for t in trades if t["pnl_usdt"] > 0]
    losses = [t for t in trades if t["pnl_usdt"] <= 0]
    longs  = [t for t in trades if t["direction"] == "LONG"]
    shorts = [t for t in trades if t["direction"] == "SHORT"]

    stops  = [t for t in trades if t["reason"] == "STOP LOSS"]
    tps    = [t for t in trades if t["reason"] == "TAKE PROFIT"]
    sigs   = [t for t in trades if "SİNYALİ" in t.get("reason", "")]

    total      = len(trades)
    winrate    = len(wins) / total * 100
    day_pnl    = sum(t["pnl_usdt"] for t in trades)
    day_pnl_pct = day_pnl / INITIAL_CAPITAL * 100
    avg_win    = sum(t["pnl_usdt"] for t in wins)   / len(wins)   if wins   else 0
    avg_loss   = sum(t["pnl_usdt"] for t in losses) / len(losses) if losses else 0

    long_wr  = len([t for t in longs  if t["pnl_usdt"] > 0]) / len(longs)  * 100 if longs  else 0
    short_wr = len([t for t in shorts if t["pnl_usdt"] > 0]) / len(shorts) * 100 if shorts else 0

    best  = max(trades, key=lambda x: x["pnl_usdt"])
    worst = min(trades, key=lambda x: x["pnl_usdt"])

    cap_emoji   = "💚" if capital_snapshot >= INITIAL_CAPITAL else "🔴"
    pnl_emoji   = "📈" if day_pnl >= 0 else "📉"
    wr_emoji    = "🟢" if winrate >= 50 else "🟡" if winrate >= 35 else "🔴"
    sample_note = "  <i>(Tüm zamanlar örnek raporu)</i>" if is_sample else ""

    msg = (
        f"📅 <b>Günlük Rapor — {tarih}</b>{sample_note}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{cap_emoji} Sermaye      : <b>{capital_snapshot:.2f} USDT</b>\n"
        f"{pnl_emoji} Günlük PnL   : <b>{day_pnl:+.2f} USDT</b> ({day_pnl_pct:+.1f}%)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 Toplam İşlem : <b>{total}</b>\n"
        f"{wr_emoji} Winrate       : <b>{winrate:.1f}%</b>  "
        f"(✅{len(wins)} kâr / 🔴{len(losses)} zarar)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 LONG  : {len(longs)} işlem  |  WR: {long_wr:.0f}%\n"
        f"📉 SHORT : {len(shorts)} işlem  |  WR: {short_wr:.0f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Take Profit  : {len(tps)}\n"
        f"🛑 Stop Loss    : {len(stops)}\n"
        f"📤 Sinyal Çıkış : {len(sigs)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Ort. Kâr     : +{avg_win:.3f} USDT\n"
        f"💸 Ort. Zarar   : {avg_loss:.3f} USDT\n"
        f"🏆 En İyi       : {best['symbol']} {best['pnl_usdt']:+.2f} USDT\n"
        f"💀 En Kötü      : {worst['symbol']} {worst['pnl_usdt']:+.2f} USDT\n"
    )

    if losses:
        msg += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔍 <b>Zararlı İşlem Analizi</b>\n"
            f"{loss_reason_analysis(losses)}\n"
        )

    return msg


def run(sample_all=False):
    if not os.path.exists(TRADES_FILE):
        print("Trades dosyası bulunamadı.")
        return

    with open(TRADES_FILE) as f:
        data = json.load(f)

    all_trades = data.get("closed", [])
    capital    = data.get("capital", INITIAL_CAPITAL)

    if sample_all:
        # Tüm işlemleri örnek olarak göster
        tarih = "16.03–18.03.2026"
        report = build_report(all_trades, capital, tarih, is_sample=True)
        tg_send(report)
        print(f"✅ Örnek rapor gönderildi — {len(all_trades)} işlem")
        return

    # Bir önceki günün İST tarihini hesapla
    now_utc   = datetime.now(timezone.utc)
    ist_now   = now_utc + timedelta(hours=3)
    yesterday = (ist_now - timedelta(days=1)).strftime("%d.%m.%Y")

    day_trades = [t for t in all_trades if ist_date(t.get("exit_time", "")) == yesterday]

    report = build_report(day_trades, capital, yesterday)
    tg_send(report)
    print(f"✅ Rapor gönderildi — {yesterday}, {len(day_trades)} işlem")


if __name__ == "__main__":
    sample = "--sample" in sys.argv or "--all" in sys.argv
    run(sample_all=sample)

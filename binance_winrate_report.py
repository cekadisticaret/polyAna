#!/usr/bin/env python3
"""
Binance Trader — Win Rate Analiz Raporu
Cron: 0 */6 * * * cd /root/aiProject && python3 binance_winrate_report.py >> /tmp/binance_winrate_report.log 2>&1
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone

try:
    from binance_config import TG_BOT_TOKEN, TG_CHAT_ID
except ImportError:
    TG_BOT_TOKEN = TG_CHAT_ID = ""

STATE_FILE = os.path.join(os.path.dirname(__file__), "binance_state.json")
INITIAL_CAPITAL = 200.0

def tg_send(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("TG config yok")
        return
    try:
        url  = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception as e:
        print(f"TG hata: {e}")

def now_str():
    now   = datetime.now(timezone.utc)
    ist_h = (now.hour + 3) % 24
    return f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')} İST"

def wr(trades):
    if not trades:
        return 0.0
    return round(len([t for t in trades if t.get("pnl_pct", 0) > 0]) / len(trades) * 100, 1)

def bar(pct, width=10):
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def analyze():
    if not os.path.exists(STATE_FILE):
        tg_send(f"📊 <b>Win Rate Analizi</b> | {now_str()}\nℹ️ State dosyası bulunamadı.")
        return

    with open(STATE_FILE) as f:
        state = json.load(f)

    trades = state.get("closed", [])

    try:
        from binance_api import get_balance
        _, total = get_balance()
        capital = total
    except Exception:
        capital = INITIAL_CAPITAL

    if len(trades) < 5:
        tg_send(
            f"📊 <b>Win Rate Analizi</b> | {now_str()}\n"
            f"ℹ️ Henüz yeterli işlem yok ({len(trades)} / min 5)"
        )
        return

    # ── Pencere win rate ──
    wr_all = wr(trades)
    wr_20  = wr(trades[-20:]) if len(trades) >= 20 else wr(trades)
    wr_10  = wr(trades[-10:]) if len(trades) >= 10 else wr(trades)
    wr_5   = wr(trades[-5:])

    # ── Trend ──
    diff = wr_5 - wr_all
    if diff >= 12:
        trend_label = "📈 Yükseliyor"
        trend_emoji = "🟢"
    elif diff <= -12:
        trend_label = "📉 Düşüyor"
        trend_emoji = "🔴"
    else:
        trend_label = "➡️ Stabil"
        trend_emoji = "🟡"

    # ── Yön bazlı ──
    longs  = [t for t in trades if t.get("direction") == "LONG"]
    shorts = [t for t in trades if t.get("direction") == "SHORT"]
    wr_l   = wr(longs)
    wr_s   = wr(shorts)

    # ── Çıkış bazlı ──
    stops = [t for t in trades if "STOP LOSS" in str(t.get("reason", ""))]
    tps   = [t for t in trades if "TAKE PROFIT" in str(t.get("reason", ""))]
    exits = [t for t in trades if t not in stops and t not in tps]

    # ── Sembol bazlı (≥3 işlem) ──
    sym_map = {}
    for t in trades:
        sym_map.setdefault(t.get("symbol", "?"), []).append(t)
    sym_stats = sorted(
        [(s, wr(ts), len(ts)) for s, ts in sym_map.items() if len(ts) >= 3],
        key=lambda x: x[1], reverse=True
    )

    # ── PnL ──
    total_pnl = round(sum(t.get("pnl_usdt", 0) for t in trades), 2)
    roi       = round((capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2)
    avg_win   = round(sum(t["pnl_pct"] for t in trades if t.get("pnl_pct", 0) > 0) /
                      max(1, len([t for t in trades if t.get("pnl_pct", 0) > 0])), 2)
    avg_loss  = round(sum(t["pnl_pct"] for t in trades if t.get("pnl_pct", 0) <= 0) /
                      max(1, len([t for t in trades if t.get("pnl_pct", 0) <= 0])), 2)

    cap_emoji = "💚" if capital >= INITIAL_CAPITAL else "🔴"

    msg = (
        f"📊 <b>Win Rate Analizi</b> | {now_str()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{cap_emoji} Sermaye  : <b>{capital:.2f} USDT</b>  ({'+' if roi>=0 else ''}{roi}%)\n"
        f"📈 Toplam PnL : {'+' if total_pnl>=0 else ''}{total_pnl:.2f} USDT\n"
        f"📊 Ort. Kâr  : %{avg_win}  |  Ort. Zarar: %{avg_loss}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Win Rate — Pencereler</b>\n"
        f"   Genel  ({len(trades):3d} işlem): <b>%{wr_all:5.1f}</b>  {bar(wr_all)}\n"
        f"   Son 20            : %{wr_20:5.1f}  {bar(wr_20)}\n"
        f"   Son 10            : %{wr_10:5.1f}  {bar(wr_10)}\n"
        f"   Son  5            : %{wr_5:5.1f}  {bar(wr_5)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{trend_emoji} <b>Trend: {trend_label}</b>  (son5 - genel = {diff:+.1f}%)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 LONG  : %{wr_l}  ({len(longs)} işlem)\n"
        f"📉 SHORT : %{wr_s}  ({len(shorts)} işlem)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ TP     : {len(tps)}\n"
        f"🛑 SL     : {len(stops)}\n"
        f"🚪 Sinyal : {len(exits)}\n"
    )

    if sym_stats:
        best  = sym_stats[:3]
        worst = sym_stats[-3:][::-1] if len(sym_stats) > 3 else []
        msg += "━━━━━━━━━━━━━━━━━━━━\n🏆 <b>En İyi Semboller</b>\n"
        for s, w, cnt in best:
            msg += f"   {s:<12} %{w:.0f}  ({cnt} işlem)\n"
        if worst:
            msg += "⚠️ <b>En Kötü Semboller</b>\n"
            for s, w, cnt in worst:
                msg += f"   {s:<12} %{w:.0f}  ({cnt} işlem)\n"

    tg_send(msg)
    print(f"Win rate raporu gönderildi | {now_str()}")

if __name__ == "__main__":
    analyze()

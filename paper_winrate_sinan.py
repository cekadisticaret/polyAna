"""
paper_trader_sinan.py — 2 saatlik win rate analiz raporu.
Genel, pencere bazlı, yön bazlı ve sembol bazlı win rate + trend gönderir.
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BOT_TOKEN   = "8666668553:AAFe2C6SWfGQfTnkaly_sAqOCPSuHAWyluo"
CHAT_ID     = "830754964"
TRADES_FILE = os.path.join(os.path.dirname(__file__), "paper_trades_sinan.json")
START_CAP   = 200.0

def tg_send(text):
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception:
        pass

def now_str():
    now   = datetime.now(timezone.utc)
    ist_h = (now.hour + 3) % 24
    return f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')} İST"

def wr(trades):
    if not trades:
        return 0.0
    return round(len([t for t in trades if t["pnl_pct"] > 0]) / len(trades) * 100, 1)

def bar(pct, width=10):
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def analyze():
    if not os.path.exists(TRADES_FILE):
        tg_send(f"📊 <b>Win Rate Analizi</b> | {now_str()}\nℹ️ Trades dosyası bulunamadı.")
        return

    with open(TRADES_FILE) as f:
        data = json.load(f)

    trades  = data.get("closed", [])
    capital = data.get("capital", START_CAP)

    if len(trades) < 5:
        tg_send(
            f"📊 <b>Win Rate Analizi</b> | {now_str()}\n"
            f"ℹ️ Henüz yeterli işlem yok ({len(trades)} / min 5)"
        )
        return

    # ── Pencere win rate ──
    wr_all  = wr(trades)
    wr_20   = wr(trades[-20:]) if len(trades) >= 20 else wr(trades)
    wr_10   = wr(trades[-10:]) if len(trades) >= 10 else wr(trades)
    wr_5    = wr(trades[-5:])

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
    stops = [t for t in trades if t.get("reason") == "STOP LOSS"]
    tps   = [t for t in trades if t.get("reason") == "TAKE PROFIT"]
    exits = [t for t in trades if t.get("reason") not in ("STOP LOSS", "TAKE PROFIT")]

    # ── Sembol bazlı (≥3 işlem) ──
    sym_map = {}
    for t in trades:
        sym_map.setdefault(t.get("symbol", "?"), []).append(t)
    sym_stats = sorted(
        [(s, wr(ts), len(ts)) for s, ts in sym_map.items() if len(ts) >= 3],
        key=lambda x: x[1], reverse=True
    )

    # ── PnL ──
    total_pnl = round(sum(t["pnl_usdt"] for t in trades), 2)
    roi       = round((capital - START_CAP) / START_CAP * 100, 2)
    avg_win   = round(sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0) /
                      max(1, len([t for t in trades if t["pnl_pct"] > 0])), 2)
    avg_loss  = round(sum(t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0) /
                      max(1, len([t for t in trades if t["pnl_pct"] <= 0])), 2)

    cap_emoji = "💚" if capital >= START_CAP else "🔴"

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
        best = sym_stats[:3]
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

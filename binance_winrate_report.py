#!/usr/bin/env python3
"""
Binance Trader — 6 Saatlik Winrate Raporu
Cron: 0 */6 * * * cd /root/aiProject && python3 binance_winrate_report.py >> /tmp/binance_winrate_report.log 2>&1
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from collections import defaultdict

try:
    from binance_config import TG_BOT_TOKEN, TG_CHAT_ID
except ImportError:
    TG_BOT_TOKEN = TG_CHAT_ID = ""

STATE_FILE = os.path.join(os.path.dirname(__file__), "binance_state.json")

# ========== TELEGRAM ==========

def tg_send(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("TG config yok")
        return
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8)
    except Exception as e:
        print(f"TG hata: {e}")

# ========== HESAPLAMALAR ==========

def wr(trades):
    if not trades:
        return 0.0, 0, 0
    wins = [t for t in trades if t.get("pnl_pct", 0) > 0]
    return len(wins) / len(trades) * 100, len(wins), len(trades) - len(wins)

def pnl_sum(trades):
    return sum(t.get("pnl_usdt", 0) for t in trades)

def avg_win_loss(trades):
    wins = [t.get("pnl_usdt", 0) for t in trades if t.get("pnl_pct", 0) > 0]
    losses = [t.get("pnl_usdt", 0) for t in trades if t.get("pnl_pct", 0) <= 0]
    avg_w = sum(wins) / len(wins) if wins else 0
    avg_l = sum(losses) / len(losses) if losses else 0
    return avg_w, avg_l

def streak(trades):
    """Mevcut kazanma/kaybetme serisi"""
    if not trades:
        return 0, ""
    rev = list(reversed(trades))
    is_win = rev[0].get("pnl_pct", 0) > 0
    count = 0
    for t in rev:
        if (t.get("pnl_pct", 0) > 0) == is_win:
            count += 1
        else:
            break
    return count, "kazanç" if is_win else "kayıp"

def parse_ist(time_str):
    try:
        return datetime.strptime(time_str.replace(" İST", ""), "%d.%m.%Y %H:%M")
    except Exception:
        return None

# ========== ANA RAPOR ==========

def run():
    if not os.path.exists(STATE_FILE):
        print("binance_state.json bulunamadı")
        return

    with open(STATE_FILE) as f:
        state = json.load(f)

    closed = state.get("closed", [])
    if not closed:
        tg_send("📊 <b>Binance WR Raporu</b>\nHenüz kapanan işlem yok.")
        return

    now_ist = datetime.now(timezone.utc) + timedelta(hours=3)
    now_naive = now_ist.replace(tzinfo=None)

    # Zaman dilimleri
    son24h = [t for t in closed if parse_ist(t.get("exit_time", "")) and
              (now_naive - parse_ist(t["exit_time"])).total_seconds() < 86400]
    son10   = closed[-10:]
    son20   = closed[-20:]

    # Genel istatistikler
    wr_all, w_all, l_all = wr(closed)
    wr_24, w_24, l_24     = wr(son24h)
    wr_10, w_10, l_10     = wr(son10)
    pnl_all  = pnl_sum(closed)
    pnl_24   = pnl_sum(son24h)
    avg_w, avg_l = avg_win_loss(closed)
    rr = abs(avg_w / avg_l) if avg_l != 0 else 0

    # LONG / SHORT ayrımı
    longs  = [t for t in closed if t.get("direction") == "LONG"]
    shorts = [t for t in closed if t.get("direction") == "SHORT"]
    wr_long,  wl, ll = wr(longs)
    wr_short, ws, ls = wr(shorts)

    # Seri
    str_cnt, str_type = streak(closed)

    # Mevcut bakiye
    balance = state.get("peak_balance", 0)
    positions = state.get("positions", {})
    open_count = len(positions)

    # Sembol bazlı WR (en az 3 işlem olanlar)
    sym_stats = defaultdict(list)
    for t in closed:
        sym_stats[t.get("symbol", "?")].append(t)
    sym_wr = []
    for sym, trades in sym_stats.items():
        if len(trades) >= 3:
            w_r, w_c, l_c = wr(trades)
            sym_wr.append((sym, w_r, len(trades), pnl_sum(trades)))
    sym_wr.sort(key=lambda x: -x[1])

    # Win prob doğruluğu
    wp_trades = [t for t in closed if t.get("win_prob") is not None]
    wp_line = ""
    if wp_trades:
        avg_wp  = sum(t["win_prob"] for t in wp_trades) / len(wp_trades)
        wr_real, _, _ = wr(wp_trades)
        wp_line = f"\n🎰 WinProb ort: %{avg_wp:.0f} → Gerçek: %{wr_real:.0f}"

    # Son 6 saatte kapanan
    son6h = [t for t in closed if parse_ist(t.get("exit_time", "")) and
             (now_naive - parse_ist(t["exit_time"])).total_seconds() < 21600]
    son6h_line = ""
    if son6h:
        wr_6, w6, l6 = wr(son6h)
        pnl_6 = pnl_sum(son6h)
        son6h_line = (
            f"\n⏱ <b>Son 6 Saat</b>\n"
            f"  İşlem: {len(son6h)} | WR: %{wr_6:.0f} ({w6}K/{l6}Z) | PnL: {pnl_6:+.2f}$"
        )

    # Rapor mesajı
    lines = [
        f"📊 <b>Binance WR Raporu — {now_ist.strftime('%d.%m.%Y %H:%M')} İST</b>",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"💼 Bakiye: <b>{balance:.2f} USDT</b>  |  Açık: {open_count}",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"📈 <b>Winrate</b>",
        f"  Tüm ({len(closed)})  : %{wr_all:.1f} ({w_all}K / {l_all}Z)",
        f"  Son 20        : %{wr(son20)[0]:.1f}",
        f"  Son 10        : %{wr_10:.1f} ({w_10}K / {l_10}Z)",
        f"  Son 24 saat   : %{wr_24:.1f} ({w_24}K / {l_24}Z)",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>PnL</b>",
        f"  Toplam  : {pnl_all:+.2f} USDT",
        f"  Son 24h : {pnl_24:+.2f} USDT",
        f"  Ort. Kazanç : +{avg_w:.2f}$ | Ort. Kayıp: {avg_l:.2f}$",
        f"  R:R     : 1:{rr:.2f}",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🧭 <b>Yön Analizi</b>",
        f"  LONG  ({len(longs)})  : %{wr_long:.1f} WR",
        f"  SHORT ({len(shorts)}) : %{wr_short:.1f} WR",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🔥 Mevcut seri: {str_cnt} {str_type}",
        wp_line,
    ]

    if son6h_line:
        lines.append(son6h_line)

    if sym_wr:
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🏆 <b>Sembol WR (≥3 işlem)</b>")
        for sym, w_r, cnt, sym_pnl in sym_wr[:5]:
            bar = "🟢" if w_r >= 60 else ("🟡" if w_r >= 40 else "🔴")
            lines.append(f"  {bar} {sym}: %{w_r:.0f} ({cnt} işlem, {sym_pnl:+.2f}$)")

    # Son 5 işlem özeti
    lines.append(f"━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🗓 <b>Son 5 İşlem</b>")
    for t in closed[-5:]:
        ok = "✅" if t.get("pnl_pct", 0) > 0 else "❌"
        dir_ = "L" if t.get("direction") == "LONG" else "S"
        sym  = t.get("symbol", "?").replace("USDT", "")
        pnl  = t.get("pnl_usdt", 0)
        pct  = t.get("pnl_pct", 0)
        lines.append(f"  {ok} [{dir_}] {sym} {pnl:+.2f}$ (%{pct:.1f})")

    msg = "\n".join(l for l in lines if l != "")
    tg_send(msg)

    print(f"✅ Winrate raporu gönderildi — {len(closed)} işlem, WR %{wr_all:.1f}, PnL {pnl_all:+.2f}$")

if __name__ == "__main__":
    run()

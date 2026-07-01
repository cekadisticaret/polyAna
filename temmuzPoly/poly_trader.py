"""
Poly Sanal Trader
Saat başı çalışır: açık pozisyonları kapatır, yeni tahminlere bakıp $10/işlem açar,
sonuçları Telegram'a bildirir.

Algoritma: poly_predictor_analysis.py — hiç değiştirilmedi, olduğu gibi import edilir.
Sanal bütçe: $300 başlangıç, her işlem $10.
Birikim: symbol + saat bazlı başarı oranı zamanla artar.
"""
import asyncio
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_TZ_TR = ZoneInfo("Europe/Istanbul")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_predictor_analysis import predict, _fetch_klines

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"

_DIR          = os.path.dirname(os.path.abspath(__file__))
STATE_FILE    = os.path.join(_DIR, "trader_state.json")
HISTORY_FILE  = os.path.join(_DIR, "trader_history.json")

INITIAL_BALANCE = 300.0
TRADE_AMOUNT    = 10.0
SYMBOLS         = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


# ── State ─────────────────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history: list) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


# ── İstatistik ────────────────────────────────────────────────
def get_stats(history: list, symbol: str, hour_tr: int) -> tuple[int, int]:
    """symbol + saat (İST) bazlı kazanma istatistiği döner: (wins, total)."""
    trades = [t for t in history if t["symbol"] == symbol and t.get("entry_hour_tr") == hour_tr]
    wins   = sum(1 for t in trades if t["win"])
    return wins, len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    """Symbol bazlı genel istatistik: (wins, total)."""
    trades = [t for t in history if t["symbol"] == symbol]
    wins   = sum(1 for t in trades if t["win"])
    return wins, len(trades)


def win_rate_str(wins: int, total: int) -> str:
    if total == 0:
        return "ilk veri"
    return f"%{wins/total*100:.0f} ({wins}/{total})"


# ── Telegram ─────────────────────────────────────────────────
def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}")


# ── Ana akış ──────────────────────────────────────────────────
async def run() -> None:
    now      = datetime.now(timezone.utc)
    now_tr   = now.astimezone(_TZ_TR)
    hour_tr  = now_tr.hour
    time_str = now_tr.strftime("%d.%m.%Y %H:%M") + " İST"

    state   = load_state()
    history = load_history()

    # ── 1. Açık pozisyonları kapat ────────────────────────────
    closed_lines  = []
    for pos in list(state["open_positions"]):
        klines = await _fetch_klines(pos["symbol"], "1h", 2)
        if not klines:
            continue
        current_price = klines[-1]["close"]

        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        actual = "UP" if current_price >= entry else "DOWN"
        win    = (pred == actual)
        pnl    = TRADE_AMOUNT if win else -TRADE_AMOUNT

        state["balance"]   = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        history.append({
            "symbol":        pos["symbol"],
            "predicted_dir": pred,
            "actual_dir":    actual,
            "win":           win,
            "entry_price":   entry,
            "exit_price":    current_price,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos["entry_hour_tr"],
            "exit_time_tr":  now_tr.isoformat(),
            "pnl":           pnl,
        })

        icon  = "✅" if win else "❌"
        name  = pos["symbol"].replace("USDT", "")
        pct   = (current_price - entry) / entry * 100
        closed_lines.append(
            f"{icon} <b>{name}</b> {pred}  "
            f"{entry:.2f}→{current_price:.2f} ({pct:+.2f}%)  "
            f"<b>{'+'if win else ''}{pnl:.0f}$</b>"
        )

    state["open_positions"] = []

    # ── 2. Yeni tahminler + pozisyon aç ───────────────────────
    new_lines = []
    for sym in SYMBOLS:
        pred_obj = await predict(sym)
        if pred_obj is None:
            continue

        entry_price = pred_obj.current_price
        hour_wins, hour_total = get_stats(history, sym, hour_tr)
        sym_wins,  sym_total  = get_symbol_stats(history, sym)
        name     = sym.replace("USDT", "")
        conf     = max(pred_obj.prob_up, pred_obj.prob_down) * 100
        dir_icon = "📈" if pred_obj.predicted_dir == "UP" else "📉"

        state["open_positions"].append({
            "symbol":        sym,
            "predicted_dir": pred_obj.predicted_dir,
            "entry_price":   entry_price,
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "amount":        TRADE_AMOUNT,
        })

        new_lines.append(
            f"{dir_icon} <b>{name}</b> {pred_obj.predicted_dir}  "
            f"konf:%{conf:.0f}  giriş:{entry_price:.2f}\n"
            f"   🕐 {hour_tr:02d}:00 İST başarı: {win_rate_str(hour_wins, hour_total)}  "
            f"| genel: {win_rate_str(sym_wins, sym_total)}"
        )

    save_state(state)
    save_history(history)

    # ── 3. Telegram bildirimi ─────────────────────────────────
    sep   = "━" * 26
    parts = [f"🤖 <b>POLY TRADER</b> — {time_str}\n{sep}"]

    if closed_lines:
        parts.append("\n📌 <b>KAPANAN İŞLEMLER</b>")
        parts.extend(closed_lines)

    if new_lines:
        parts.append("\n🆕 <b>YENİ İŞLEMLER</b>")
        parts.extend(new_lines)
    else:
        parts.append("\n⏸ <i>Bu saatte sinyal yok — işlem açılmadı.</i>")

    total_pnl  = state.get("total_pnl", 0.0)
    pnl_icon   = "🟢" if total_pnl >= 0 else "🔴"
    open_count = len(state["open_positions"])
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel_oran = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"

    parts.append(
        f"\n{sep}\n"
        f"💰 Bakiye: <b>${state['balance']:.2f}</b>  "
        f"{pnl_icon} Toplam P&L: <b>{'+'if total_pnl>=0 else ''}{total_pnl:.2f}$</b>\n"
        f"📂 Açık: {open_count}  |  Toplam: {closed_all} işlem  |  Genel: {genel_oran}"
    )

    tg_send("\n".join(parts))
    print(f"[POLY TRADER] {time_str} — kapatılan:{len(closed_lines)} yeni:{len(new_lines)}")


if __name__ == "__main__":
    asyncio.run(run())

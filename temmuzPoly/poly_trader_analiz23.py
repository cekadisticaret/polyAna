"""
23. ANALİZ — A4 BTC + A2 SOL hibrit sanal trader

  BTC → 4. Analiz motoru (Trend+MR+OF+Fund, |skor|≥2)
  SOL → 2. Analiz motoru (poly_predictor, fallback kapalı)

$300 sanal, işlem $20 / $30 / $40 (sembol WR).
Telegram: 5M 107 kanalı (poly_trader_5m_common)
Modlar: close / open / weekly / stats
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from poly_trader_analiz4 import analyze as a4_analyze
from poly_predictor_analysis import predict, _fetch_klines
from poly_trader_5m_common import tg_send, tg_send_photo
from pm_trader_helpers import apply_pm_quote, sanal_pnl, pm_tg_stake

_TZ_TR    = ZoneInfo("Europe/Istanbul")

STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz23_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz23_history.json")
WEEKLY_IMG   = "/tmp/poly_weekly_heatmap_analiz23.png"

INITIAL_BALANCE   = 300.0
TRADE_AMOUNT_LOW  = 20.0
TRADE_AMOUNT      = 30.0
TRADE_AMOUNT_HIGH = 40.0
SYMBOLS           = ["BTCUSDT", "SOLUSDT"]
_LABEL            = "23. ANALİZ"
_DAYS_TR          = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


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


def _wr(wins: int, total: int) -> str:
    return f"%{wins/total*100:.0f} ({wins}/{total})" if total else "veri yok"


def trade_amount(history: list, symbol: str) -> float:
    trades = [t for t in history if t.get("symbol") == symbol]
    if not trades:
        return TRADE_AMOUNT
    rate = sum(1 for t in trades if t.get("win")) / len(trades)
    if rate > 0.5:
        return TRADE_AMOUNT_HIGH
    if rate < 0.5:
        return TRADE_AMOUNT_LOW
    return TRADE_AMOUNT


def get_stats(history: list, symbol: str, hour_tr: int) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol and t.get("entry_hour_tr") == hour_tr]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


async def _btc_signal() -> dict | None:
    sig = await asyncio.to_thread(a4_analyze, "BTCUSDT")
    if not sig or not sig.get("open_ok") or not sig.get("predicted_dir"):
        score = sig.get("score", 0) if sig else 0
        print(f"[{_LABEL} open] BTCUSDT — A4 elendi (skor:{score:+d}/4)")
        return None
    return {
        "symbol": "BTCUSDT",
        "predicted_dir": sig["predicted_dir"],
        "entry_price": sig["price"],
        "source": "A4",
        "score": sig["score"],
        "votes": sig.get("votes", []),
        "labels": sig.get("labels", []),
    }


async def _sol_signal() -> dict | None:
    pred = await predict("SOLUSDT")
    if pred is None:
        print(f"[{_LABEL} open] SOLUSDT — A2 sinyal yok (BEKLE)")
        return None
    try:
        klines = await _fetch_klines("SOLUSDT", "1h", 3)
        entry_price = klines[-2]["close"] if klines and len(klines) >= 2 else pred.current_price
    except Exception:
        entry_price = pred.current_price
    conf = max(pred.prob_up, pred.prob_down)
    return {
        "symbol": "SOLUSDT",
        "predicted_dir": pred.predicted_dir,
        "entry_price": entry_price,
        "source": "A2",
        "conf": conf,
        "ind_rsi_vote": "UP" if pred.rsi < 50 else "DOWN",
        "ind_rsi_val": round(pred.rsi, 1),
        "ind_macd_vote": "UP" if pred.macd_bull else "DOWN",
        "ind_ema_vote": (
            "UP" if "YUKARI" in pred.trend.upper()
            else "DOWN" if "AŞAĞI" in pred.trend.upper()
            else "NEUTRAL"
        ),
    }


async def run_close() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    state = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[{_LABEL} close] {saat} İST — açık pozisyon yok")
        return

    lines, toplam_pnl, failed_pos = [], 0.0, []

    for pos in list(state["open_positions"]):
        klines = await _fetch_klines(pos["symbol"], "1h", 2)
        if not klines:
            failed_pos.append(pos)
            continue
        current_price = klines[-1]["close"]
        entry, pred = pos["entry_price"], pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        actual = "UP" if current_price >= entry else "DOWN"
        win = pred == actual
        pnl = sanal_pnl(pos, win)
        toplam_pnl += pnl
        state["balance"] = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        rec = {
            "symbol": pos["symbol"],
            "predicted_dir": pred,
            "actual_dir": actual,
            "win": win,
            "entry_price": entry,
            "exit_price": current_price,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos["entry_hour_tr"],
            "entry_dow": pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "amount": amount,
            "exit_time_tr": now_tr.isoformat(),
            "pnl": pnl,
            "signal_source": pos.get("signal_source"),
        }
        for k in ("score", "conf", "ind_rsi_vote", "ind_macd_vote", "ind_ema_vote",
                  "pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)

        icon = "✅" if win else "❌"
        name = pos["symbol"].replace("USDT", "")
        pct = (current_price - entry) / entry * 100
        src = pos.get("signal_source", "?")
        stake = pm_tg_stake(pos) or f"💵 ${amount:.0f}"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)\n"
            f"   {stake}  net {'+' if pnl >= 0 else ''}{pnl:.2f}$  [{src}]"
        )

    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)
    if not lines:
        return

    total_pnl = state.get("total_pnl", 0.0)
    closed_all, win_all = len(history), sum(1 for t in history if t["win"])
    genel = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    sep = "━" * 26
    tg_send(
        f"{sep}\n"
        f"🏁 <b>{_LABEL} — {int(saat[:2]):02d}:00 Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+' if toplam_pnl >= 0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{'🟢' if total_pnl >= 0 else '🔴'} Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all})\n"
        f"{sep}"
    )
    print(f"[{_LABEL} close] {saat} İST — {len(lines)} pozisyon kapatıldı")


async def run_open() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    hour_tr, dow = now_tr.hour, now_tr.weekday()
    saat = now_tr.strftime("%H:%M")
    next_h = f"{(hour_tr + 1) % 24:02d}:00"

    state = load_state()
    history = load_history()
    opened = []

    resolvers = {"BTCUSDT": _btc_signal, "SOLUSDT": _sol_signal}
    for sym in SYMBOLS:
        if any(p["symbol"] == sym for p in state["open_positions"]):
            continue
        sig = await resolvers[sym]()
        if not sig:
            continue

        amount = trade_amount(history, sym)
        pos = {
            "symbol": sym,
            "predicted_dir": sig["predicted_dir"],
            "entry_price": sig["entry_price"],
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "entry_dow": dow,
            "entry_is_weekend": dow >= 5,
            "amount": amount,
            "signal_source": sig["source"],
        }
        if sig["source"] == "A4":
            pos.update({"score": sig["score"], "votes": sig.get("votes", []), "labels": sig.get("labels", [])})
        else:
            pos.update({
                "conf": sig.get("conf"),
                "ind_rsi_vote": sig.get("ind_rsi_vote"),
                "ind_rsi_val": sig.get("ind_rsi_val"),
                "ind_macd_vote": sig.get("ind_macd_vote"),
                "ind_ema_vote": sig.get("ind_ema_vote"),
            })

        apply_pm_quote(pos, sym, sig["predicted_dir"], amount, now)
        state["open_positions"].append(pos)
        opened.append((sig, amount))

    save_state(state)

    if not opened:
        print(f"[{_LABEL} open] {saat} İST — işlem yok")
        return

    lines = []
    for sig, amount in opened:
        sym = sig["symbol"]
        name = sym.replace("USDT", "")
        dir_icon = "📈" if sig["predicted_dir"] == "UP" else "📉"
        dir_tr = "YÜKSELİR" if sig["predicted_dir"] == "UP" else "DÜŞER"
        hw, ht = get_stats(history, sym, hour_tr)
        sw, st = get_symbol_stats(history, sym)
        if sig["source"] == "A4":
            detail = f"skor:{sig['score']:+d}/4 (A4)"
        else:
            detail = f"konf:%{sig['conf']*100:.0f} (A2)"
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  {detail}  giriş:{sig['entry_price']:.2f}  💵{amount:.0f}$\n"
            f"   🕐 {hour_tr:02d}:00→{next_h}  başarı: {_wr(hw, ht)}  |  genel: {_wr(sw, st)}"
        )

    at_risk = sum(p.get("pm_spent") or p.get("amount", TRADE_AMOUNT) for p in state["open_positions"])
    bakiye = round(state["balance"] - at_risk, 2)
    toplam = round(state["balance"], 2)
    sep = "━" * 26
    tg_send(
        f"{sep}\n"
        f"🆕 <b>{_LABEL} — {saat} - {next_h}</b>  (A4 BTC + A2 SOL)\n"
        + "\n".join(lines) + "\n"
        f"{sep}\n"
        f"💰 Bakiye: ${bakiye:.2f}  |  📂 Açık: ${at_risk:.0f}  |  Toplam: ${toplam:.2f}\n"
        f"<i>Tutar: $20/$30/$40 (sembol WR)</i>\n"
        f"{sep}"
    )
    print(f"[{_LABEL} open] {saat} İST — {len(opened)} yeni işlem açıldı")


def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history, state = load_history(), load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    grid_w, grid_n = [[0] * 24 for _ in range(7)], [[0] * 24 for _ in range(7)]
    sym_names = [s.replace("USDT", "") for s in SYMBOLS]
    grid_sym = {s: {"w": [[0] * 24 for _ in range(7)], "n": [[0] * 24 for _ in range(7)]} for s in sym_names}

    for t in history:
        d, h = t.get("entry_dow"), t.get("entry_hour_tr")
        if d is None or h is None:
            continue
        grid_n[d][h] += 1
        if t["win"]:
            grid_w[d][h] += 1
        sn = t["symbol"].replace("USDT", "")
        if sn in grid_sym:
            grid_sym[sn]["n"][d][h] += 1
            if t["win"]:
                grid_sym[sn]["w"][d][h] += 1

    rate = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            if grid_n[d][h] >= 3:
                rate[d][h] = grid_w[d][h] / grid_n[d][h]

    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")
    cmap = mcolors.LinearSegmentedColormap.from_list("a23", [(0, "#4a3000"), (0.5, "#fff176"), (1, "#00e676")], N=256)
    cmap.set_bad(color="#141820")
    ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=9, color="#b0bec5")
    total, wins = len(history), sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    ax.set_title(
        f"{_LABEL} — Haftalık ({now_tr.strftime('%d.%m.%Y')})  |  {total} işlem  {genel}  |  ${state.get('balance', INITIAL_BALANCE):.0f}",
        color="#4fc3f7", fontsize=10, fontweight="bold",
    )
    plt.tight_layout()
    plt.savefig(WEEKLY_IMG, dpi=120, facecolor=fig.get_facecolor())
    plt.close()
    tg_send_photo(WEEKLY_IMG, f"{_LABEL} haftalık ısı haritası")


def run_stats() -> None:
    history, state = load_history(), load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if not history:
        tg_send(f"📊 <b>{_LABEL} STATS</b>\nHenüz veri yok.")
        return
    total, wins = len(history), sum(1 for t in history if t["win"])
    pnl = state.get("total_pnl", 0.0)
    parts = [
        f"📊 <b>{_LABEL} İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"Toplam: {total}  |  {_wr(wins, total)}",
        f"P&L: {'+' if pnl >= 0 else ''}{pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
        f"Tutar: $20/$30/$40",
    ]
    for sym in SYMBOLS:
        s = [t for t in history if t["symbol"] == sym]
        if s:
            parts.append(f"📌 {sym.replace('USDT','')} ({s[0].get('signal_source','?')}): {_wr(sum(1 for t in s if t['win']), len(s))}")
    tg_send("\n".join(parts))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        asyncio.run(run_open())

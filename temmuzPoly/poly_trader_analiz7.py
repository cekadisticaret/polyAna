"""
7. ANALİZ — Gelişmiş 6-Algo Konsensüs (1 Saatlik, Sanal)

btc_1h_analiz7_algo: A1+HMA + Trend+ST + MR + OF v2 + Volume + Ichimoku (≥2/6, momentum kapalı)
Sembol: BTCUSDT
Sanal bütçe: $300  |  İşlem: $12/$16/$20 (sembol WR, 1. Analiz mantığı)

Modlar: close / open / weekly / stats
Cron: 0 * * * * close  |  5 * * * * open
"""

import html
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btc_1h_analiz7_algo import analyze, fetch_klines, TOTAL_ALGOS
from pm_trader_helpers import (
    apply_pm_quote, sanal_close_balance, pm_tg_stake, pm_history_extras,
    symbol_wr_amount, SANAL_INITIAL_BALANCE, SANAL_TRADE_AMOUNT,
)

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA")
CHAT_ID   = os.getenv("TELEGRAM_CHAT", "830754964")
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz7_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz7_history.json")
WEEKLY_IMG   = "/tmp/poly_analiz7_weekly_heatmap.png"

LABEL           = "7. ANALİZ"
ALGO_NAME       = "Enhanced 6-Algo 1H"
INITIAL_BALANCE = SANAL_INITIAL_BALANCE
TRADE_AMOUNT    = SANAL_TRADE_AMOUNT
SYMBOLS         = ["BTCUSDT"]
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_ENABLED        = os.getenv("ANALIZ7_ENABLED", "true").lower() in ("1", "true", "yes")


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
    if total == 0:
        return "veri yok"
    return f"%{wins / total * 100:.0f} ({wins}/{total})"


def _tg_esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def get_stats(history: list, symbol: str, hour_tr: int, dow: int | None = None) -> tuple[int, int]:
    trades = [
        t for t in history
        if t["symbol"] == symbol
        and t.get("entry_hour_tr") == hour_tr
        and (dow is None or t.get("entry_dow") == dow)
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


def tg_send(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}", file=sys.stderr)


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----Analiz7Boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"heatmap.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception as e:
        print(f"[TG photo] Hata: {e}", file=sys.stderr)


def _fetch_klines(symbol: str, limit: int = 60) -> list[dict]:
    raw = fetch_klines(symbol, "1h", limit)
    return [
        {"open": k["open"], "high": k["high"], "low": k["low"],
         "close": k["close"], "volume": k["volume"]}
        for k in raw
    ]


def analyze_symbol(symbol: str) -> dict | None:
    sig = analyze(symbol=symbol)
    if sig is None:
        return None
    klines = _fetch_klines(symbol, 60)
    entry_price = klines[-1]["open"] if klines else sig.entry_price
    return {
        "symbol": symbol,
        "direction": sig.direction,
        "entry_price": entry_price,
        "consensus": sig.consensus,
        "votes": sig.votes,
        "labels": sig.labels,
        "momentum": sig.momentum,
        "atr": sig.atr,
        "adx": sig.adx,
        "volume_ratio": sig.volume_ratio,
        "htf_trend": sig.htf_trend,
        "htf_supertrend": getattr(sig, "htf_supertrend", "NEUTRAL"),
        "supertrend": "UP" if getattr(sig, "supertrend_direction", True) else "DOWN",
        "skip_reason": sig.skip_reason,
        "raw_direction": sig.raw_direction,
    }


def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[{LABEL} close] {saat} — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        try:
            klines = _fetch_klines(pos["symbol"], 2)
            if not klines:
                failed_pos.append(pos)
                continue
            current_price = klines[-1]["close"]
        except Exception:
            failed_pos.append(pos)
            continue

        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        actual = "UP" if current_price >= entry else "DOWN"
        win    = pred == actual
        pnl    = sanal_close_balance(state, pos, win)
        toplam_pnl += pnl

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
            "entry_is_weekend": pos.get("entry_is_weekend", False),
            "amount": amount,
            "exit_time_tr": now_tr.isoformat(),
            "pnl": pnl,
            "consensus": pos.get("consensus"),
            "votes": pos.get("votes"),
            "algo": ALGO_NAME,
        }
        rec.update(pm_history_extras(pos))
        history.append(rec)

        icon = "✅" if win else "❌"
        pct  = (current_price - entry) / entry * 100 if entry else 0
        pnl_str = f"+${pnl:.2f} ({pm_tg_stake(pos)})" if win else f"-${abs(pnl):.2f}"
        lines.append(
            f"{icon} BTC {pred}  {entry:,.0f} → {current_price:,.0f} ({pct:+.2f}%)  {pnl_str}"
        )

    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    if failed_pos:
        print(f"[{LABEL} close] {saat} — fiyat alınamadı, pozisyon ertelendi")

    if not lines:
        return

    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all / closed_all * 100:.0f}" if closed_all else "—"
    saat_round = f"{int(saat[:2]):02d}:00"
    sep        = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>{LABEL} — {saat_round} Sonuçlar</b>\n"
        f"🔬 {ALGO_NAME}\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+' if toplam_pnl >= 0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[{LABEL} close] {saat} — {len(lines)} pozisyon kapatıldı")


def run_open() -> None:
    if not _ENABLED:
        print(f"[{LABEL}] devre dışı (ANALIZ7_ENABLED=false)")
        return

    now        = datetime.now(timezone.utc)
    now_tr     = now.astimezone(_TZ_TR)
    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5
    saat       = now_tr.strftime("%H:%M")
    next_h     = f"{(hour_tr + 1) % 24:02d}:00"

    state   = load_state()
    history = load_history()
    opened  = []
    skipped = []

    for sym in SYMBOLS:
        try:
            sig = analyze_symbol(sym)
        except Exception as e:
            print(f"[{LABEL}] {sym} analiz hatası: {e}", file=sys.stderr)
            continue

        name = sym.replace("USDT", "")
        if sig is None:
            skipped.append(f"⏸ {name} — veri yok")
            continue
        if sig["direction"] is None:
            reason = sig.get("skip_reason") or "Konsensüs yok"
            skipped.append(f"⏸ {name} — {_tg_esc(reason)}")
            print(f"[{LABEL}] {sym} — {reason}")
            continue

        dyn_amount = symbol_wr_amount(history, sym)
        if state["balance"] < dyn_amount:
            skipped.append(f"⏸ {name} — bakiye yetersiz")
            continue

        pos = {
            "symbol": sym,
            "predicted_dir": sig["direction"],
            "entry_price": sig["entry_price"],
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "entry_dow": dow,
            "entry_is_weekend": is_weekend,
            "amount": dyn_amount,
            "consensus": sig["consensus"],
            "votes": sig["votes"],
            "labels": sig.get("labels"),
            "algo": ALGO_NAME,
        }
        apply_pm_quote(pos, sym, sig["direction"], dyn_amount, now)
        risk = pos.get("pm_spent", dyn_amount)
        if state["balance"] < risk:
            skipped.append(f"⏸ {name} — bakiye yetersiz (PM ${risk:.2f})")
            continue
        state["open_positions"].append(pos)
        state["balance"] = round(state["balance"] - risk, 2)
        opened.append(sig)

    save_state(state)

    sep = "━" * 26
    lines = []
    for sig in opened:
        sym = sig["symbol"]
        dir_icon = "📈" if sig["direction"] == "UP" else "📉"
        dir_tr   = "YÜKSELİR" if sig["direction"] == "UP" else "DÜŞER"
        hw, ht = get_stats(history, sym, hour_tr)
        sw, st = get_symbol_stats(history, sym)
        icons = " ".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in sig.get("votes", []))
        lines.append(
            f"{dir_icon} <b>BTC {dir_tr}</b>  ({sig['consensus']}/{TOTAL_ALGOS})  {pm_tg_stake(next((p for p in state['open_positions'] if p['symbol']==sym and p.get('entry_hour_tr')==hour_tr), {'amount': TRADE_AMOUNT}))}\n"
            f"   {icons}  mom:{sig.get('momentum')} ADX:{sig.get('adx', 0):.1f} vol:{sig.get('volume_ratio', 0):.2f}x HTF:{sig.get('htf_trend')} ST:{sig.get('supertrend')}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} {_wr(hw, ht)}  |  genel {_wr(sw, st)}"
        )

    at_risk = sum(p.get("amount", TRADE_AMOUNT) for p in state["open_positions"])
    if not lines:
        print(f"[{LABEL} open] {saat} — işlem yok")
        return

    msg = (
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} → {next_h} Yeni İşlemler</b>  🔶 SANAL\n"
        + "\n".join(lines)
        + (("\n" + "\n".join(skipped)) if skipped else "")
        + f"\n{sep}\n"
        f"💰 Serbest: ${state['balance'] - at_risk:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${at_risk:.0f}  |  Toplam: ${state['balance']:.2f}\n"
        f"{sep}"
    )

    tg_send(msg)
    print(f"[{LABEL} open] {saat} — {len(opened)} yeni işlem")


def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send(f"📊 <b>{LABEL} WEEKLY</b>\nHenüz veri yok.")
        return

    grid_w = [[0] * 24 for _ in range(7)]
    grid_n = [[0] * 24 for _ in range(7)]
    for t in history:
        d, h = t.get("entry_dow"), t.get("entry_hour_tr")
        if d is None or h is None:
            continue
        grid_n[d][h] += 1
        if t["win"]:
            grid_w[d][h] += 1

    rate = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            if grid_n[d][h] >= 3:
                rate[d][h] = grid_w[d][h] / grid_n[d][h]

    fig, ax = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "gy", [("#4a3000", 0), ("#f9a825", .3), ("#388e3c", .5), ("#00e676", 1)], N=256
    )
    cmap.set_bad("#141820")
    im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=9, color="#b0bec5")

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    balance = state.get("balance", INITIAL_BALANCE)
    ax.set_title(
        f"{LABEL} — Haftalık Harita  |  {genel}  |  ${balance:.2f}",
        color="#4fc3f7", fontsize=10, fontweight="bold", pad=10,
    )
    plt.tight_layout()
    plt.savefig(WEEKLY_IMG, dpi=150, bbox_inches="tight", facecolor="#0a0e1a")
    plt.close()
    tg_send_photo(WEEKLY_IMG, f"📊 {LABEL} haftalık — {total} işlem {genel}")


def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send(f"📊 <b>{LABEL} STATS</b>\nHenüz veri yok.")
        return

    total     = len(history)
    wins_all  = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    tg_send(
        f"📊 <b>{LABEL} İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"🔬 {ALGO_NAME}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}\n"
        f"{pnl_icon} P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"Lot: $12–$20/işlem (sembol WR)  |  Başlangıç: ${INITIAL_BALANCE:.0f}"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        run_close()
    elif mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        run_open()

"""
8. ANALİZ JESSE — Saatlik Polymarket sanal (BTC + SOL + ETH)

Sinyal: Jesse GoldenCross (EMA 8/21) — analiz8_signal.py
Sanal: $300, PM gamma kotasyonu, gerçek emir yok.
Jesse çekirdeğine dokunmaz; ayrı cron betiği.

Modlar: close (:02) / open (:05) / stats
Hafta sonu: Cuma 22:00 – Pazar 18:00 İST (open atlanır)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_DIR, "..")
sys.path.insert(0, _DIR)
sys.path.insert(0, os.path.join(_ROOT, "temmuzPoly"))

from analiz8_signal import predict_pm_direction
from pm_trader_helpers import (
    apply_pm_quote,
    in_weekend_pause_tr,
    pm_tg_stake,
    sanal_pnl,
    symbol_wr_amount,
    SANAL_INITIAL_BALANCE,
)

_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

LABEL = "8. ANALİZ JESSE"
BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("TELEGRAM_LAB_BOT_TOKEN")
    or ""
)
CHAT_ID = (
    os.getenv("TELEGRAM_CHAT_ID")
    or os.getenv("TELEGRAM_CHAT")
    or os.getenv("TELEGRAM_LAB_CHAT_ID")
    or ""
)
_TZ_TR = ZoneInfo("Europe/Istanbul")
_USERDATA = os.path.join(_DIR, "storage")
STATE_FILE = os.path.join(_USERDATA, "analiz8_jesse_state.json")
HISTORY_FILE = os.path.join(_USERDATA, "analiz8_jesse_history.json")

INITIAL_BALANCE = SANAL_INITIAL_BALANCE
SYMBOLS = ["BTCUSDT", "SOLUSDT", "ETHUSDT"]


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0}


def save_state(state: dict) -> None:
    os.makedirs(_USERDATA, exist_ok=True)
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
    os.makedirs(_USERDATA, exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _wr(wins: int, total: int) -> str:
    if total == 0:
        return "veri yok"
    return f"%{wins / total * 100:.0f} ({wins}/{total})"


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


def tg_send(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[{LABEL} TG] token/chat eksik")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
        }).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=12) as r:
            r.read()
    except Exception as exc:
        print(f"[{LABEL} TG] Hata: {exc}")


async def _hour_open_price(symbol: str, fallback: float) -> float:
    from poly_predictor_analysis import _fetch_klines

    try:
        klines = await _fetch_klines(symbol, "1h", 3)
        if klines and len(klines) >= 2:
            return float(klines[-2]["close"])
    except Exception:
        pass
    return fallback


async def run_close() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")

    state = load_state()
    history = load_history()
    if not state["open_positions"]:
        print(f"[{LABEL} close] {saat} IST — acik pozisyon yok")
        return

    lines: list[str] = []
    tur_pnl = 0.0
    failed: list[dict] = []

    for pos in list(state["open_positions"]):
        from poly_predictor_analysis import _fetch_klines

        klines = await _fetch_klines(pos["symbol"], "1h", 2)
        if not klines:
            failed.append(pos)
            continue

        current = float(klines[-1]["close"])
        entry = float(pos["entry_price"])
        pred = pos["predicted_dir"]
        actual = "UP" if current >= entry else "DOWN"
        win = pred == actual
        pnl = sanal_pnl(pos, win)
        tur_pnl += pnl
        state["balance"] = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        rec = {
            "symbol": pos["symbol"],
            "predicted_dir": pred,
            "actual_dir": actual,
            "win": win,
            "entry_price": entry,
            "exit_price": current,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos["entry_hour_tr"],
            "entry_dow": pos.get("entry_dow"),
            "exit_time_tr": now_tr.isoformat(),
            "amount": pos.get("amount"),
            "pnl": pnl,
            "signal_engine": "jesse_golden_cross",
            "ind_rsi_val": pos.get("ind_rsi_val"),
            "ema_fast": pos.get("ema_fast"),
            "ema_slow": pos.get("ema_slow"),
            "golden_cross": pos.get("golden_cross"),
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)

        name = pos["symbol"].replace("USDT", "")
        icon = "✅" if win else "❌"
        pct = (current - entry) / entry * 100 if entry else 0
        stake = pm_tg_stake(pos) or f"${pos.get('amount', 0):.0f}"
        lines.append(
            f"{icon} {name} {pred}  {entry:.4g}→{current:.4g} ({pct:+.2f}%)  {stake}"
        )

    state["open_positions"] = failed
    save_state(state)
    save_history(history)

    if not lines:
        return

    total_pnl = state.get("total_pnl", 0.0)
    closed_all = len(history)
    win_all = sum(1 for t in history if t["win"])
    genel = f"%{win_all / closed_all * 100:.0f}" if closed_all else "—"
    sep = "━" * 26
    tg_send(
        f"{sep}\n"
        f"🏁 <b>{LABEL} — {int(saat[:2]):02d}:00 Sonuclar</b>  🔶 SANAL PM\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{'🟢' if total_pnl >= 0 else '🔴'} Toplam P&amp;L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all})\n"
        f"{sep}"
    )
    print(f"[{LABEL} close] {saat} IST — {len(lines)} kapandi")


async def run_open() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")

    if in_weekend_pause_tr(now_tr):
        print(f"[{LABEL} open] {saat} IST — hafta sonu duraklama")
        return

    hour_tr = now_tr.hour
    dow = now_tr.weekday()
    state = load_state()
    history = load_history()

    opened: list[dict] = []
    for sym in SYMBOLS:
        sig = predict_pm_direction(sym)
        if sig is None:
            continue
        amount = symbol_wr_amount(history, sym)
        entry_price = await _hour_open_price(sym, sig.current_price)
        pos = {
            "symbol": sym,
            "predicted_dir": sig.predicted_dir,
            "entry_price": entry_price,
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "entry_dow": dow,
            "entry_is_weekend": dow >= 5,
            "amount": amount,
            "signal_engine": "jesse_golden_cross",
            "ind_rsi_val": round(sig.rsi, 1),
            "ema_fast": round(sig.ema_fast, 4),
            "ema_slow": round(sig.ema_slow, 4),
            "golden_cross": sig.golden_cross,
        }
        apply_pm_quote(pos, sym, sig.predicted_dir, amount, now)
        state["open_positions"].append(pos)
        opened.append({"sym": sym, "sig": sig, "pos": pos, "amount": amount})

    save_state(state)

    if not opened:
        print(f"[{LABEL} open] {saat} IST — islem yok")
        return

    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    lines: list[str] = []
    for item in opened:
        sym, sig, pos, amount = item["sym"], item["sig"], item["pos"], item["amount"]
        name = sym.replace("USDT", "")
        conf = max(sig.prob_up, sig.prob_down) * 100
        icon = "📈" if sig.predicted_dir == "UP" else "📉"
        dir_tr = "YUKSELIR" if sig.predicted_dir == "UP" else "DUSER"
        sym_w, sym_t = get_symbol_stats(history, sym)
        pm_line = pm_tg_stake(pos) or f"💵 ${amount:.0f}"
        cross = "Golden✓" if sig.golden_cross else "Golden✗"
        lines.append(
            f"{icon} <b>{name}</b>  {dir_tr}  konf:%{conf:.0f}  "
            f"RSI:{sig.rsi:.0f}  EMA8/21:{cross}\n"
            f"   {pm_line}  |  genel: {_wr(sym_w, sym_t)}"
        )

    at_risk = sum(p.get("pm_spent") or p.get("amount", 0) for p in state["open_positions"])
    sep = "━" * 26
    tg_send(
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} - {next_h}</b>  🔶 SANAL PM  Jesse GoldenCross\n"
        + "\n".join(lines) + "\n"
        f"{sep}\n"
        f"💰 Bakiye: ${state['balance']:.2f}  |  📂 Riskte: ${at_risk:.0f}  |  Acik: {len(state['open_positions'])}\n"
        f"{sep}"
    )
    print(f"[{LABEL} open] {saat} IST — {len(opened)} acildi")


def run_stats() -> None:
    history = load_history()
    state = load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total = len(history)
    wins = sum(1 for t in history if t.get("win"))
    net = round(sum(t.get("pnl", 0) or 0 for t in history), 2)
    tg_send(
        f"📊 <b>{LABEL} ISTATISTIK</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} IST\n"
        f"Toplam: {total}  |  {_wr(wins, total)}\n"
        f"{'🟢' if net >= 0 else '🔴'} P&amp;L: {net:+.2f}$\n"
        f"Bakiye: ${state.get('balance', INITIAL_BALANCE):.2f}\n"
        f"BTC+SOL+ETH saatlik sanal PM · Jesse GoldenCross EMA8/21"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "stats":
        run_stats()
    else:
        asyncio.run(run_open())

"""
ALFA ANALİZ — Üçlü konsensüs sanal (A1 + A3 + A8, BTC + SOL)

A1 (PolyPredict) + A3 (Freqtrade TA) + A8 (Jesse GoldenCross) oylaması;
motor WR ağırlıklı puan ve min 2/3 konsensüs ile giriş.
Sanal $300, gerçek emir yok.

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
sys.path.insert(0, _DIR)

from alfa_signal import AlfaDecision, amount_for_decision, analyze_symbol
from pm_trader_helpers import (
    apply_pm_quote,
    in_weekend_pause_tr,
    pm_tg_stake,
    sanal_pnl,
    symbol_wr_amount,
    SANAL_INITIAL_BALANCE,
)

LABEL = "ALFA ANALİZ"
BOT_TOKEN = "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E"
CHAT_ID = os.getenv("TELEGRAM_ALFA_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or "830754964"

_TZ_TR = ZoneInfo("Europe/Istanbul")
STATE_FILE = os.path.join(_DIR, "poly_trader_alfa_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_alfa_history.json")

INITIAL_BALANCE = SANAL_INITIAL_BALANCE
SYMBOLS = ["BTCUSDT", "SOLUSDT"]


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
            resp = json.loads(r.read().decode())
        if resp.get("ok"):
            print(f"[{LABEL} TG] gonderildi")
        else:
            print(f"[{LABEL} TG] hata: {resp.get('description', 'bilinmiyor')}")
    except Exception as exc:
        print(f"[{LABEL} TG] Hata: {exc}")


def _vote_line(v) -> str:
    if not v.predicted_dir:
        return f"{v.label}: —"
    icon = "✓" if v.predicted_dir == "UP" else "↓" if v.predicted_dir == "DOWN" else "?"
    d = "UP" if v.predicted_dir == "UP" else "DN"
    return f"{v.label}:{d}{icon} %{v.confidence * 100:.0f} WR:%{v.wr_weight * 100:.0f}"


def _decision_tg_block(dec: AlfaDecision) -> str:
    votes = " | ".join(_vote_line(v) for v in dec.votes)
    if dec.should_trade:
        dir_tr = "YUKSELIR" if dec.predicted_dir == "UP" else "DUSER"
        return f"puan:{dec.score:.0f}  {dec.agree_count}/3  {dir_tr}\n   {votes}"
    return f"ATLANDI — {dec.skip_reason}\n   {votes}"


async def _hour_open_price(symbol: str, fallback: float) -> float:
    from poly_predictor_analysis import _fetch_klines

    try:
        klines = await _fetch_klines(symbol, "1h", 3)
        if klines and len(klines) >= 2:
            return float(klines[-2]["close"])
    except Exception:
        pass
    return fallback


async def _current_price(symbol: str) -> float | None:
    from poly_predictor_analysis import _fetch_klines

    klines = await _fetch_klines(symbol, "1h", 3)
    if not klines or len(klines) < 2:
        return None
    return float(klines[-2]["close"])


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
        current = await _current_price(pos["symbol"])
        if current is None:
            failed.append(pos)
            continue

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
            "alfa_score": pos.get("alfa_score"),
            "alfa_agree": pos.get("alfa_agree"),
            "votes_a1": pos.get("votes_a1"),
            "votes_a3": pos.get("votes_a3"),
            "votes_a8": pos.get("votes_a8"),
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)

        name = pos["symbol"].replace("USDT", "")
        icon = "✅" if win else "❌"
        pct = (current - entry) / entry * 100 if entry else 0
        stake = pm_tg_stake(pos) or f"${pos.get('amount', 0):.0f}"
        sc = pos.get("alfa_score", "?")
        lines.append(
            f"{icon} {name} {pred}  {entry:.4g}→{current:.4g} ({pct:+.2f}%)  "
            f"puan:{sc}  {stake}"
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
    saat_round = f"{now_tr.hour:02d}:00"
    sep = "━" * 26
    tg_send(
        f"{sep}\n"
        f"🏁 <b>{LABEL} — {saat_round} Sonuclar</b>  🔶 SANAL PM\n"
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
    skipped: list[str] = []

    for sym in SYMBOLS:
        dec = await analyze_symbol(sym)
        if not dec.should_trade:
            skipped.append(f"{sym.replace('USDT', '')}: {dec.skip_reason or 'elenmedi'}")
            continue

        base = symbol_wr_amount(history, sym)
        amount = amount_for_decision(base, dec)
        if amount <= 0:
            skipped.append(f"{sym.replace('USDT', '')}: tutar 0")
            continue

        from poly_predictor_analysis import predict
        pred = await predict(sym)
        fallback = pred.current_price if pred else 0.0
        entry_price = await _hour_open_price(sym, fallback)

        votes_map = {v.key: v.predicted_dir for v in dec.votes}
        pos = {
            "symbol": sym,
            "predicted_dir": dec.predicted_dir,
            "entry_price": entry_price,
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "entry_dow": dow,
            "entry_is_weekend": dow >= 5,
            "amount": amount,
            "alfa_score": dec.score,
            "alfa_agree": dec.agree_count,
            "votes_a1": votes_map.get("a1"),
            "votes_a3": votes_map.get("a3"),
            "votes_a8": votes_map.get("a8"),
        }
        apply_pm_quote(pos, sym, dec.predicted_dir, amount, now)
        state["open_positions"].append(pos)
        opened.append({"sym": sym, "dec": dec, "pos": pos, "amount": amount})

    save_state(state)

    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    sep = "━" * 26
    lines: list[str] = []

    for item in opened:
        sym, dec, pos, amount = item["sym"], item["dec"], item["pos"], item["amount"]
        name = sym.replace("USDT", "")
        icon = "📈" if dec.predicted_dir == "UP" else "📉"
        sym_w, sym_t = get_symbol_stats(history, sym)
        pm_line = pm_tg_stake(pos) or f"💵 ${amount:.0f}"
        lines.append(
            f"{icon} <b>{name}</b>  {_decision_tg_block(dec)}\n"
            f"   {pm_line}  |  ALFA: {_wr(sym_w, sym_t)}"
        )

    if opened:
        at_risk = sum(p.get("pm_spent") or p.get("amount", 0) for p in state["open_positions"])
        tg_send(
            f"{sep}\n"
            f"🅰️ <b>{LABEL} — {saat} - {next_h}</b>  🔶 SANAL PM  A1+A3+A8\n"
            + "\n".join(lines) + "\n"
            f"{sep}\n"
            f"💰 Bakiye: ${state['balance']:.2f}  |  📂 Riskte: ${at_risk:.0f}  |  Acik: {len(state['open_positions'])}\n"
            + (f"⏭ Elenen: {', '.join(skipped)}\n" if skipped else "")
            + f"{sep}"
        )
        print(f"[{LABEL} open] {saat} IST — {len(opened)} acildi")
    else:
        tg_send(
            f"{sep}\n"
            f"🅰️ <b>{LABEL} — {saat}</b>  🔶 SANAL PM\n"
            f"Bu tur islem acilmadi.\n"
            + "\n".join(skipped) + "\n"
            f"{sep}"
        )
        print(f"[{LABEL} open] {saat} IST — islem yok ({len(skipped)} elendi)")


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
        f"BTC+SOL saatlik sanal · A1+A3+A8 konsensüs"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "stats":
        run_stats()
    else:
        asyncio.run(run_open())

"""
ALFA ANALİZ — Konsensüs sanal (A1 + A3 + A8; SOL + Markov #35)

SOL: 4 motor — 2/4→$6, 3/4→$12, 4/4→$24
BTC/ETH: 3 motor — 2/3→$8, 3/3→$16
Sanal $300, gerçek emir yok.

Modlar: close (:02) / open (:05) / stats
Hafta sonu: Cuma 22:00 – Pazar 18:00 İST (open/close atlanır)
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

from alfa_signal import AlfaDecision, amount_for_decision, analyze_symbol, consensus_mode_label
from pm_trader_helpers import (
    apply_pm_quote,
    skip_if_weekend_pause,
    pm_tg_stake,
    sanal_pnl,
    SANAL_INITIAL_BALANCE,
)

LABEL = "ALFA ANALİZ"
BOT_TOKEN = "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E"
CHAT_ID = os.getenv("TELEGRAM_ALFA_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or "830754964"

_TZ_TR = ZoneInfo("Europe/Istanbul")
STATE_FILE = os.path.join(_DIR, "poly_trader_alfa_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_alfa_history.json")

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
        return f"{consensus_mode_label(dec)}  {dir_tr}\n   {votes}"
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
    if skip_if_weekend_pause(LABEL, "close", now_tr):
        return

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
            "alfa_mode": pos.get("alfa_mode"),
            "votes_a1": pos.get("votes_a1"),
            "votes_a3": pos.get("votes_a3"),
            "votes_a8": pos.get("votes_a8"),
            "votes_m35": pos.get("votes_m35"),
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

    if skip_if_weekend_pause(LABEL, "open", now_tr):
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

        amount = amount_for_decision(dec)
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
            "alfa_engines": dec.engine_total,
            "alfa_mode": dec.consensus_mode,
            "votes_a1": votes_map.get("a1"),
            "votes_a3": votes_map.get("a3"),
            "votes_a8": votes_map.get("a8"),
            "votes_m35": votes_map.get("m35"),
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
            f"🅰️ <b>{LABEL} — {saat} - {next_h}</b>  🔶 SANAL PM  A1+A3+A8 (+M35 SOL)\n"
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


def run_stats(last_n: int = 10) -> None:
    history = load_history()
    state = load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    closed = [t for t in history if t.get("win") is not None]
    total = len(closed)
    wins = sum(1 for t in closed if t.get("win"))
    net = round(sum(float(t.get("pnl") or 0) for t in closed), 2)
    today_key = now_tr.date().isoformat()
    today = [t for t in closed if (t.get("exit_time_tr") or "").startswith(today_key)]
    tw = sum(1 for t in today if t.get("win"))
    tpnl = round(sum(float(t.get("pnl") or 0) for t in today), 2)

    sep = "━" * 26
    recent_lines: list[str] = []
    for t in closed[-last_n:][::-1]:
        name = (t.get("symbol") or "?").replace("USDT", "")
        pred = t.get("predicted_dir") or "?"
        icon = "✅" if t.get("win") else "❌"
        pnl = float(t.get("pnl") or 0)
        et = (t.get("exit_time_tr") or "")[11:16] or "?"
        dt = (t.get("exit_time_tr") or "")[5:10] or ""
        recent_lines.append(
            f"{icon} {dt} {et} {name} {pred}  {'+' if pnl >= 0 else ''}{pnl:.2f}$"
        )

    open_lines: list[str] = []
    for p in state.get("open_positions") or []:
        name = (p.get("symbol") or "?").replace("USDT", "")
        pred = p.get("predicted_dir") or "?"
        amt = float(p.get("amount") or p.get("pm_spent") or 0)
        open_lines.append(f"📂 {name} {pred}  ${amt:.0f}")

    body = (
        f"{sep}\n"
        f"📊 <b>{LABEL} — Son İşlemler</b>  🔶 SANAL PM\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"Genel: {_wr(wins, total)}  |  {'🟢' if net >= 0 else '🔴'} P&amp;L {net:+.2f}$\n"
    )
    if today:
        body += f"Bugün: {_wr(tw, len(today))}  |  {'🟢' if tpnl >= 0 else '🔴'} {tpnl:+.2f}$\n"
    body += f"💰 Bakiye: ${float(state.get('balance', INITIAL_BALANCE)):.2f}\n"
    if open_lines:
        body += f"\n<b>Açık ({len(open_lines)})</b>\n" + "\n".join(open_lines) + "\n"
    if recent_lines:
        body += f"\n<b>Son {min(last_n, len(recent_lines))} kapanan</b>\n" + "\n".join(recent_lines) + "\n"
    body += f"{sep}"
    tg_send(body)
    print(f"[{LABEL} stats] gonderildi — {total} islem, son {len(recent_lines)}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "stats":
        run_stats()
    else:
        asyncio.run(run_open())

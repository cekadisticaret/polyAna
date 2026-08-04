#!/usr/bin/env python3
"""A2#16 Supertrend LIVE — gerçek Polymarket (BTC+ETH+SOL).

Sanal A2#16 (poly_trader_a2.py / poly_a2_algo_trader_core) yapısına DOKUNMAZ.
Aynı sinyal kaynağı: /tmp/algo_signals_v2.json → algo 16 (Supertrend).

Env: PM_A2_16_LIVE_ENABLED=true
Dashboard: a2_16_live aç/kapa + a2_16 miktarları (DÜŞ/ORTA/YÜK)
Cron: close :02 · open :06 (algo_signals_v2 :05 sonrası)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poly_live_hourly_common import tg_send, try_pm_open
from poly_predictor_analysis import _fetch_klines
from poly_a2_algo_trader_core import _load_v2_signal, SYMBOLS, _sym_short
from pm_trader_helpers import (
    pm_fetch_resolution,
    pm_get_balance,
    pm_realized_pnl,
    pm_tg_stake,
    resolve_slot_trade_amount,
    skip_if_weekend_pause,
    slot_amount_log,
    pm_live_wr_amount,
    pm_live_amount_range_str,
    HOURLY_MIN_NET_PROFIT_RATIO,
)
from pm_balance_guard import can_open_trade

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_TZ_TR = ZoneInfo("Europe/Istanbul")
_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_DIR, "poly_trader_a2_16_live_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_a2_16_live_history.json")
HATA_FILE = os.path.join(_DIR, "a2_16_live_polyhata.json")

LABEL = "A2#16 Supertrend Live"
ALGO_NUM = 16
ALGO_NAME = "Supertrend"
TRADE_AMOUNT = 12.0
_PM_LIVE = os.getenv("PM_A2_16_LIVE_ENABLED", "false").lower() in ("1", "true", "yes")
_AMOUNT_SYSTEM = "a2_16"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": 300.0, "open_positions": [], "total_pnl": 0.0}


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
    return f"%{wins / total * 100:.0f} ({wins}/{total})" if total else "veri yok"


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t.get("symbol") == symbol]
    return sum(1 for t in trades if t.get("win")), len(trades)


def get_stats(history: list, symbol: str, hour_tr: int) -> tuple[int, int]:
    trades = [
        t for t in history
        if t.get("symbol") == symbol and t.get("entry_hour_tr") == hour_tr
    ]
    return sum(1 for t in trades if t.get("win")), len(trades)


def _trade_amount(history: list, symbol: str) -> float:
    return pm_live_wr_amount(_AMOUNT_SYSTEM, history, symbol, get_symbol_stats)


def _pm_bal_line() -> str:
    bal = pm_get_balance()
    return f"💰 PM Bakiye: ${bal:.2f}" if bal >= 0 else "💰 PM Bakiye: ?"


async def run_close() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if skip_if_weekend_pause(LABEL, "close", now_tr):
        return
    state = load_state()
    history = load_history()
    if not state["open_positions"]:
        print(f"[{LABEL} close] açık pozisyon yok")
        return

    lines = []
    tur_pnl = 0.0
    failed = []
    for pos in list(state["open_positions"]):
        sym = pos["symbol"]
        klines = await _fetch_klines(sym, "1h", 2)
        if not klines:
            failed.append(pos)
            continue
        current_price = klines[-1]["close"]
        entry = pos["entry_price"]
        pred = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        has_pm = bool(pos.get("pm_slug") and pos.get("pm_order_id"))
        if has_pm:
            res = pm_fetch_resolution(pos["pm_slug"])
            if res is None:
                failed.append(pos)
                continue
            token_dir = pos.get("pm_token_dir") or pred
            win = (token_dir == "UP" and res["up_won"]) or (token_dir == "DOWN" and not res["up_won"])
            actual = "UP" if res["up_won"] else "DOWN"
            pnl = pm_realized_pnl(pos, win)
        else:
            actual = "UP" if current_price >= entry else "DOWN"
            win = pred == actual
            pm_spent = float(pos.get("pm_spent") or amount)
            pm_size = float(pos.get("pm_size") or 0)
            pnl = round(pm_size - pm_spent, 2) if win and pm_size else round(-pm_spent, 2)
        tur_pnl += pnl
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)
        history.append({
            "symbol": sym,
            "predicted_dir": pred,
            "actual_dir": actual,
            "win": win,
            "entry_price": entry,
            "exit_price": current_price,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos.get("entry_hour_tr"),
            "entry_dow": pos.get("entry_dow"),
            "amount": amount,
            "pnl": pnl,
            "pm_live": True,
            "exit_time_tr": now_tr.isoformat(),
            "pm_spent": pos.get("pm_spent"),
            "pm_size": pos.get("pm_size"),
            "pm_slug": pos.get("pm_slug"),
            "algo_name": pos.get("algo_name", ALGO_NAME),
            "algo_num": ALGO_NUM,
        })
        name = _sym_short(sym)
        lines.append(f"{'✅' if win else '❌'} {name}  {pred}  net {'+' if pnl >= 0 else ''}{pnl:.2f}$")

    state["open_positions"] = failed
    save_state(state)
    save_history(history)
    if not lines:
        return
    closed = len(history)
    wins = sum(1 for t in history if t["win"])
    genel = f"%{wins / closed * 100:.0f}" if closed else "—"
    sep = "━" * 26
    tg_send(
        LABEL,
        f"{sep}\n🏁 <b>{LABEL} — Sonuçlar</b>  🔴 GERÇEK PM\n"
        + "\n".join(lines)
        + f"\nBu tur: {'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$  |  {_pm_bal_line()}\n"
        f"Genel: {genel} ({closed} işlem)\n{sep}",
    )


async def run_open() -> None:
    if not _PM_LIVE:
        print(f"[{LABEL} open] PM_A2_16_LIVE_ENABLED=false — atlandı")
        return
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    if skip_if_weekend_pause(LABEL, "open", now_tr):
        return
    if not can_open_trade(LABEL, lambda t: tg_send(LABEL, t)):
        return

    hour_tr = now_tr.hour
    dow = now_tr.weekday()
    is_weekend = dow >= 5
    saat = now_tr.strftime("%H:%M")

    sig_entry = _load_v2_signal(ALGO_NUM)
    if not sig_entry:
        print(f"[{LABEL} open] {saat} — A2#16 sinyal yok")
        return

    state = load_state()
    history = load_history()
    open_syms = {p["symbol"] for p in state.get("open_positions", [])}
    opened = []

    for sym in SYMBOLS:
        short = _sym_short(sym)
        direction = sig_entry.get(short)
        if direction not in ("UP", "DOWN"):
            print(f"[{LABEL} open] {sym} — NEUTRAL, işlem yok")
            continue
        if sym in open_syms:
            print(f"[{LABEL} open] {sym} zaten açık — atlandı")
            continue
        try:
            klines = await _fetch_klines(sym, "1h", 3)
            entry_price = klines[-2]["close"] if klines and len(klines) >= 2 else None
        except Exception:
            entry_price = None
        if entry_price is None:
            continue

        base = _trade_amount(history, sym)
        amount, hot_boost, cold_cut = resolve_slot_trade_amount(base, hour_tr, history)
        slot_amount_log(LABEL, hour_tr, base, amount, hot_boost, cold_cut)
        pos, err = try_pm_open(
            state,
            label=LABEL,
            hata_file=HATA_FILE,
            sym=sym,
            direction=direction,
            entry_price=entry_price,
            hour_tr=hour_tr,
            dow=dow,
            is_weekend=is_weekend,
            now_tr=now_tr,
            now=now,
            extra={
                "algo_name": ALGO_NAME,
                "algo_num": ALGO_NUM,
                "algo_signal": direction,
                "hot_hour_boost": hot_boost,
                "cold_hour_cut": cold_cut,
            },
            amount=amount,
            pm_live=_PM_LIVE,
            min_profit_ratio=HOURLY_MIN_NET_PROFIT_RATIO,
        )
        if pos:
            opened.append((sym, direction, entry_price, pos))
            open_syms.add(sym)
        elif err:
            print(f"[{LABEL} open] {sym} PM hatası: {err}")

    save_state(state)
    if not opened:
        print(f"[{LABEL} open] {saat} — açılan yok")
        return

    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    lines = []
    for sym, direction, entry_price, pos in opened:
        name = _sym_short(sym)
        dir_icon = "📈" if direction == "UP" else "📉"
        hw, ht = get_stats(history, sym, hour_tr)
        sw, st = get_symbol_stats(history, sym)
        pm_line = pm_tg_stake(pos) or f"💵 ${pos.get('amount', TRADE_AMOUNT):.0f}"
        lines.append(
            f"{dir_icon} <b>{name}</b>  {direction}  📊 {ALGO_NAME}  giriş:{entry_price:.2f}\n"
            f"   {pm_line}\n   🕐 {_wr(hw, ht)}  |  genel: {_wr(sw, st)}"
        )
    sep = "━" * 26
    tg_send(
        LABEL,
        f"{sep}\n🆕 <b>{LABEL} — {saat}-{next_h}</b>  🔴 GERÇEK PM  "
        f"{pm_live_amount_range_str(_AMOUNT_SYSTEM)}\n"
        + "\n".join(lines)
        + f"\n{sep}\n{_pm_bal_line()}\n{sep}",
    )
    print(f"[{LABEL} open] {len(opened)} açıldı")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    asyncio.run(run_close() if mode == "close" else run_open())

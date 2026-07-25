"""
CEM-ANALİZ — A1 + A2 + 110 mirror sanal ($300 ortak havuz)

Kaynak algolar kendi state/TG/cron'larında bağımsız çalışır.
CEM, açık pozisyonlarını okuyup aynı işlemleri ortak havuzda kopyalar.
Telegram: 13. Analiz kanalı (8722131600).

Modlar:
  close_hourly  → :03 — A1/A2 saatlik kapanış
  open_hourly   → :06 — A1/A2 mirror açılış
  sync_15m      → */15 +1dk — 110 kapanış + mirror
  status / reset
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poly_predictor_analysis import _fetch_klines
from btc_5m_105_algo import fetch_klines_15m
from pm_trader_helpers import pm_tg_stake, pm_stake_fields, skip_if_weekend_pause
from pm_cem_pool import (
    pool_view,
    try_open,
    settle,
    replace_algo_positions,
    positions_for,
    load_history,
    save_history,
    pool_status,
    reset_pool,
    has_position,
    SOURCE_LABELS,
)

LABEL = "CEM-ANALİZ"
BOT_TOKEN = "8722131600:AAH8eg11cvm1xU0KiKEjzCIVsc-RSgkZi4Y"
CHAT_ID = "830754964"
_TZ_TR = ZoneInfo("Europe/Istanbul")
_DIR = os.path.dirname(os.path.abspath(__file__))
_SEP = "━" * 26

SOURCES = {
    "a1": os.path.join(_DIR, "poly_trader_analiz1_state.json"),
    "a2": os.path.join(_DIR, "poly_trader_analiz2_state.json"),
    "110": os.path.join(_DIR, "poly_trader_5m_sol_110_state.json"),
}


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
        print(f"[TG] Hata: {e}")


def _load_source_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"open_positions": []}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"open_positions": []}


def _resolve_15m_candle(symbol: str, ts_period: int, retries: int = 6, wait_sec: float = 2.0) -> dict | None:
    target_ms = ts_period * 1000
    for _ in range(retries):
        for k in fetch_klines_15m(symbol, 30):
            if k["open_time"] == target_ms:
                return k
        time.sleep(wait_sec)
    return None


def _history_rec(pos: dict, algo: str, actual: str, win: bool, pnl: float, exit_price: float, now_tr: datetime) -> dict:
    rec = {
        "source_algo": algo,
        "symbol": pos.get("symbol"),
        "predicted_dir": pos.get("predicted_dir"),
        "actual_dir": actual,
        "win": win,
        "entry_price": pos.get("entry_price"),
        "exit_price": exit_price,
        "amount": pos.get("amount"),
        "entry_time_tr": pos.get("entry_time_tr"),
        "exit_time_tr": now_tr.isoformat(),
        "pnl": pnl,
    }
    for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug", "ts_period", "ts_5m"):
        if pos.get(k) is not None:
            rec[k] = pos[k]
    return rec


async def _close_positions(algos: tuple[str, ...]) -> tuple[list[str], float]:
    positions = positions_for(algos)
    if not positions:
        return [], 0.0

    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    history = load_history()
    lines: list[str] = []
    toplam_pnl = 0.0
    failed: list[dict] = []

    for pos in list(positions):
        algo = pos.get("pool_algo", "")
        sym = pos.get("symbol", "")
        name = sym.replace("USDT", "")
        pred = pos.get("predicted_dir", "?")
        entry = pos.get("entry_price", 0)

        if algo == "110":
            ts = pos.get("ts_period") or pos.get("ts_5m")
            candle = _resolve_15m_candle(sym, ts) if ts else None
            if candle is None:
                try:
                    candle = fetch_klines_15m(sym, 10)[-2]
                except Exception as e:
                    print(f"[CEM] 110 kapanış fiyatı yok ({sym}): {e}")
                    failed.append(pos)
                    continue
            exit_price = candle["close"]
            ref_open = candle["open"]
            actual = "UP" if exit_price >= ref_open else "DOWN"
        else:
            klines = await _fetch_klines(sym, "1h", 2)
            if not klines:
                failed.append(pos)
                continue
            exit_price = klines[-1]["close"]
            actual = "UP" if exit_price >= entry else "DOWN"

        win = pred == actual
        pnl = settle(algo, pos, win)
        toplam_pnl += pnl
        history.append(_history_rec(pos, algo, actual, win, pnl, exit_price, now_tr))

        icon = "✅" if win else "❌"
        pct = (exit_price - entry) / entry * 100 if entry else 0
        pnl_str = f"+{pnl:.2f}$" if pnl >= 0 else f"{pnl:.2f}$"
        src = SOURCE_LABELS.get(algo, algo)
        lines.append(
            f"{icon} <b>{src}</b> {name}  {pred}  {entry:.2f} → {exit_price:.2f} ({pct:+.2f}%)  {pnl_str}"
        )

    for algo in algos:
        failed_algo = [p for p in failed if p.get("pool_algo") == algo]
        if failed_algo:
            replace_algo_positions(algo, failed_algo)

    save_history(history)
    return lines, toplam_pnl


def _mirror_opens(algos: tuple[str, ...]) -> tuple[list[str], list[str]]:
    opened: list[str] = []
    skipped: list[str] = []
    for algo in algos:
        src = _load_source_state(SOURCES[algo])
        for pos in src.get("open_positions", []):
            if has_position(algo, pos):
                continue
            name = pos.get("symbol", "?").replace("USDT", "")
            dir_tr = "YÜKSELİR" if pos.get("predicted_dir") == "UP" else "DÜŞER"
            dir_icon = "📈" if pos.get("predicted_dir") == "UP" else "📉"
            stake = pm_tg_stake(pos) or f"💵 ${pos.get('amount', 0):.0f}"
            if try_open(algo, pos):
                opened.append(
                    f"{dir_icon} <b>{SOURCE_LABELS[algo]}</b> {name} {dir_tr}\n   {stake}"
                )
            else:
                skipped.append(f"⏸ {SOURCE_LABELS[algo]} {name} — havuz yetersiz")
    return opened, skipped


def _balance_footer(state: dict, history: list) -> str:
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all = sum(1 for t in history if t.get("win"))
    genel = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    return (
        f"{pnl_icon} Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$"
        f"  |  Bakiye: ${state['balance']:.2f}  |  Genel: {genel} ({closed_all} işlem)"
    )


async def run_close_hourly() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if skip_if_weekend_pause(LABEL, "close_hourly", now_tr):
        return
    saat = now_tr.strftime("%H:%M")
    saat_round = f"{int(saat[:2]):02d}:00"

    lines, toplam_pnl = await _close_positions(("a1", "a2"))
    if not lines:
        print(f"[CEM close_hourly] {saat} — kapanış yok")
        return

    state = pool_view()
    history = load_history()
    msg = (
        f"{_SEP}\n"
        f"🏁 <b>{LABEL} — {saat_round} Sonuçlar</b>  🔶 SANAL\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+' if toplam_pnl >= 0 else ''}{toplam_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{_balance_footer(state, history)}\n"
        f"{_SEP}"
    )
    tg_send(msg)
    print(f"[CEM close_hourly] {saat} — {len(lines)} kapanış")


async def run_open_hourly() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if skip_if_weekend_pause(LABEL, "open_hourly", now_tr):
        return
    saat = now_tr.strftime("%H:%M")
    hour_tr = now_tr.hour
    next_h = f"{(hour_tr + 1) % 24:02d}:00"

    opened, skipped = _mirror_opens(("a1", "a2"))
    if not opened and not skipped:
        print(f"[CEM open_hourly] {saat} — mirror yok")
        return

    state = pool_view()
    history = load_history()
    at_risk = sum(p.get("pm_spent") or p.get("amount", 0) for p in state["open_positions"])
    body = "\n".join(opened)
    if skipped:
        body += "\n" + "\n".join(skipped)
    msg = (
        f"{_SEP}\n"
        f"🆕 <b>{LABEL} — {saat} - {next_h} Mirror Açılış</b>  🔶 SANAL\n"
        f"<i>A1 + A2 → ortak $300 havuz</i>\n"
        f"{body}\n"
        f"💰 Bakiye: ${state['balance']:.2f}  |  📂 ${at_risk:.0f} riskte\n"
        f"{_balance_footer(state, history)}\n"
        f"{_SEP}"
    )
    tg_send(msg)
    print(f"[CEM open_hourly] {saat} — {len(opened)} mirror açılış")


async def run_sync_15m() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if skip_if_weekend_pause(LABEL, "sync_15m", now_tr):
        return
    period_min = (now_tr.hour * 60 + now_tr.minute) // 15 * 15
    saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
    next_period = period_min + 15
    next_saat = f"{(next_period % (24 * 60)) // 60:02d}:{next_period % 60:02d}"

    closed_lines, tur_pnl = await _close_positions(("110",))
    opened, skipped = _mirror_opens(("110",))

    if not closed_lines and not opened and not skipped:
        print(f"[CEM sync_15m] {saat} — değişiklik yok")
        return

    state = pool_view()
    history = load_history()
    parts = [f"{_SEP}"]

    if closed_lines:
        parts.append(f"🏁 <b>{LABEL} — {saat} Sonuçlar (110)</b>  🔶 SANAL")
        parts.extend(closed_lines)
        parts.append(f"Bu tur: {'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$")

    if opened or skipped:
        parts.append(f"🆕 <b>{LABEL} — {saat} - {next_saat} Mirror (110)</b>  🔶 SANAL")
        if opened:
            parts.extend(opened)
        if skipped:
            parts.extend(skipped)

    parts.append(_balance_footer(state, history))
    parts.append(_SEP)
    tg_send("\n".join(parts))
    print(f"[CEM sync_15m] {saat} — kapanış:{len(closed_lines)} açılış:{len(opened)}")


def run_status() -> None:
    s = pool_status()
    print(f"{LABEL} — ortak havuz $300")
    print(f"Bakiye: ${s['balance']:.2f}  |  P&L: {'+' if s['total_pnl'] >= 0 else ''}{s['total_pnl']:.2f}$")
    print(f"Açık: {s['open_total']}  |  Riskte: ${s['at_risk']:.2f}")
    for algo, n in s["by_algo"].items():
        print(f"  {SOURCE_LABELS[algo]}: {n}")


def main() -> None:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    if cmd == "close_hourly":
        asyncio.run(run_close_hourly())
    elif cmd == "open_hourly":
        asyncio.run(run_open_hourly())
    elif cmd == "sync_15m":
        asyncio.run(run_sync_15m())
    elif cmd == "status":
        run_status()
    elif cmd == "reset":
        bal = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
        reset_pool(bal)
        print(f"{LABEL} havuz sıfırlandı: ${bal:.2f}")
        run_status()
    else:
        print("Modlar: close_hourly | open_hourly | sync_15m | status | reset [bakiye]")


if __name__ == "__main__":
    main()

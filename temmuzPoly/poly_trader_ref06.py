"""REF06 sanal defter. Gerçek PM yok.

Uç nokta dönüşü + saat başı WR en yüksek defter onayı:
  1. Saatlik yolda ekstrem oluşmuş (≥25 bps) ve geri çekilmiş (≥10 bps).
  2. Her saat başında coin bazında WR en yüksek defter seçilir; ters yöndeyse atlanır.
  3. Token ask 0.20–0.35 bandında.

Kasa $1000 · sembol WR $24/$36/$48.
Cron: :01 close · * * open (her dakika) · Cumartesi 21:00 weekly.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_DIR, "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, _DIR)

from ref06_signal import ASK_MAX, ASK_MIN, SYMBOLS, decide  # noqa: E402
from ref06_wr_pick import ensure_hour_mapping, resolve_confirmation  # noqa: E402
from pm_trader_helpers import (  # noqa: E402
    apply_pm_quote,
    pm_sanal_settle_trade,
    pm_sanal_slot_candle,
    resolve_open_slot_gates,
    skip_if_weekend_pause,
    slot_amount_log,
    symbol_wr_amount_for_book,
)

_TZ_TR = ZoneInfo("Europe/Istanbul")

STATE_FILE   = os.path.join(_DIR, "poly_trader_ref06_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_ref06_history.json")
LABEL        = "REF06"
BOOK_KEY     = "ref06"
ALGO_NAME    = "REF06 · uç dönüş + WR en iyi"
INITIAL_BALANCE        = 1000.0
REF06_MIN_PROFIT_RATIO = 0.50

_ENTRY_LO = 10
_ENTRY_HI = 50


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


async def run_open() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    if skip_if_weekend_pause(LABEL, "open", now_tr):
        return
    if now_tr.minute < _ENTRY_LO or now_tr.minute > _ENTRY_HI:
        return

    ensure_hour_mapping(now_tr)

    state   = load_state()
    history = load_history()
    balance = float(state.get("balance") or INITIAL_BALANCE)
    open_syms = {p.get("symbol") for p in (state.get("open_positions") or [])}
    opened, skipped = [], []
    verbose = os.environ.get("REF06_TICK_VERBOSE") == "1"

    for sym in SYMBOLS:
        if sym in open_syms:
            skipped.append((sym, "zaten açık"))
            continue

        dec = decide(sym, now_tr.minute)
        if not dec.get("allow"):
            skipped.append((sym, dec.get("reason") or "kapı kapalı"))
            if verbose:
                print(f"[{LABEL} open] {sym} — {dec.get('reason')} · {dec.get('detail')}")
            continue

        conf_dir, pick = await resolve_confirmation(sym, now_tr)
        if conf_dir is not None and conf_dir != dec["direction"]:
            lbl = pick.get("label") or pick.get("book") or "WR"
            reason = f"{lbl} ters yön ({conf_dir}) — REF06 {dec['direction']}"
            skipped.append((sym, reason))
            if verbose:
                print(f"[{LABEL} open] {sym} — {reason}")
            continue

        base_amt = symbol_wr_amount_for_book(history, sym, BOOK_KEY)
        _sk, stake, hot_boost, cold_cut, _note = resolve_open_slot_gates(
            history, now_tr.hour, base_amt
        )
        slot_amount_log(LABEL, now_tr.hour, base_amt, stake, hot_boost, cold_cut)
        if stake <= 0 or stake > balance:
            skipped.append((sym, "bakiye/kademe"))
            continue

        pos = {
            "symbol":             sym,
            "predicted_dir":      dec["direction"],
            "entry_price":        None,
            "entry_time_tr":      now_tr.isoformat(),
            "entry_hour_tr":      now_tr.hour,
            "entry_dow":          now_tr.weekday(),
            "entry_is_weekend":   now_tr.weekday() >= 5,
            "amount":             stake,
            "hot_hour_boost":     hot_boost,
            "cold_hour_cut":      cold_cut,
            "algo_signal":        dec["direction"],
            "algo_name":          ALGO_NAME,
            "ref06_mode":         dec.get("mode"),
            "ref06_detail":       dec.get("detail"),
            "ref06_extreme_bps":  dec.get("extreme_bps"),
            "ref06_pullback_bps": dec.get("pullback_bps"),
            "ref06_extreme_mn":   dec.get("extreme_mn"),
            "ref06_path_bps":     dec.get("path_bps"),
            "ref06_entry_min":    now_tr.minute,
            "ref06_wr_book":      pick.get("book"),
            "ref06_wr_label":     pick.get("label"),
            "ref06_wr_pct":       pick.get("wr"),
            "ref06_wr_dir":       conf_dir,
            "ref06_wr_hour":      pick.get("hour_key"),
        }

        apply_pm_quote(pos, sym, dec["direction"], stake, now,
                       min_profit_ratio=REF06_MIN_PROFIT_RATIO)
        if pos.get("entry_skip"):
            skipped.append((sym, pos["entry_skip"]))
            print(f"[{LABEL} open] {sym} — {pos['entry_skip']}")
            continue

        ask = pos.get("pm_entry_price")
        try:
            ask_f = float(ask) if ask is not None else None
        except (TypeError, ValueError):
            ask_f = None
        lo = dec.get("ask_min", ASK_MIN)
        hi = dec.get("ask_max", ASK_MAX)
        if ask_f is not None and lo is not None and ask_f < float(lo):
            skipped.append((sym, f"ask {ask_f:.2f} < {lo} (çok riskli)"))
            print(f"[{LABEL} open] {sym} — ask_min {lo} · gelen {ask_f:.2f} (piyasa çok olumsuz)")
            continue
        if ask_f is not None and hi is not None and ask_f > float(hi):
            skipped.append((sym, f"ask {ask_f:.2f} > {hi}"))
            print(f"[{LABEL} open] {sym} — ask_max {hi} · gelen {ask_f:.2f}")
            continue

        if not pos.get("pm_slug"):
            skipped.append((sym, "PM dolum yok"))
            continue

        state["open_positions"].append(pos)
        open_syms.add(sym)
        opened.append((sym, dec, stake, pos))
        wr_note = ""
        if pick.get("label"):
            wr_note = f" · {pick['label']} %{pick.get('wr', '?')} {conf_dir or 'nötr'}"
        print(f"[{LABEL} open] {sym} {dec['direction']} ${stake:.2f} · {dec.get('detail')}{wr_note}")

    save_state(state)
    if not opened:
        if verbose:
            print(f"[{LABEL} open] {saat} İST — sinyal yok ({len(skipped)} skip)")
        return
    print(f"[{LABEL} open] {saat} İST — {len(opened)} pozisyon")


def run_close() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")
    state  = load_state()
    history = load_history()

    if not state.get("open_positions"):
        print(f"[{LABEL} close] {saat} İST — açık pozisyon yok")
        return

    lines, failed = [], []
    for pos in list(state["open_positions"]):
        candle = pm_sanal_slot_candle(pos["symbol"], pos["entry_time_tr"])
        if not candle:
            failed.append(pos)
            continue
        hour_open, hour_close = candle
        s   = pm_sanal_settle_trade(pos, hour_open, hour_close)
        win, pnl, actual = s["win"], s["pnl"], s["actual_dir"]
        state["balance"]   = round(float(state["balance"]) + pnl, 2)
        state["total_pnl"] = round(float(state.get("total_pnl") or 0) + pnl, 2)
        rec = {
            "symbol":             pos["symbol"],
            "predicted_dir":      pos["predicted_dir"],
            "actual_dir":         actual,
            "win":                win,
            "entry_price":        s["entry_price"],
            "exit_price":         s["exit_price"],
            "entry_time_tr":      pos["entry_time_tr"],
            "entry_hour_tr":      pos.get("entry_hour_tr"),
            "entry_dow":          pos.get("entry_dow"),
            "entry_is_weekend":   pos.get("entry_is_weekend"),
            "amount":             pos.get("amount"),
            "exit_time_tr":       now_tr.isoformat(),
            "pnl":                pnl,
            "algo_signal":        pos.get("algo_signal"),
            "algo_name":          pos.get("algo_name", ALGO_NAME),
            "ref06_mode":         pos.get("ref06_mode"),
            "ref06_detail":       pos.get("ref06_detail"),
            "ref06_extreme_bps":  pos.get("ref06_extreme_bps"),
            "ref06_pullback_bps": pos.get("ref06_pullback_bps"),
            "ref06_extreme_mn":   pos.get("ref06_extreme_mn"),
            "ref06_path_bps":     pos.get("ref06_path_bps"),
            "ref06_entry_min":    pos.get("ref06_entry_min"),
            "ref06_wr_book":      pos.get("ref06_wr_book"),
            "ref06_wr_label":     pos.get("ref06_wr_label"),
            "ref06_wr_pct":       pos.get("ref06_wr_pct"),
            "ref06_wr_dir":       pos.get("ref06_wr_dir"),
            "ref06_wr_hour":      pos.get("ref06_wr_hour"),
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug",
                  "pm_fee", "pm_quote_src", "pm_mid_price"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)
        name = pos["symbol"].replace("USDT", "")
        lines.append(f"{'W' if win else 'L'} {name} {pos['predicted_dir']} {pnl:+.2f}$")

    state["open_positions"] = failed
    save_state(state)
    save_history(history)
    if not lines:
        print(f"[{LABEL} close] {saat} — kapanan yok")
        return
    print(f"[{LABEL} close] {saat} İST — {len(lines)} kapandı · bakiye ${state['balance']:.2f}")


def run_preview() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    mapping = ensure_hour_mapping(now_tr)
    print(f"{LABEL} önizleme — {now_tr:%d.%m.%Y %H:%M} İST  dakika {now_tr.minute}")
    for sym in SYMBOLS:
        dec  = decide(sym, now_tr.minute)
        flag = "AÇ" if dec.get("allow") else "YOK"
        ext  = dec.get("extreme_bps")
        pb   = dec.get("pullback_bps")
        ext_str = f" ext={ext:+.1f}" if ext is not None else ""
        pb_str  = f" pb={pb:.1f}" if pb is not None else ""
        row = mapping.get(sym.replace("USDT", "")) or {}
        wr_note = f"{row.get('label', '—')} %{row.get('wr', '—')}" if row else "eşleme yok"
        print(f"  {sym:9s} {flag:3s}  {dec.get('direction') or '—':4s} "
              f" {dec.get('detail') or dec.get('reason')}{ext_str}{pb_str}"
              f"  WR={wr_note}")


def run_stats() -> None:
    history, state = load_history(), load_state()
    if not history:
        print(f"{LABEL} — işlem yok · bakiye ${state.get('balance', 0):.2f}")
        return
    wins = sum(1 for t in history if t.get("win"))
    pnl  = state.get("total_pnl", 0)
    print(f"{LABEL} — {len(history)} işlem · {_wr(wins, len(history))} · "
          f"${state.get('balance', 0):.2f} · {pnl:+.2f}$")
    by: dict[str, list] = defaultdict(list)
    for t in history:
        by[t["symbol"]].append(t)
    for sym, rows in sorted(by.items()):
        w = sum(1 for t in rows if t.get("win"))
        p = sum(float(t.get("pnl") or 0) for t in rows)
        wr_ok = [t for t in rows if t.get("ref06_wr_dir")]
        wr_n  = [t for t in rows if not t.get("ref06_wr_dir")]
        print(f"  {sym:9s} {_wr(w, len(rows)):>16s}  {p:+8.2f}$"
              f"  WR_onay={len(wr_ok)}  WR_nötr={len(wr_n)}")


def run_weekly() -> None:
    run_stats()


_MODES = {
    "open": lambda: asyncio.run(run_open()),
    "close": run_close,
    "preview": run_preview,
    "stats": run_stats,
    "weekly": run_weekly,
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    fn = _MODES.get(mode)
    if not fn:
        print(f"Bilinmeyen mod: {mode}\nKullanım: {' | '.join(_MODES)}")
        sys.exit(1)
    fn()

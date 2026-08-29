"""COMBO — A1 + C1#01 + A2#05 V2 oy defteri. Sanal, gerçek PM yok.

Kaynaklar :02'de açar; COMBO :02:25'te onların açık pozisyonuna bakar.
Çatışmada açmaz. Kademe sembol WR $16/$24/$32. Ask ≤ 0,50. Kasa $1000.
Cron: :01 close · :02+25s open. Betik adı e01 (crontab).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
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

from e01_signal import SYMBOLS, decide  # noqa: E402
from pm_trader_helpers import (  # noqa: E402
    apply_pm_quote,
    pm_tg_stake,
    pm_sanal_settle_trade,
    pm_sanal_slot_candle,
    resolve_open_slot_gates,
    skip_if_weekend_pause,
    slot_amount_log,
    symbol_wr_amount_for_book,
)
from telegram_poly_channels import chat_analiz4  # noqa: E402

BOT_TOKEN = os.getenv("TELEGRAM_ANALIZ4_BOT_TOKEN", "")
CHAT_ID = chat_analiz4()
_TZ_TR = ZoneInfo("Europe/Istanbul")

STATE_FILE = os.path.join(_DIR, "poly_trader_combo_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_combo_history.json")
LABEL = "COMBO"
BOOK_KEY = "combo"
ALGO_NAME = "COMBO · A1+C101+A2#05V2 oy"
INITIAL_BALANCE = 1000.0
# Ask tavanı: yalnız p≤0.50 — kazanç ≥ zarar. Üstünü açma.
COMBO_MAX_ASK = float(os.getenv("COMBO_MAX_ASK") or 0.50)


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


def tg_send(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=15).read()
    except Exception as e:
        print(f"[{LABEL}] TG hatası: {e}")


def _wr(wins: int, total: int) -> str:
    return f"%{wins/total*100:.0f} ({wins}/{total})" if total else "veri yok"


def run_open() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    if skip_if_weekend_pause(LABEL, "open", now_tr):
        return

    state = load_state()
    history = load_history()
    balance = float(state.get("balance") or INITIAL_BALANCE)
    open_syms = {p.get("symbol") for p in (state.get("open_positions") or [])}
    opened, skipped = [], []

    for sym in SYMBOLS:
        if sym in open_syms:
            skipped.append((sym, "zaten açık"))
            continue
        dec = decide(sym, now_tr.hour)
        if not dec.get("allow"):
            skipped.append((sym, dec.get("reason") or "kapı kapalı"))
            print(f"[{LABEL} open] {sym} — {dec.get('reason')} · {dec.get('detail')}")
            continue
        base_amt = symbol_wr_amount_for_book(history, sym, BOOK_KEY)
        _sk, stake, hot_boost, cold_cut, _note = resolve_open_slot_gates(
            history, now_tr.hour, base_amt
        )
        slot_amount_log(LABEL, now_tr.hour, base_amt, stake, hot_boost, cold_cut)
        if stake <= 0 or stake > balance:
            skipped.append((sym, "bakiye/kademe"))
            continue
        dec["stake"] = stake
        pos = {
            "symbol": sym,
            "predicted_dir": dec["direction"],
            "entry_price": None,
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": now_tr.hour,
            "entry_dow": now_tr.weekday(),
            "entry_is_weekend": now_tr.weekday() >= 5,
            "amount": stake,
            "hot_hour_boost": hot_boost,
            "cold_hour_cut": cold_cut,
            "algo_signal": dec["direction"],
            "algo_name": ALGO_NAME,
            "e01_votes": dec.get("votes"),
            "e01_reason": dec.get("reason"),
            "e01_detail": dec.get("detail"),
            "e01_silent": dec.get("silent"),
        }
        apply_pm_quote(pos, sym, dec["direction"], stake, now)
        if pos.get("entry_skip"):
            skipped.append((sym, pos["entry_skip"]))
            print(f"[{LABEL} open] {sym} — {pos['entry_skip']}")
            continue
        if not pos.get("pm_slug"):
            skipped.append((sym, "PM dolum yok"))
            continue
        ask = float(pos.get("pm_entry_price") or 0)
        if ask > COMBO_MAX_ASK:
            skipped.append((sym, f"ask {ask:.2f} > {COMBO_MAX_ASK:.2f}"))
            print(
                f"[{LABEL} open] {sym} {dec['direction']} — "
                f"ask {ask:.2f} > {COMBO_MAX_ASK:.2f} (kazanç/zarar dengesiz, atlandı)"
            )
            continue
        state["open_positions"].append(pos)
        open_syms.add(sym)
        opened.append((sym, dec, stake, pos))
        print(
            f"[{LABEL} open] {sym} {dec['direction']} "
            f"{dec.get('votes')} oy ${stake:.2f} · {dec.get('detail')}"
        )

    save_state(state)
    if not opened:
        print(f"[{LABEL} open] {saat} İST — oy yok / çatışma")
        return

    sep = "━" * 26
    lines = []
    for sym, dec, stake, pos in opened:
        name = sym.replace("USDT", "")
        icon = "📈" if dec["direction"] == "UP" else "📉"
        lines.append(
            f"{icon} <b>{name}</b>  {dec['direction']}  {pm_tg_stake(pos)}\n"
            f"   {dec.get('votes')} oy · {dec.get('detail')}"
            f" · ask {float(pos.get('pm_entry_price') or 0):.2f}"
        )
    next_h = f"{(now_tr.hour + 1) % 24:02d}:00"
    tg_send(
        f"{sep}\n🧪 <b>{LABEL}</b>  {now_tr:%d.%m.%Y} {now_tr.hour:02d}:00→{next_h}\n"
        f"<i>A1 + C1#01 + A2#05 V2 oy · sanal $300</i>\n"
        + "\n".join(lines) + "\n"
        f"💰 Bakiye: ${state['balance']:.2f}\n{sep}"
    )
    print(f"[{LABEL} open] {saat} İST — {len(opened)} pozisyon")


def run_close() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    state = load_state()
    history = load_history()
    if not state.get("open_positions"):
        print(f"[{LABEL} close] {saat} İST — açık pozisyon yok")
        return

    lines, failed = [], []
    tur_pnl = 0.0
    for pos in list(state["open_positions"]):
        candle = pm_sanal_slot_candle(pos["symbol"], pos["entry_time_tr"])
        if not candle:
            failed.append(pos)
            continue
        hour_open, hour_close = candle
        s = pm_sanal_settle_trade(pos, hour_open, hour_close)
        win, pnl, actual = s["win"], s["pnl"], s["actual_dir"]
        tur_pnl += pnl
        state["balance"] = round(float(state["balance"]) + pnl, 2)
        state["total_pnl"] = round(float(state.get("total_pnl") or 0) + pnl, 2)
        rec = {
            "symbol": pos["symbol"],
            "predicted_dir": pos["predicted_dir"],
            "actual_dir": actual,
            "win": win,
            "entry_price": s["entry_price"],
            "exit_price": s["exit_price"],
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos.get("entry_hour_tr"),
            "entry_dow": pos.get("entry_dow"),
            "entry_is_weekend": pos.get("entry_is_weekend"),
            "amount": pos.get("amount"),
            "exit_time_tr": now_tr.isoformat(),
            "pnl": pnl,
            "algo_signal": pos.get("algo_signal"),
            "algo_name": pos.get("algo_name", ALGO_NAME),
            "e01_votes": pos.get("e01_votes"),
            "e01_detail": pos.get("e01_detail"),
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug",
                  "pm_fee", "pm_quote_src", "pm_mid_price"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)
        icon = "✅" if win else "❌"
        name = pos["symbol"].replace("USDT", "")
        lines.append(f"{icon} {name}  {pos['predicted_dir']}  {pnl:+.2f}$")

    state["open_positions"] = failed
    save_state(state)
    save_history(history)
    if not lines:
        print(f"[{LABEL} close] {saat} — kapanan yok")
        return
    total = state.get("total_pnl", 0.0)
    closed_all = len(history)
    win_all = sum(1 for t in history if t.get("win"))
    tg_send(
        f"{'━'*26}\n🏁 <b>{LABEL} — {int(saat[:2]):02d}:00</b>\n"
        + "\n".join(lines) + "\n"
        f"Tur {tur_pnl:+.2f}$ · bakiye ${state['balance']:.2f}\n"
        f"Toplam {total:+.2f}$ · {_wr(win_all, closed_all)}\n{'━'*26}"
    )
    print(f"[{LABEL} close] {saat} İST — {len(lines)} kapandı")


def run_preview() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    print(f"{LABEL} önizleme — {now_tr:%d.%m.%Y %H:%M} İST  saat {now_tr.hour:02d}")
    for sym in SYMBOLS:
        dec = decide(sym, now_tr.hour)
        flag = "AÇ" if dec.get("allow") else "YOK"
        print(f"  {sym:8s} {flag:3s}  {dec.get('direction') or '—':4s}  "
              f"${float(dec.get('stake') or 0):.0f}  {dec.get('detail')}")


def run_stats() -> None:
    history, state = load_history(), load_state()
    if not history:
        print(f"{LABEL} — işlem yok · bakiye ${state.get('balance', 0):.2f}")
        return
    wins = sum(1 for t in history if t.get("win"))
    print(f"{LABEL} — {len(history)} işlem · {_wr(wins, len(history))} · "
          f"${state.get('balance', 0):.2f} · {state.get('total_pnl', 0):+.2f}$")
    by: dict[str, list] = defaultdict(list)
    for t in history:
        by[t["symbol"]].append(t)
    for sym, rows in sorted(by.items()):
        w = sum(1 for t in rows if t.get("win"))
        pnl = sum(float(t.get("pnl") or 0) for t in rows)
        print(f"  {sym:9s} {_wr(w, len(rows)):>16s}  {pnl:+8.2f}$")


def run_weekly() -> None:
    run_stats()


_MODES = {
    "open": run_open, "close": run_close, "preview": run_preview,
    "stats": run_stats, "weekly": run_weekly,
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    fn = _MODES.get(mode)
    if not fn:
        print(f"Bilinmeyen mod: {mode}\nKullanım: {' | '.join(_MODES)}")
        sys.exit(1)
    fn()

"""X1#01 - 13Analiz — sanal Poly saatlik defter.

BTC/ETH/SOL. Gerçek PM emri yok. Cron: :02 close · :03 open.
Başlangıç $300. Kapı: x101_signal (13 katman, ask kenarı).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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

from pm_trader_helpers import (  # noqa: E402
    apply_pm_quote,
    pm_best_ask,
    pm_find_market,
    pm_sanal_settle_trade,
    pm_sanal_slot_candle,
    skip_if_weekend_pause,
)
from telegram_poly_channels import chat_analiz4  # noqa: E402
from x101_signal import SYMBOLS, decide  # noqa: E402

BOT_TOKEN = os.getenv("TELEGRAM_ANALIZ4_BOT_TOKEN", "")
CHAT_ID = chat_analiz4()
_TZ_TR = ZoneInfo("Europe/Istanbul")

STATE_FILE = os.path.join(_DIR, "poly_trader_x101_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_x101_history.json")
LABEL = "X1#01 - 13Analiz"
BOOK_KEY = "x101"
ALGO_NAME = "X1#01 - 13Analiz"
INITIAL_BALANCE = 300.0


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


def pm_prices(symbol: str, now_utc: datetime) -> dict | None:
    et_hour = (now_utc - timedelta(hours=4)).hour
    pm = pm_find_market(symbol, et_hour, now_utc)
    if not pm or pm.get("closed"):
        return None
    op = pm.get("outcome_prices") or []
    if len(op) < 2:
        return None
    try:
        up_mid, down_mid = float(op[0]), float(op[1])
    except (ValueError, TypeError):
        return None
    up_ask = pm_best_ask(pm["up_token"])
    down_ask = pm_best_ask(pm["down_token"])
    up_p = up_ask if up_ask is not None else up_mid
    down_p = down_ask if down_ask is not None else down_mid
    if not (0.01 < up_p < 0.99 and 0.01 < down_p < 0.99):
        return None
    return {
        "slug": pm["slug"],
        "title": pm.get("title", ""),
        "up": up_p,
        "down": down_p,
        "quote_src": "ask" if (up_ask is not None and down_ask is not None) else "mid",
        "up_mid": round(up_mid, 4),
        "down_mid": round(down_mid, 4),
        "overround": round(up_p + down_p - 1.0, 4),
    }


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
        mkt = pm_prices(sym, now)
        dec = decide(
            sym, now_tr, mkt=mkt, history=history,
            open_syms=open_syms, balance=balance,
        )
        if not dec.get("allow"):
            skipped.append((sym, dec.get("verdict") or "kapı kapalı"))
            continue
        stake = float(dec.get("stake") or 0)
        if stake <= 0 or stake > balance:
            skipped.append((sym, "bakiye/kademe"))
            continue
        pos = {
            "symbol": sym,
            "predicted_dir": dec["direction"],
            "entry_price": (dec.get("model") or {}).get("ptb"),
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": now_tr.hour,
            "entry_dow": now_tr.weekday(),
            "entry_is_weekend": now_tr.weekday() >= 5,
            "amount": stake,
            "algo_signal": dec["direction"],
            "algo_name": ALGO_NAME,
            "x101_score": dec.get("score"),
            "x101_verdict": dec.get("verdict"),
            "x101_edge": dec.get("edge"),
            "x101_regime": dec.get("regime"),
            "x101_checklist": dec.get("checklist"),
        }
        apply_pm_quote(pos, sym, dec["direction"], stake, now)
        if not pos.get("pm_slug"):
            skipped.append((sym, "PM dolum yok"))
            continue
        state["open_positions"].append(pos)
        open_syms.add(sym)
        opened.append((sym, dec, stake, pos))
        print(f"[{LABEL} open] {sym} {dec['direction']} skor {dec['score']} "
              f"kenar +{(dec.get('edge') or 0)*100:.1f}p ${stake:.2f}")

    save_state(state)
    for sym, reason in skipped:
        print(f"[{LABEL} open] {sym} — {reason}")
    if not opened:
        print(f"[{LABEL} open] {saat} İST — kapı açılmadı")
        return

    sep = "━" * 26
    lines = []
    for sym, dec, stake, pos in opened:
        name = sym.replace("USDT", "")
        icon = "📈" if dec["direction"] == "UP" else "📉"
        lines.append(
            f"{icon} <b>{name}</b>  {dec['direction']}  💵{stake:.2f}$\n"
            f"   skor {dec['score']:.0f} · kenar +{(dec.get('edge') or 0)*100:.1f}p"
            f" · ask {float(pos.get('pm_entry_price') or 0):.2f}"
        )
    next_h = f"{(now_tr.hour + 1) % 24:02d}:00"
    tg_send(
        f"{sep}\n🧪 <b>{LABEL}</b>  {now_tr:%d.%m.%Y} {now_tr.hour:02d}:00→{next_h}\n"
        f"<i>13 katman · ask kenarı · sanal $300</i>\n"
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
            "x101_score": pos.get("x101_score"),
            "x101_edge": pos.get("x101_edge"),
            "x101_regime": pos.get("x101_regime"),
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
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    print(f"{LABEL} önizleme — {now_tr:%d.%m.%Y %H:%M} İST")
    hist = load_history()
    for sym in SYMBOLS:
        mkt = pm_prices(sym, now)
        dec = decide(sym, now_tr, mkt=mkt, history=hist, balance=INITIAL_BALANCE)
        print(f"\n{sym}  {dec['verdict']}")
        print(f"  skor {dec['score']:.1f}  aday {dec.get('candidate')}  "
              f"kenar {((dec.get('edge') or 0)*100):+.1f}p")
        for it in dec.get("checklist") or []:
            mark = "✓" if it["ok"] else "·"
            print(f"  {mark} {it['id']:2}. {it['name']:12} {it['score']:5.1f}  {it['reason']}")


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

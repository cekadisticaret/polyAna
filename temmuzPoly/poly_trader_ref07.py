"""REF07 sanal defter. Gerçek PM yok.

Uç nokta dönüşü + A2#05 (Mean Reversion Z-Score) onayı:
  1. Saatlik yolda ekstrem oluşmuş (≥33 bps) ve geri çekilmiş (≥10 bps).
  2. A2#05 sinyali ters yöndeyse işlem atlanır; aynı yön veya nötr ise açılır.
  3. Token fiyatı 0.25–0.30 bandında olmalı (altın dilim).
  4. ETH geçici olarak devre dışı (WR %0).

Kasa $1000 · ask-tier dinamik kademe ($9/$12/$14/$16/$18).
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

from ref07_signal import ASK_MAX, ASK_MIN, SYMBOLS, decide  # noqa: E402
from pm_trader_helpers import (                              # noqa: E402
    apply_pm_quote,
    pm_sanal_settle_trade,
    pm_sanal_slot_candle,
    resolve_open_slot_gates,
    skip_if_weekend_pause,
    slot_amount_log,
    symbol_wr_amount_for_book,
)

_TZ_TR = ZoneInfo("Europe/Istanbul")

STATE_FILE   = os.path.join(_DIR, "poly_trader_ref07_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_ref07_history.json")
LABEL        = "REF07"
BOOK_KEY     = "ref07"
ALGO_NAME    = "REF07 · uç dönüş + A2#05"
INITIAL_BALANCE        = 1000.0
REF07_MIN_PROFIT_RATIO = 0.50

_ENTRY_LO = 10
_ENTRY_HI = 50

_A2_05_SIGNAL_FILE = "/tmp/algo_signals_v2.json"

# ── Ask seviyesi kademe tablosu ─────────────────────────────────
_ASK_TIER_MIN_N  = 5
_ASK_BAND_MIN_N  = 2
_ASK_DEFAULT_AMT = 12.0


def ask_tier_amount(history: list, ask_price: float) -> float:
    """Geçmiş WR'ye göre ask-bazlı stake döndürür (REF04 ile aynı mantık)."""
    def _wr_to_amt(wr: float) -> float:
        if wr >= 0.65: return 20.0
        if wr >= 0.50: return 16.0
        return 12.0

    lvl = round(ask_price, 2)
    band_lo = round(int(ask_price * 20) / 20, 2)
    band_hi = round(band_lo + 0.05, 2)

    lvl_w = lvl_t = 0
    band_w = band_t = 0
    for t in history:
        a = float(t.get("pm_entry_price") or 0)
        if a <= 0:
            continue
        a_r = round(a, 2)
        if a_r == lvl:
            lvl_t += 1
            if t.get("win"): lvl_w += 1
        if band_lo <= a_r < band_hi:
            band_t += 1
            if t.get("win"): band_w += 1

    if lvl_t >= _ASK_TIER_MIN_N:
        return _wr_to_amt(lvl_w / lvl_t)
    if band_t >= _ASK_BAND_MIN_N:
        return _wr_to_amt(band_w / band_t)
    return _ASK_DEFAULT_AMT


# ── State / History ────────────────────────────────────────────
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


# ── A2#05 sinyal okuma ────────────────────────────────────────
def _get_a2_05_dir(sym: str) -> str | None:
    """A2#05 (Mean Reversion Z-Score) yönünü döndürür: 'UP', 'DOWN' veya None.

    /tmp/algo_signals_v2.json → signals["5"]["BTC"/"ETH"/"SOL"]
    NEUTRAL veya okunamazsa None döner → trader nötr sayar ve açar.
    """
    try:
        sym_key = sym.replace("USDT", "")  # BTCUSDT → BTC
        data = json.load(open(_A2_05_SIGNAL_FILE))
        val = data.get("signals", {}).get("5", {}).get(sym_key)
        if val in ("UP", "DOWN"):
            return val
        return None  # NEUTRAL veya başka değer
    except Exception:
        return None


# ── OPEN ───────────────────────────────────────────────────────
async def run_open() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    if skip_if_weekend_pause(LABEL, "open", now_tr):
        return
    if now_tr.minute < _ENTRY_LO or now_tr.minute > _ENTRY_HI:
        return

    state   = load_state()
    history = load_history()
    balance = float(state.get("balance") or INITIAL_BALANCE)
    open_syms = {p.get("symbol") for p in (state.get("open_positions") or [])}
    opened, skipped = [], []
    verbose = os.environ.get("REF07_TICK_VERBOSE") == "1"

    for sym in SYMBOLS:
        if sym in open_syms:
            skipped.append((sym, "zaten açık"))
            continue

        # 1. Saatlik yol sinyali
        dec = decide(sym, now_tr.minute)
        if not dec.get("allow"):
            skipped.append((sym, dec.get("reason") or "kapı kapalı"))
            if verbose:
                print(f"[{LABEL} open] {sym} — {dec.get('reason')} · {dec.get('detail')}")
            continue

        # 2. A2#05 onayı (dosya okuma, sync)
        a2_dir = _get_a2_05_dir(sym)
        if a2_dir is not None and a2_dir != dec["direction"]:
            reason = f"A2#05 ters yön ({a2_dir}) — REF07 {dec['direction']}"
            skipped.append((sym, reason))
            if verbose:
                print(f"[{LABEL} open] {sym} — {reason}")
            continue

        # 3. Stake
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
            "ref07_mode":         dec.get("mode"),
            "ref07_detail":       dec.get("detail"),
            "ref07_extreme_bps":  dec.get("extreme_bps"),
            "ref07_pullback_bps": dec.get("pullback_bps"),
            "ref07_extreme_mn":   dec.get("extreme_mn"),
            "ref07_path_bps":     dec.get("path_bps"),
            "ref07_entry_min":    now_tr.minute,
            "ref07_a2_05_dir":    a2_dir,
        }

        # 4. PM kotasyonu + kâr kapısı
        apply_pm_quote(pos, sym, dec["direction"], stake, now,
                       min_profit_ratio=REF07_MIN_PROFIT_RATIO)
        if pos.get("entry_skip"):
            skipped.append((sym, pos["entry_skip"]))
            print(f"[{LABEL} open] {sym} — {pos['entry_skip']}")
            continue

        # 5. Ask sınırları
        ask = pos.get("pm_entry_price")
        try:
            ask_f = float(ask) if ask is not None else None
        except (TypeError, ValueError):
            ask_f = None
        lo = dec.get("ask_min", ASK_MIN)
        hi = dec.get("ask_max", ASK_MAX)
        if ask_f is not None and lo is not None and ask_f < float(lo):
            skipped.append((sym, f"ask {ask_f:.2f} < {lo}"))
            print(f"[{LABEL} open] {sym} — ask_min {lo} · gelen {ask_f:.2f} (piyasa çok olumsuz)")
            continue
        if ask_f is not None and hi is not None and ask_f > float(hi):
            skipped.append((sym, f"ask {ask_f:.2f} > {hi}"))
            print(f"[{LABEL} open] {sym} — ask_max {hi} · gelen {ask_f:.2f}")
            continue

        # 5b. Ask-tier kademe ayarı
        if ask_f and ask_f > 0:
            tier_stake = ask_tier_amount(history, ask_f)
            if tier_stake != stake:
                ratio = tier_stake / stake
                pos["amount"]   = tier_stake
                pos["pm_spent"] = round(float(pos.get("pm_spent") or 0) * ratio, 4)
                pos["pm_size"]  = round(float(pos.get("pm_size")  or 0) * ratio, 4)
                pos["to_win"]   = round(float(pos.get("to_win")   or 0) * ratio, 4)
                pos["pm_fee"]   = round(float(pos.get("pm_fee")   or 0) * ratio, 4)
                pos["ref07_tier_ask"] = ask_f
                pos["ref07_tier_amt"] = tier_stake
                stake = tier_stake

        if not pos.get("pm_slug"):
            skipped.append((sym, "PM dolum yok"))
            continue

        state["open_positions"].append(pos)
        open_syms.add(sym)
        opened.append((sym, dec, stake, pos))
        a2_note  = f" · A2#05 {a2_dir}" if a2_dir else " · A2#05 nötr"
        tier_note = f" · ask@{ask_f:.2f}→${stake:.0f}" if ask_f else ""
        print(f"[{LABEL} open] {sym} {dec['direction']} ${stake:.2f} · {dec.get('detail')}{a2_note}{tier_note}")

    save_state(state)
    if not opened:
        if verbose:
            print(f"[{LABEL} open] {saat} İST — sinyal yok ({len(skipped)} skip)")
        return
    print(f"[{LABEL} open] {saat} İST — {len(opened)} pozisyon")


# ── CLOSE ──────────────────────────────────────────────────────
def run_close() -> None:
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat    = now_tr.strftime("%H:%M")
    state   = load_state()
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
            "ref07_mode":         pos.get("ref07_mode"),
            "ref07_detail":       pos.get("ref07_detail"),
            "ref07_extreme_bps":  pos.get("ref07_extreme_bps"),
            "ref07_pullback_bps": pos.get("ref07_pullback_bps"),
            "ref07_extreme_mn":   pos.get("ref07_extreme_mn"),
            "ref07_path_bps":     pos.get("ref07_path_bps"),
            "ref07_entry_min":    pos.get("ref07_entry_min"),
            "ref07_a2_05_dir":    pos.get("ref07_a2_05_dir"),
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


# ── PREVIEW ────────────────────────────────────────────────────
def run_preview() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    print(f"{LABEL} önizleme — {now_tr:%d.%m.%Y %H:%M} İST  dakika {now_tr.minute}")
    for sym in SYMBOLS:
        dec  = decide(sym, now_tr.minute)
        flag = "AÇ" if dec.get("allow") else "YOK"
        ext  = dec.get("extreme_bps")
        pb   = dec.get("pullback_bps")
        ext_str = f" ext={ext:+.1f}" if ext is not None else ""
        pb_str  = f" pb={pb:.1f}" if pb is not None else ""
        a2_dir = _get_a2_05_dir(sym)
        a2_str = f" A2#05={a2_dir}" if a2_dir else " A2#05=nötr"
        print(f"  {sym:9s} {flag:3s}  {dec.get('direction') or '—':4s}"
              f"  {dec.get('detail') or dec.get('reason')}{ext_str}{pb_str}{a2_str}")


# ── STATS ──────────────────────────────────────────────────────
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
        a2_ok = [t for t in rows if t.get("ref07_a2_05_dir")]
        a2_n  = [t for t in rows if not t.get("ref07_a2_05_dir")]
        print(f"  {sym:9s} {_wr(w, len(rows)):>16s}  {p:+8.2f}$"
              f"  A2_onay={len(a2_ok)}  A2_nötr={len(a2_n)}")


# ── WEEKLY ─────────────────────────────────────────────────────
def run_weekly() -> None:
    run_stats()


# ── Giriş noktası ──────────────────────────────────────────────
_MODES = {
    "open":    lambda: asyncio.run(run_open()),
    "close":   run_close,
    "preview": run_preview,
    "stats":   run_stats,
    "weekly":  run_weekly,
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    fn = _MODES.get(mode)
    if not fn:
        print(f"Bilinmeyen mod: {mode}. Geçerli: {list(_MODES)}")
        sys.exit(1)
    fn()

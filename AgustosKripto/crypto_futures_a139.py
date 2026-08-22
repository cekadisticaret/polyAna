#!/usr/bin/env python3
"""A1#39 Live — Test defterinin Binance Futures aynası.

Sinyal / TF seçimi / ters kapanış / çıkış rejimi
`/kripto/test/a1_39` (H1 Profesyonel Kombinasyon) ile aynı.
Fark: gerçek emir, $20×7x, en fazla 4 açık.

CR6 (4-algo oy) dokunulmaz — kendi pause'u kapalı kalır.

CLI:
  python3 crypto_futures_a139.py close
  python3 crypto_futures_a139.py open
  python3 crypto_futures_a139.py trail
  python3 crypto_futures_a139.py scan
  python3 crypto_futures_a139.py status
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
_TEST = os.path.join(_DIR, "Test")
sys.path.insert(0, _DIR)
sys.path.insert(0, os.path.join(_DIR, "Algoritmalar"))
sys.path.insert(0, os.path.join(_ROOT, "temmuzPoly"))

_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from atr_profit_lock import (  # noqa: E402
    LOSS_STOP_MIN_AGE_MIN,
    atr_from_klines,
    init_lock_fields,
    lock_summary,
    should_loss_stop,
    should_stop_out,
    update_lock,
)
from crypto_futures_trader import (  # noqa: E402
    close_market,
    estimate_qty,
    get_positions,
    load_config,
    open_market,
    usdt_balance,
    _client,
    _is_dry,
)
from exit_policy import policy_for  # noqa: E402
from fee_utils import estimate_fee, get_taker_rate, net_pnl  # noqa: E402
from virtual_book import fetch_all_klines, now_tr_iso, position_age_minutes  # noqa: E402


def _load_mod(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_test_cat = _load_mod("a139_test_catalog", os.path.join(_TEST, "catalog.py"))
_test_sig = _load_mod("a139_test_signals", os.path.join(_TEST, "signals.py"))
_test_eng = _load_mod("a139_test_engine", os.path.join(_TEST, "engine.py"))

TEST_SYMBOLS = list(_test_cat.TEST_SYMBOLS)
signal_for_book = _test_sig.signal_for_book
build_candidates = _test_eng.build_candidates
find_reversal_closes = _test_eng.find_reversal_closes
klines_for_positions = _test_eng.klines_for_positions

_TZ_TR = ZoneInfo("Europe/Istanbul")
STATE_FILE = os.path.join(_DIR, "crypto_futures_a139_state.json")
HISTORY_FILE = os.path.join(_DIR, "crypto_futures_a139_history.json")
CONTROL_FILE = os.path.join(_DIR, "crypto_futures_a139_control.json")
USDT_CACHE_FILE = os.path.join(_DIR, "crypto_futures_a139_usdt.json")
TEST_HISTORY = os.path.join(_TEST, "data", "test_a1_39_history.json")
LABEL = "A1#39 Live"
ALGO_NAME = "A1#39 H1 Profesyonel Kombinasyon"
MARGIN_USD = 20.0
LEVERAGE = 7
TOP_N_DEFAULT = 4
TOP_N_MIN = 1
TOP_N_MAX = 4
STATE_LOCK_WAIT_SEC = 90.0
EXIT_POLICY = policy_for("Test")


def _book() -> dict:
    for b in _test_cat.ALL_BOOKS:
        if (b.get("uid") or "") == "a1_39":
            return b
    raise RuntimeError("Test kataloğunda a1_39 yok")


def _env_enabled() -> bool:
    return os.getenv("CRYPTO_FUTURES_A139_ENABLED", "true").lower() in ("1", "true", "yes")


def _clamp_top_n(n) -> int:
    try:
        v = int(n)
    except Exception:
        v = TOP_N_DEFAULT
    return max(TOP_N_MIN, min(TOP_N_MAX, v))


def get_live_control() -> dict:
    data = {
        "live_paused": False,
        "top_n": TOP_N_DEFAULT,
        "updated_at_tr": None,
        "updated_by": None,
    }
    if os.path.exists(CONTROL_FILE):
        try:
            with open(CONTROL_FILE) as f:
                raw = json.load(f) or {}
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            pass
    data["live_paused"] = bool(data.get("live_paused"))
    data["top_n"] = _clamp_top_n(data.get("top_n", TOP_N_DEFAULT))
    return data


def get_top_n() -> int:
    return int(get_live_control().get("top_n") or TOP_N_DEFAULT)


def is_live_paused() -> bool:
    return bool(get_live_control().get("live_paused"))


def save_live_control(data: dict, *, source: str = "dashboard") -> dict:
    out = get_live_control()
    out.update(data or {})
    out["live_paused"] = bool(out.get("live_paused"))
    out["top_n"] = _clamp_top_n(out.get("top_n", TOP_N_DEFAULT))
    out["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    out["updated_by"] = source
    tmp = CONTROL_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONTROL_FILE)
    return out


def set_live_paused(paused: bool, *, source: str = "dashboard") -> dict:
    return save_live_control({"live_paused": bool(paused)}, source=source)


def set_top_n(n: int, *, source: str = "dashboard") -> dict:
    return save_live_control({"top_n": _clamp_top_n(n)}, source=source)


def toggle_live_paused(*, source: str = "dashboard") -> dict:
    return set_live_paused(not is_live_paused(), source=source)


def _opens_allowed() -> bool:
    return _env_enabled() and not is_live_paused()


def _manage_allowed() -> bool:
    return _env_enabled()


def _atomic_write_json(path: str, data) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class StateLockBusy(RuntimeError):
    pass


@contextlib.contextmanager
def state_lock(wait_sec: float | None = None):
    limit = STATE_LOCK_WAIT_SEC if wait_sec is None else float(wait_sec)
    lock_path = STATE_FILE + ".lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    fh = open(lock_path, "w")
    deadline = time.monotonic() + limit
    got = False
    try:
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                got = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise StateLockBusy(
                        f"state kilidi {limit:.0f}s içinde alınamadı",
                    ) from None
                time.sleep(0.5)
        yield
    finally:
        if got:
            with contextlib.suppress(Exception):
                fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _load_usdt_cache() -> dict | None:
    if not os.path.exists(USDT_CACHE_FILE):
        return None
    try:
        with open(USDT_CACHE_FILE) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        bal = data.get("balance")
        if bal is None:
            return None
        return {
            "asset": data.get("asset") or "USDT",
            "balance": float(bal),
            "available": float(data["available"]) if data.get("available") is not None else None,
            "cross_wallet": float(data["cross_wallet"]) if data.get("cross_wallet") is not None else None,
            "cached": True,
            "cached_at_tr": data.get("cached_at_tr") or "",
        }
    except Exception:
        return None


def _save_usdt_cache(usdt: dict) -> None:
    if not usdt or usdt.get("balance") is None:
        return
    try:
        with open(USDT_CACHE_FILE, "w") as f:
            json.dump({
                "asset": usdt.get("asset") or "USDT",
                "balance": float(usdt["balance"]),
                "available": usdt.get("available"),
                "cross_wallet": usdt.get("cross_wallet"),
                "cached_at_tr": now_tr_iso(),
            }, f)
    except Exception:
        pass


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "open_positions": [],
        "total_pnl": 0.0,
        "total_commission": 0.0,
        "updated_at_tr": "",
        "last_open_slot": "",
        "atr_skip_syms": [],
    }


def save_state(state: dict) -> None:
    state["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    _atomic_write_json(STATE_FILE, state)


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history: list) -> None:
    _atomic_write_json(HISTORY_FILE, history)


def _load_test_history() -> list:
    """TF seçimi Test a1_39 geçmişinden — canlı defter boşken de aynı 1h/4h."""
    try:
        with open(TEST_HISTORY) as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _tf_history() -> list:
    live = load_history()
    paper = _load_test_history()
    return list(paper) + list(live)


def _slot_key() -> str:
    return datetime.now(_TZ_TR).strftime("%Y-%m-%d %H:00")


def _closed_order_ids(history: list | None = None) -> set:
    rows = load_history() if history is None else history
    out = set()
    for r in rows:
        if not isinstance(r, dict) or r.get("exit_price") is None:
            continue
        oid = r.get("order_id")
        if oid:
            out.add(str(oid))
    return out


def _drop_closed_ghosts(opens: list, history: list | None = None) -> tuple[list, list]:
    done = _closed_order_ids(history)
    if not done:
        return list(opens), []
    keep, ghosts = [], []
    for p in opens:
        oid = p.get("order_id")
        (ghosts if oid and str(oid) in done else keep).append(p)
    return keep, ghosts


def _close_local_only(pos: dict, *, reason: str) -> dict:
    """Binance zaten düz — yeni emir yok, yalnız defter satırı."""
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or 0)
    side = pos.get("side") or "LONG"
    sym = pos.get("symbol") or ""
    try:
        px = float(_client().mark_price(sym))
    except Exception:
        px = entry
    if px <= 0:
        px = entry
    if side == "LONG":
        pnl_gross = (px - entry) * qty
    else:
        pnl_gross = (entry - px) * qty
    pnl_gross = round(pnl_gross, 4)
    rate = get_taker_rate(None, sym or "BTCUSDT", cfg=load_config())
    entry_notional = float(pos.get("notional") or (entry * qty))
    exit_notional = px * qty
    entry_fee = float(pos.get("entry_fee") or 0)
    if entry_fee <= 0:
        entry_fee = estimate_fee(entry_notional, rate)
    exit_fee = estimate_fee(exit_notional, rate)
    commission = round(entry_fee + exit_fee, 6)
    pnl = net_pnl(pnl_gross, commission)
    return {
        **pos,
        "exit_price": round(px, 8),
        "exit_time_tr": now_tr_iso(),
        "pnl_gross": pnl_gross,
        "commission": commission,
        "entry_fee": round(entry_fee, 6),
        "exit_fee": round(exit_fee, 6),
        "pnl": round(pnl, 4),
        "close_reason": reason,
        "close_order_id": None,
        "dry_run": False,
    }


def _reconcile_binance(state: dict, history: list) -> list:
    """Binance'te olmayan yerel açıkları kapat. Emir göndermez."""
    opens = list(state.get("open_positions") or [])
    if not opens:
        return []
    try:
        live = {(p.get("symbol") or "").upper() for p in get_positions()}
    except Exception as e:
        print(f"[{LABEL}] reconcile: {e}")
        return []
    closed = []
    kept = []
    for pos in opens:
        sym = (pos.get("symbol") or "").upper()
        if sym in live:
            kept.append(pos)
            continue
        rec = _close_local_only(pos, reason="binance_sync")
        _record_close(state, history, rec)
        closed.append(rec)
        print(f"[{LABEL}] SYNC {sym} Binance'te yok — defterden düşüldü pnl={rec.get('pnl')}")
    if closed:
        state["open_positions"] = kept
    return closed


def run_sync() -> dict:
    try:
        with state_lock():
            state = load_state()
            history = load_history()
            closed = _reconcile_binance(state, history)
            if closed:
                save_state(state)
                save_history(history)
            return {
                "ok": True,
                "closed": len(closed),
                "symbols": [c.get("symbol") for c in closed],
                "held": len(state.get("open_positions") or []),
            }
    except StateLockBusy as e:
        print(f"[{LABEL}] sync atlandı — {e}")
        return {"ok": False, "skipped": "locked", "closed": 0}


def _apply_policy(pos: dict) -> dict:
    out = dict(pos)
    ls = EXIT_POLICY.get("loss_stop_atr")
    if ls is not None:
        out["loss_stop_atr"] = float(ls)
    if not out.get("max_hold_h") and EXIT_POLICY.get("max_hold_h"):
        out["max_hold_h"] = float(EXIT_POLICY["max_hold_h"])
    return out


def _hold_expired(pos: dict) -> bool:
    limit = float(pos.get("max_hold_h") or EXIT_POLICY.get("max_hold_h") or 0)
    if limit <= 0:
        return False
    return position_age_minutes(pos) >= limit * 60.0


def _live_upnl_net(pos: dict, mark: float | None = None) -> tuple[float, float, float]:
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or 0)
    side = pos.get("side") or "LONG"
    px = float(mark) if mark and mark > 0 else 0.0
    if px <= 0:
        try:
            px = _client().mark_price(pos["symbol"])
        except Exception:
            px = entry
    if side == "LONG":
        upnl_gross = (px - entry) * qty
    else:
        upnl_gross = (entry - px) * qty
    upnl_gross = round(upnl_gross, 4)
    entry_notional = float(pos.get("notional") or (entry * qty))
    exit_notional = px * qty
    entry_fee = float(pos.get("entry_fee") or 0)
    rate = get_taker_rate(None, pos.get("symbol") or "BTCUSDT", cfg=load_config())
    if entry_fee <= 0:
        entry_fee = estimate_fee(entry_notional, rate)
    exit_fee = estimate_fee(exit_notional, rate)
    return upnl_gross, net_pnl(upnl_gross, entry_fee + exit_fee), px


def _close_one(pos: dict, *, reason: str) -> dict:
    sym = pos.get("symbol")
    qty = float(pos.get("qty") or 0)
    r = close_market(sym, qty=qty if qty > 0 else None)
    exit_px = float(r.get("mark_price") or pos.get("entry_price") or 0)
    entry = float(pos.get("entry_price") or 0)
    side = pos.get("side") or "LONG"
    q = float(r.get("qty") or qty)
    if r.get("pnl_gross") is not None:
        pnl_gross = float(r["pnl_gross"])
    elif side == "LONG":
        pnl_gross = (exit_px - entry) * q
    else:
        pnl_gross = (entry - exit_px) * q
    pnl_gross = round(pnl_gross, 4)
    commission = float(r.get("commission") or 0)
    entry_fee = float(r.get("entry_fee") or pos.get("entry_fee") or 0)
    exit_fee = float(r.get("exit_fee") or 0)
    if commission <= 0:
        rate = get_taker_rate(None, sym or "BTCUSDT", cfg=load_config())
        entry_notional = float(pos.get("notional") or (entry * q))
        exit_notional = exit_px * q
        if entry_fee <= 0:
            entry_fee = estimate_fee(entry_notional, rate)
        if exit_fee <= 0:
            exit_fee = estimate_fee(exit_notional, rate)
        commission = round(entry_fee + exit_fee, 6)
    pnl = float(r["pnl"]) if r.get("pnl") is not None else net_pnl(pnl_gross, commission)
    return {
        **pos,
        "exit_price": exit_px,
        "exit_time_tr": r.get("exit_time_tr"),
        "pnl_gross": pnl_gross,
        "commission": round(commission, 6),
        "entry_fee": round(entry_fee, 6),
        "exit_fee": round(exit_fee, 6),
        "pnl": round(pnl, 4),
        "close_reason": reason,
        "close_order_id": (r.get("order") or {}).get("orderId"),
        "dry_run": r.get("dry_run"),
    }


def _record_close(state: dict, history: list, rec: dict) -> None:
    history.append(rec)
    state["total_pnl"] = round(float(state.get("total_pnl") or 0) + float(rec.get("pnl") or 0), 4)
    state["total_commission"] = round(
        float(state.get("total_commission") or 0) + float(rec.get("commission") or 0), 6,
    )


def _build_cands(kl_1h: dict, kl_4h: dict) -> list[dict]:
    book = _book()
    cands = build_candidates(
        book, kl_1h, kl_4h, _tf_history(),
        symbols=TEST_SYMBOLS,
        signal_for_book=signal_for_book,
    )
    for c in cands:
        c["algo"] = ALGO_NAME
    return cands


def _place(cand: dict, *, kl_cache: dict) -> dict | None:
    sym = (cand.get("symbol") or "").upper()
    side = cand.get("side")
    if not sym or side not in ("LONG", "SHORT"):
        return None
    est = estimate_qty(sym, MARGIN_USD, LEVERAGE)
    if not est.get("ok"):
        print(f"[{LABEL}] {sym} min lot yok — atlandı")
        return None
    r = open_market(
        sym,
        side,
        margin_usd=MARGIN_USD,
        leverage=LEVERAGE,
        margin_type="ISOLATED",
        skip_max_positions=True,
        allow_excluded=True,
        skip_allowlist=True,
    )
    if not r.get("ok"):
        print(f"[{LABEL}] {sym} giriş yok ({r.get('reason') or 'fail'})")
        return None
    entry = float(
        r.get("entry_price")
        or (r.get("order") or {}).get("avgPrice")
        or r.get("mark_price")
        or 0
    )
    iv = str(cand.get("interval") or "1h")
    kl_atr = kl_cache.get(f"{sym}|{iv}") or []
    if len(kl_atr) < 30:
        try:
            from virtual_book import fetch_klines
            kl_atr = fetch_klines(sym, iv, 80)
        except Exception:
            kl_atr = []
    pos = init_lock_fields(
        {
            "strategy": LABEL,
            "symbol": sym,
            "side": side,
            "signal": cand.get("signal") or ("UP" if side == "LONG" else "DOWN"),
            "score": cand.get("score"),
            "algo": ALGO_NAME,
            "interval": iv,
            "qty": float(r.get("qty") or 0),
            "leverage": LEVERAGE,
            "margin_usd": MARGIN_USD,
            "entry_price": entry,
            "notional": float(r.get("notional") or 0),
            "entry_time_tr": r.get("entry_time_tr") or now_tr_iso(),
            "slot": _slot_key(),
            "order_id": (r.get("order") or {}).get("orderId"),
            "entry_type": "taker",
            "entry_fee": r.get("entry_fee"),
            "dry_run": r.get("dry_run"),
            "virtual": False,
            "max_hold_h": float(EXIT_POLICY.get("max_hold_h") or 24),
            "loss_stop_atr": float(EXIT_POLICY.get("loss_stop_atr") or 3.0),
        },
        atr=atr_from_klines(kl_atr),
        price=entry,
    )
    return pos


def _open_from_cands(
    state: dict,
    cands: list[dict],
    *,
    kl_cache: dict,
    bypass_slot_gate: bool,
    blocked: set[str],
) -> dict:
    existing = list(state.get("open_positions") or [])
    held = {str(p.get("symbol") or "").upper() for p in existing if p.get("symbol")}
    top_n = get_top_n()
    slot = _slot_key()
    if not bypass_slot_gate and state.get("last_open_slot") == slot:
        print(f"[{LABEL}] open: aynı slot {slot} — atlandı (held={len(existing)})")
        return {"ok": False, "skipped": "same_slot", "opened": 0, "held": len(existing)}
    slots_left = max(0, top_n - len(existing))
    if slots_left <= 0:
        print(f"[{LABEL}] open: kota dolu held={len(existing)}/{top_n}")
        return {"ok": False, "skipped": "max_open", "opened": 0, "held": len(existing)}

    opened = []
    errors = []
    for cand in cands:
        if len(opened) >= slots_left:
            break
        sym = (cand.get("symbol") or "").upper()
        if not sym or sym in held or sym in blocked:
            continue
        try:
            pos = _place(cand, kl_cache=kl_cache)
            if not pos:
                errors.append({"symbol": sym, "error": "not_filled"})
                continue
            opened.append(pos)
            held.add(sym)
            print(
                f"[{LABEL}] OPEN {pos['side']} {sym} qty={pos['qty']} "
                f"{pos.get('interval')} score={cand.get('score')} "
                f"dry={pos.get('dry_run')}"
            )
        except Exception as e:
            print(f"[{LABEL}] OPEN hata {sym}: {e}")
            errors.append({"symbol": sym, "error": str(e)})

    state["open_positions"] = existing + opened
    if not bypass_slot_gate:
        state["last_open_slot"] = slot
    save_state(state)
    return {
        "ok": True,
        "opened": len(opened),
        "positions": opened,
        "held": len(existing),
        "errors": errors,
        "top_n": top_n,
    }


def run_open() -> dict:
    if not _opens_allowed():
        why = "paused" if is_live_paused() else "disabled"
        print(f"[{LABEL}] open atlandı — {why}")
        return {"ok": False, "skipped": why}
    try:
        with state_lock():
            return _run_open_locked(bypass_slot_gate=False)
    except StateLockBusy as e:
        print(f"[{LABEL}] open atlandı — {e}")
        return {"ok": False, "skipped": "locked"}


def _run_open_locked(*, bypass_slot_gate: bool) -> dict:
    state = load_state()
    existing, ghosts = _drop_closed_ghosts(list(state.get("open_positions") or []))
    if ghosts:
        state["open_positions"] = existing
        save_state(state)
    blocked = {str(s).upper() for s in (state.get("atr_skip_syms") or []) if s}
    if not bypass_slot_gate:
        state["atr_skip_syms"] = []
        save_state(state)
        blocked = set()
    kl_1h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="1h")
    kl_4h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="4h")
    cache = {
        **{f"{s}|1h": kl_1h.get(s, []) for s in TEST_SYMBOLS},
        **{f"{s}|4h": kl_4h.get(s, []) for s in TEST_SYMBOLS},
    }
    cands = _build_cands(kl_1h, kl_4h)
    print(
        f"[{LABEL}] aday={len(cands)} held={len(state.get('open_positions') or [])} "
        f"max={get_top_n()} ${MARGIN_USD:.0f}×{LEVERAGE}x"
    )
    return _open_from_cands(
        state, cands, kl_cache=cache,
        bypass_slot_gate=bypass_slot_gate, blocked=blocked,
    )


def run_close() -> dict:
    """Test ile aynı: saatlik zorunlu kapanış yok, yalnız 24s tavan."""
    if not _manage_allowed():
        print(f"[{LABEL}] close atlandı — disabled")
        return {"ok": False, "skipped": "disabled", "closed": 0}
    try:
        with state_lock():
            return _run_close_locked()
    except StateLockBusy as e:
        print(f"[{LABEL}] close atlandı — {e}")
        return {"ok": False, "skipped": "locked", "closed": 0}


def _run_close_locked() -> dict:
    state = load_state()
    history = load_history()
    synced = _reconcile_binance(state, history)
    if synced:
        save_state(state)
        save_history(history)
    opens, ghosts = _drop_closed_ghosts(list(state.get("open_positions") or []), history)
    if ghosts:
        state["open_positions"] = opens
        save_state(state)
    if not opens:
        print(f"[{LABEL}] close: açık yok")
        return {"ok": True, "closed": len(synced), "held": 0, "synced": len(synced)}

    closed = []
    remaining = []
    for pos in opens:
        pos = _apply_policy(pos)
        sym = pos.get("symbol")
        try:
            if not _hold_expired(pos):
                remaining.append(pos)
                continue
            rec = _close_one(pos, reason="max_hold")
            _record_close(state, history, rec)
            closed.append(rec)
            print(f"[{LABEL}] CLOSE[max_hold] {rec.get('side')} {sym} pnl={rec.get('pnl', 0):+.4f}")
        except Exception as e:
            print(f"[{LABEL}] CLOSE hata {sym}: {e}")
            remaining.append(pos)

    state["open_positions"] = remaining
    save_state(state)
    save_history(history)
    print(f"[{LABEL}] close kapanan={len(closed)} hold={len(remaining)}")
    return {"ok": True, "closed": len(closed), "held": len(remaining), "trades": closed}


def run_trail() -> dict:
    if not _manage_allowed():
        print(f"[{LABEL}] trail atlandı — disabled")
        return {"ok": False, "skipped": "disabled", "closed": 0}
    try:
        with state_lock():
            return _run_trail_locked()
    except StateLockBusy as e:
        print(f"[{LABEL}] trail atlandı — {e}")
        return {"ok": False, "skipped": "locked", "closed": 0}


def _run_trail_locked() -> dict:
    state = load_state()
    history = load_history()
    synced = _reconcile_binance(state, history)
    if synced:
        save_state(state)
        save_history(history)
    opens, ghosts = _drop_closed_ghosts(list(state.get("open_positions") or []), history)
    if ghosts:
        state["open_positions"] = opens
        save_state(state)
    if not opens:
        return {"ok": True, "closed": len(synced), "updated": 0, "synced": len(synced)}

    closed = []
    remaining = []
    updated = 0
    skip_add: list[str] = []
    for pos in opens:
        pos = _apply_policy(pos)
        sym = pos.get("symbol")
        try:
            if not float(pos.get("atr_usd") or 0):
                iv = str(pos.get("interval") or "1h")
                from virtual_book import fetch_klines
                kl = fetch_klines(sym, iv, 80)
                pos = init_lock_fields(
                    pos,
                    atr=atr_from_klines(kl),
                    price=float(pos.get("entry_price") or 0),
                )
            _g, upnl_net, _px = _live_upnl_net(pos)
            pos2, ch = update_lock(pos, upnl_net)
            if ch:
                updated += 1
            age_min = position_age_minutes(pos2)
            if _hold_expired(pos2):
                rec = _close_one(pos2, reason="max_hold")
                _record_close(state, history, rec)
                closed.append(rec)
                if sym:
                    skip_add.append(str(sym).upper())
                print(f"[{LABEL}] MAX HOLD {sym} pnl={rec.get('pnl', 0):+.4f}")
            elif should_loss_stop(pos2, upnl_net) and age_min >= LOSS_STOP_MIN_AGE_MIN:
                rec = _close_one(pos2, reason="atr_loss")
                _record_close(state, history, rec)
                closed.append(rec)
                if sym:
                    skip_add.append(str(sym).upper())
                print(f"[{LABEL}] ATR LOSS {sym} uPnL={upnl_net:+.2f}")
            elif should_stop_out(pos2, upnl_net):
                rec = _close_one(pos2, reason="atr_stop")
                _record_close(state, history, rec)
                closed.append(rec)
                if sym:
                    skip_add.append(str(sym).upper())
                print(f"[{LABEL}] ATR STOP {sym} pnl={rec.get('pnl', 0):+.4f}")
            else:
                remaining.append(pos2)
        except Exception as e:
            print(f"[{LABEL}] trail hata {sym}: {e}")
            remaining.append(pos)

    if skip_add:
        skip = {str(s).upper() for s in (state.get("atr_skip_syms") or []) if s}
        skip.update(skip_add)
        state["atr_skip_syms"] = sorted(skip)
    state["open_positions"] = remaining
    save_state(state)
    save_history(history)
    return {"ok": True, "closed": len(closed), "updated": updated, "remaining": len(remaining)}


def run_scan() -> dict:
    """Test scan ile aynı: ters sinyal kapat + boş slotu canlı fiyattan doldur."""
    if not _manage_allowed() and not _opens_allowed():
        return {"ok": False, "skipped": "disabled"}
    try:
        with state_lock():
            return _run_scan_locked()
    except StateLockBusy as e:
        print(f"[{LABEL}] scan atlandı — {e}")
        return {"ok": False, "skipped": "locked"}


def _run_scan_locked() -> dict:
    state = load_state()
    history = load_history()
    opens, ghosts = _drop_closed_ghosts(list(state.get("open_positions") or []), history)
    if ghosts:
        state["open_positions"] = opens
        save_state(state)

    kl_1h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="1h")
    kl_4h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="4h")
    cache = {
        **{f"{s}|1h": kl_1h.get(s, []) for s in TEST_SYMBOLS},
        **{f"{s}|4h": kl_4h.get(s, []) for s in TEST_SYMBOLS},
    }
    book = _book()
    reversed_syms = find_reversal_closes(
        book, opens, kl_1h, kl_4h, signal_for_book=signal_for_book,
    )
    closed = []
    remaining = []
    for pos in opens:
        sym = str(pos.get("symbol") or "").upper()
        if sym in reversed_syms:
            try:
                rec = _close_one(pos, reason="reversal")
                _record_close(state, history, rec)
                closed.append(rec)
                print(f"[{LABEL}] REVERSAL {sym} pnl={rec.get('pnl', 0):+.4f}")
            except Exception as e:
                print(f"[{LABEL}] reversal hata {sym}: {e}")
                remaining.append(pos)
        else:
            remaining.append(pos)
    state["open_positions"] = remaining
    save_state(state)
    save_history(history)

    opened = 0
    if _opens_allowed():
        r = _open_from_cands(
            load_state(),
            _build_cands(kl_1h, kl_4h),
            kl_cache=cache,
            bypass_slot_gate=True,
            blocked={str(s).upper() for s in (load_state().get("atr_skip_syms") or []) if s},
        )
        opened = int(r.get("opened") or 0)
    print(f"[{LABEL}] scan ters={len(closed)} yeni={opened}")
    return {"ok": True, "closed": len(closed), "opened": opened}


def _enrich(pos: dict, chain: dict | None, *, fee_rate: float, refresh_price: bool = True) -> dict:
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or 0)
    side = pos.get("side") or "LONG"
    mark = float((chain or {}).get("mark_price") or 0)
    if mark <= 0 and refresh_price:
        try:
            mark = _client().mark_price(pos["symbol"])
        except Exception:
            mark = 0
    if mark <= 0:
        mark = entry
    _g, upnl_net, _px = _live_upnl_net(pos, mark)
    pos_locked, _ = update_lock(dict(pos), upnl_net)
    ls = lock_summary(pos_locked)
    name = (pos.get("symbol") or "").replace("USDT", "")
    return {
        **pos_locked,
        "name": name,
        "current": round(mark, 4),
        "unrealized_pnl": upnl_net,
        "lock_armed": bool(ls.get("armed") or int(pos_locked.get("stop_level") or 0) >= 1),
        "stop_level": pos_locked.get("stop_level"),
        "stop_upnl": pos_locked.get("stop_upnl"),
    }


def status_block(*, refresh_price: bool = True) -> dict:
    cfg = load_config()
    dry = _is_dry(cfg)
    state = load_state()
    history = load_history()
    opens = list(state.get("open_positions") or [])
    ctrl = get_live_control()
    usdt = None
    chain_map = {}
    live_err = None
    c = None
    if refresh_price:
        try:
            c = _client(cfg)
            if c.configured():
                usdt = usdt_balance(c)
                for p in get_positions(c):
                    chain_map[p["symbol"]] = p
                _save_usdt_cache(usdt)
        except Exception as e:
            live_err = str(e)
            c = None
    if usdt is None:
        usdt = _load_usdt_cache()
    try:
        fee_rate = get_taker_rate(
            c if (refresh_price and c and c.configured()) else None,
            "BTCUSDT",
            cfg=cfg,
        )
    except Exception:
        fee_rate = float(cfg.get("taker_fee_rate") or 0.0005)
    cards = [
        _enrich(
            p, chain_map.get(p.get("symbol")),
            fee_rate=fee_rate, refresh_price=refresh_price and not live_err,
        )
        for p in opens
    ]
    wins = sum(1 for t in history if float(t.get("pnl") or 0) > 0)
    n = len(history)
    recent = []
    for t in list(reversed(history))[:20]:
        sym = (t.get("symbol") or "").upper()
        recent.append({
            "symbol": sym,
            "name": sym.replace("USDT", "") if sym.endswith("USDT") else sym,
            "side": t.get("side"),
            "algo": t.get("algo") or ALGO_NAME,
            "interval": t.get("interval") or "1h",
            "leverage": t.get("leverage") or LEVERAGE,
            "margin_usd": t.get("margin_usd") or MARGIN_USD,
            "entry_price": t.get("entry_price"),
            "exit_price": t.get("exit_price"),
            "pnl": round(float(t.get("pnl") or 0), 4),
            "entry_time_tr": t.get("entry_time_tr") or "",
            "exit_time_tr": t.get("exit_time_tr") or "",
            "close_reason": t.get("close_reason") or "",
        })
    return {
        "ok": True,
        "label": LABEL,
        "algo": ALGO_NAME,
        "book_uid": "a1_39",
        "margin_usd": MARGIN_USD,
        "leverage": LEVERAGE,
        "top_n": get_top_n(),
        "top_n_min": TOP_N_MIN,
        "top_n_max": TOP_N_MAX,
        "live_paused": bool(ctrl.get("live_paused")),
        "live_control": ctrl,
        "env_enabled": _env_enabled(),
        "enabled": _opens_allowed(),
        "dry_run": dry,
        "error": live_err,
        "usdt": usdt,
        "open_count": len(cards),
        "cards": cards,
        "open_positions": opens,
        "total_pnl": round(float(state.get("total_pnl") or 0), 4),
        "total_commission": round(float(state.get("total_commission") or 0), 6),
        "trade_count": n,
        "win_rate": round(100.0 * wins / n, 1) if n else None,
        "recent_trades": recent,
        "updated_at_tr": state.get("updated_at_tr") or "",
        "symbols_n": len(TEST_SYMBOLS),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="A1#39 Live Binance Futures")
    p.add_argument("cmd", choices=["open", "close", "trail", "scan", "status", "sync"])
    args = p.parse_args()
    if args.cmd == "open":
        r = run_open()
    elif args.cmd == "close":
        r = run_close()
    elif args.cmd == "trail":
        r = run_trail()
    elif args.cmd == "scan":
        r = run_scan()
    elif args.cmd == "sync":
        r = run_sync()
    else:
        r = status_block()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

"""XAUUSD sanal defter — $1000 · $200×100x · kom $0.35/taraf.

CEM01 forex_book.py'ye dokunmaz.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_DIR, ".."))
_AGUSTOS = os.path.join(_ROOT, "AgustosKripto")
for p in (_AGUSTOS, _DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from atr_profit_lock import (  # noqa: E402
    LOSS_STOP_MIN_AGE_MIN,
    atr_from_klines,
    init_lock_fields,
    should_loss_stop,
    should_stop_out,
    update_lock,
)
from exit_policy import policy_for  # noqa: E402
from fx_algo_catalog import (  # noqa: E402
    ALL_BOOKS,
    COMMISSION_SIDE,
    INIT_BAL,
    LEVERAGE,
    MARGIN,
    MAX_OPEN,
    SYMBOL,
    get_book,
)

DATA = os.path.join(_DIR, "data")
_TZ = ZoneInfo("Europe/Istanbul")
POLICY = policy_for("Test")
HIST_MAX = 800


def _now() -> datetime:
    return datetime.now(_TZ)


def now_iso() -> str:
    return _now().isoformat()


def paths(uid: str) -> tuple[str, str]:
    os.makedirs(DATA, exist_ok=True)
    return (
        os.path.join(DATA, f"fx_algo_{uid}_state.json"),
        os.path.join(DATA, f"fx_algo_{uid}_history.json"),
    )


@contextlib.contextmanager
def book_lock(uid: str):
    state_p, _ = paths(uid)
    lock_p = state_p + ".lock"
    os.makedirs(DATA, exist_ok=True)
    fh = open(lock_p, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            fh.close()


def _atomic(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _empty_state() -> dict:
    return {
        "balance": INIT_BAL,
        "init_balance": INIT_BAL,
        "total_pnl": 0.0,
        "total_commission": 0.0,
        "open_positions": [],
        "seq": 0,
        "updated_at_tr": now_iso(),
    }


def load_state(uid: str) -> dict:
    p, _ = paths(uid)
    try:
        with open(p) as f:
            st = json.load(f)
        if isinstance(st, dict) and "balance" in st:
            st.setdefault("open_positions", [])
            st.setdefault("init_balance", INIT_BAL)
            return st
    except Exception:
        pass
    return _empty_state()


def load_history(uid: str) -> list:
    _, p = paths(uid)
    try:
        with open(p) as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def save_state(uid: str, st: dict) -> None:
    st["updated_at_tr"] = now_iso()
    _atomic(paths(uid)[0], st)


def save_history(uid: str, hist: list) -> None:
    _atomic(paths(uid)[1], hist[-HIST_MAX:])


def _qty(entry: float) -> float:
    if entry <= 0:
        return 0.0
    return round(MARGIN * LEVERAGE / entry, 4)


def _pnl(side: str, entry: float, exit_px: float, qty: float) -> float:
    if side == "LONG":
        return round((exit_px - entry) * qty, 4)
    return round((entry - exit_px) * qty, 4)


def mark_for_side(side: str, bid: float | None, ask: float | None, mid: float | None) -> float | None:
    """CEM01 gibi: LONG çıkış bid, SHORT çıkış ask."""
    if (side or "").upper() in ("LONG", "BUY"):
        px = bid or mid or ask
    else:
        px = ask or mid or bid
    try:
        return float(px) if px else None
    except (TypeError, ValueError):
        return None


def _net_float(pos: dict, mark: float) -> float:
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or _qty(entry))
    gross = _pnl(pos.get("side") or "LONG", entry, mark, qty)
    comm_open = float(pos.get("commission_open") or COMMISSION_SIDE)
    return round(gross - comm_open - COMMISSION_SIDE, 4)


def _age_min(pos: dict) -> float:
    ts = pos.get("entry_time_tr")
    if not ts:
        return 0.0
    try:
        opened = datetime.fromisoformat(str(ts))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=_TZ)
        return max(0.0, (_now() - opened).total_seconds() / 60.0)
    except Exception:
        return 0.0


def _max_hold_h(pos: dict) -> float:
    if pos.get("max_hold_h") is not None:
        return float(pos["max_hold_h"])
    return float(POLICY.get("max_hold_h") or 24.0)


def _hold_expired(pos: dict) -> bool:
    return _age_min(pos) >= _max_hold_h(pos) * 60.0


def _close_one(st: dict, hist: list, pos: dict, exit_px: float, reason: str) -> dict:
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or _qty(entry))
    side = pos.get("side") or "LONG"
    comm_open = float(pos.get("commission_open") or COMMISSION_SIDE)
    comm_close = COMMISSION_SIDE
    gross = _pnl(side, entry, exit_px, qty)
    comm = round(comm_open + comm_close, 2)
    net = round(gross - comm, 4)
    st["balance"] = round(float(st["balance"]) + gross - comm_close, 2)
    st["total_pnl"] = round(float(st.get("total_pnl") or 0) + net, 4)
    st["total_commission"] = round(float(st.get("total_commission") or 0) + comm, 4)
    rec = {
        **pos,
        "exit_price": round(exit_px, 4),
        "exit_time_tr": now_iso(),
        "gross": gross,
        "commission_open": comm_open,
        "commission_close": comm_close,
        "commission": comm,
        "pnl": net,
        "win": net >= 0,
        "close_reason": reason,
        "balance_after": st["balance"],
    }
    hist.append(rec)
    return rec


def open_position(uid: str, side: str, entry: float, kl: list, *, signal: str, tf: str) -> dict | None:
    if side not in ("LONG", "SHORT") or entry <= 0:
        return None
    with book_lock(uid):
        st = load_state(uid)
        rows = list(st.get("open_positions") or [])
        if rows or len(rows) >= MAX_OPEN:
            return None
        if float(st["balance"]) < MARGIN:
            return None
        qty = _qty(entry)
        if qty <= 0:
            return None
        st["seq"] = int(st.get("seq") or 0) + 1
        st["balance"] = round(float(st["balance"]) - COMMISSION_SIDE, 2)
        pos = {
            "id": f"{uid}-{st['seq']}",
            "uid": uid,
            "symbol": SYMBOL,
            "side": side,
            "signal": signal,
            "qty": qty,
            "entry_price": round(entry, 4),
            "entry_time_tr": now_iso(),
            "interval": tf,
            "margin_usd": MARGIN,
            "leverage": LEVERAGE,
            "notional": round(qty * entry, 4),
            "commission_open": COMMISSION_SIDE,
            "max_hold_h": float(POLICY.get("max_hold_h") or 24.0),
            "loss_stop_atr": float(POLICY.get("loss_stop_atr") or 3.0),
        }
        pos = init_lock_fields(pos, atr=atr_from_klines(kl), price=entry)
        st["open_positions"] = [pos]
        save_state(uid, st)
        return pos


def close_expired(uid: str, mark: float, kl: list) -> dict:
    with book_lock(uid):
        st = load_state(uid)
        hist = load_history(uid)
        closed, remaining = [], []
        for pos in list(st.get("open_positions") or []):
            if not float(pos.get("atr_usd") or 0):
                pos = init_lock_fields(pos, atr=atr_from_klines(kl), price=float(pos.get("entry_price") or mark))
            if _hold_expired(pos):
                rec = _close_one(st, hist, pos, mark, "max_hold")
                closed.append(rec)
            else:
                remaining.append(pos)
        st["open_positions"] = remaining
        save_state(uid, st)
        save_history(uid, hist)
        return {"ok": True, "closed": len(closed), "held": len(remaining)}


def close_if_reverse(uid: str, new_side: str, mark: float, kl: list) -> dict:
    """Ters sinyal + min hold → kapat."""
    with book_lock(uid):
        st = load_state(uid)
        hist = load_history(uid)
        closed, remaining = [], []
        for pos in list(st.get("open_positions") or []):
            if not float(pos.get("atr_usd") or 0):
                pos = init_lock_fields(pos, atr=atr_from_klines(kl), price=float(pos.get("entry_price") or mark))
            age = _age_min(pos)
            opp = (pos.get("side") == "LONG" and new_side == "SHORT") or (
                pos.get("side") == "SHORT" and new_side == "LONG"
            )
            if opp and age >= 15.0:
                rec = _close_one(st, hist, pos, mark, "reverse")
                closed.append(rec)
            else:
                remaining.append(pos)
        st["open_positions"] = remaining
        save_state(uid, st)
        save_history(uid, hist)
        return {"ok": True, "closed": len(closed), "held": len(remaining)}


def trail(uid: str, mark: float, kl: list, bid: float | None = None, ask: float | None = None) -> dict:
    with book_lock(uid):
        st = load_state(uid)
        hist = load_history(uid)
        closed, remaining = [], []
        updated = 0
        for pos in list(st.get("open_positions") or []):
            px = mark_for_side(pos.get("side"), bid, ask, mark) or mark
            if not float(pos.get("atr_usd") or 0):
                pos = init_lock_fields(pos, atr=atr_from_klines(kl), price=float(pos.get("entry_price") or px))
            net = _net_float(pos, px)
            pos2, ch = update_lock(pos, net)
            if ch:
                updated += 1
            age = _age_min(pos2)
            if _hold_expired(pos2):
                closed.append(_close_one(st, hist, pos2, px, "max_hold"))
            elif should_loss_stop(pos2, net) and age >= LOSS_STOP_MIN_AGE_MIN:
                closed.append(_close_one(st, hist, pos2, px, "atr_loss"))
            elif should_stop_out(pos2, net):
                closed.append(_close_one(st, hist, pos2, px, "atr_stop"))
            else:
                remaining.append(pos2)
        st["open_positions"] = remaining
        save_state(uid, st)
        save_history(uid, hist)
        return {"ok": True, "closed": len(closed), "updated": updated, "held": len(remaining)}


def snapshot(
    uid: str,
    mark: float | None = None,
    *,
    bid: float | None = None,
    ask: float | None = None,
    include_history: bool = True,
) -> dict:
    book = get_book(uid) or {"uid": uid, "name": uid, "title": uid}
    st = load_state(uid)
    hist = load_history(uid)
    rows = []
    float_sum = 0.0
    for pos in st.get("open_positions") or []:
        item = dict(pos)
        px = mark_for_side(pos.get("side"), bid, ask, mark)
        if px is not None:
            item["mark"] = round(px, 4)
            item["float_net"] = _net_float(pos, px)
            float_sum += item["float_net"] or 0
        rows.append(item)
    wins = sum(1 for t in hist if t.get("win") or float(t.get("pnl") or 0) > 0)
    n = len(hist)
    bal = float(st.get("balance") or INIT_BAL)
    init = float(st.get("init_balance") or INIT_BAL)
    pnl = round(bal - init, 2)
    return {
        "ok": True,
        "id": uid,
        "name": book.get("name") or uid,
        "title": book.get("title") or "",
        "symbol": SYMBOL,
        "balance": round(bal, 2),
        "init_balance": init,
        "total_pnl": pnl,
        "unrealized_pnl": round(float_sum, 2) if rows else 0.0,
        "equity": round(bal + float_sum, 2),
        "open_count": len(rows),
        "positions": rows,
        "cards": [
            {
                "name": SYMBOL,
                "side": p.get("side"),
                "entry": p.get("entry_price"),
                "mark": p.get("mark"),
                "float_net": p.get("float_net"),
                "entry_time_tr": p.get("entry_time_tr"),
            }
            for p in rows
        ],
        "history": list(reversed(hist[-100:])) if include_history else [],
        "history_n": n,
        "wins": wins,
        "wr": round(100.0 * wins / n, 1) if n else None,
        "margin": MARGIN,
        "leverage": LEVERAGE,
        "updated_at_tr": st.get("updated_at_tr"),
    }


def snapshot_all(
    mark: float | None = None,
    *,
    bid: float | None = None,
    ask: float | None = None,
    include_history: bool = False,
) -> dict:
    books = [
        snapshot(b["uid"], mark, bid=bid, ask=ask, include_history=include_history)
        for b in ALL_BOOKS
    ]
    books.sort(key=lambda b: (
        float(b.get("balance") or 0),
        float(b.get("total_pnl") or 0),
        float(b.get("wr") or -1),
    ), reverse=True)
    return {
        "ok": True,
        "symbol": SYMBOL,
        "mark": mark,
        "bid": bid,
        "ask": ask,
        "init_balance": INIT_BAL,
        "count": len(books),
        "total_balance": round(sum(float(b.get("balance") or 0) for b in books), 2),
        "total_pnl": round(sum(float(b.get("total_pnl") or 0) for b in books), 2),
        "total_unrealized": round(sum(float(b.get("unrealized_pnl") or 0) for b in books), 2),
        "total_open": sum(int(b.get("open_count") or 0) for b in books),
        "total_trades": sum(int(b.get("history_n") or 0) for b in books),
        "books": books,
    }

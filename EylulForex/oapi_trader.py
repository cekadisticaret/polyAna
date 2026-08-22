"""OPEN API — CEM01 (Grafik) kararının cTrader DEMO aynası.

Sinyal / plan / kapanış Grafik `forex_book` g1. Bu dosya yalnız
cTrader'a aynı tarafı açar/kapatır. Canlı hesaba yol yok.
"""
from __future__ import annotations

import fcntl
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ctrader_api import (
    close_position,
    orders_allowed,
    place_market,
    snapshot_book,
)

_DIR = Path(__file__).resolve().parent / "data"
_STATE = _DIR / "oapi_live_state.json"
_LOCK = _DIR / "oapi_live.lock"
_TZ = ZoneInfo("Europe/Istanbul")
VOLUME = 0.10


def _now() -> str:
    return datetime.now(_TZ).strftime("%Y.%m.%d %H:%M:%S")


def _empty() -> dict:
    return {
        "last_reject": None,
        "last_order": None,
        "seq": 0,
        "mirror_src": "g1",
    }


def _load() -> dict:
    try:
        st = json.loads(_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        st = {}
    base = _empty()
    for k, v in base.items():
        st.setdefault(k, v)
    return st


def _save(st: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    tmp = _STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_STATE)


def _side(pos: dict | None) -> str:
    return str((pos or {}).get("side") or "")


def _g1_book() -> dict:
    from forex_book import snapshot
    from forex_data import forex_quote
    q = forex_quote()
    return snapshot(q.get("bid"), q.get("ask"), book="g1")


def tick() -> dict:
    if not orders_allowed():
        return {"ok": False, "trade": False, "reason": "need_trading_scope"}

    g1 = _g1_book()
    want = [_side(p) for p in (g1.get("positions") or []) if _side(p) in ("buy", "sell")]
    want_pos = { _side(p): p for p in (g1.get("positions") or []) if _side(p) in ("buy", "sell") }

    book = snapshot_book()
    live = list(book.get("positions") or [])
    live_by = {}
    for p in live:
        s = _side(p)
        if s:
            live_by.setdefault(s, []).append(p)

    _DIR.mkdir(parents=True, exist_ok=True)
    with open(_LOCK, "a+", encoding="utf-8") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        st = _load()
        closed = []
        opened = []

        for side, rows in list(live_by.items()):
            if side in want_pos:
                continue
            for pos in rows:
                try:
                    close_position(
                        pos.get("id"),
                        volume_raw=pos.get("volume_raw"),
                        lots=pos.get("volume") or VOLUME,
                    )
                    closed.append({"id": pos.get("id"), "side": side, "reason": "g1_flat"})
                except Exception as e:
                    st["last_reject"] = {
                        "side": side,
                        "reason": f"close {type(e).__name__}: {str(e)[:120]}",
                        "at": _now(),
                    }
                    _save(st)
                    return {
                        "ok": False,
                        "trade": True,
                        "error": f"close {type(e).__name__}: {e}"[:200],
                        "balance": book.get("balance"),
                    }

        if closed:
            book = snapshot_book()
            live = list(book.get("positions") or [])
            live_by = {}
            for p in live:
                s = _side(p)
                if s:
                    live_by.setdefault(s, []).append(p)

        for side, src in want_pos.items():
            if live_by.get(side):
                continue
            try:
                out = place_market(
                    side,
                    lots=VOLUME,
                    stop=src.get("stop"),
                    target=src.get("target"),
                    comment="oapi=g1",
                )
                opened.append(out)
                st["seq"] = int(st.get("seq") or 0) + 1
                st["last_order"] = {
                    "side": side,
                    "at": _now(),
                    "position_id": (out or {}).get("position_id"),
                    "price": (out or {}).get("price"),
                    "src_id": src.get("id"),
                }
                st["last_reject"] = None
            except Exception as e:
                st["last_reject"] = {
                    "side": side,
                    "reason": f"emir {type(e).__name__}: {str(e)[:120]}",
                    "at": _now(),
                }
                _save(st)
                return {
                    "ok": False,
                    "trade": True,
                    "error": str(e)[:200],
                    "balance": book.get("balance"),
                }
        _save(st)

    return {
        "ok": True,
        "trade": True,
        "demo": True,
        "mirror": "g1",
        "want": want,
        "opened": opened,
        "closed": closed,
        "reject": (st.get("last_reject") or {}).get("reason"),
        "open_count": len(live) + len(opened) - len(closed),
        "balance": book.get("balance"),
        "equity": book.get("equity"),
    }

"""BIN_XAUUSDT sinyal — Algoritma işlemler kartından seçilen motor.

Varsayılan `a2_09`. `fx_algo_signals.signal_for_book` yalnız okunur.
GPSUSDT / CEM01 / fx_algo defterlerine yazmaz.
"""
from __future__ import annotations

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from fx_algo_catalog import get_book  # noqa: E402
from fx_algo_signals import signal_for_book  # noqa: E402

DEFAULT_UID = "a2_09"


def _control() -> dict:
    try:
        from bin_b103_binance import load_control
        c = load_control()
        return c if isinstance(c, dict) else {}
    except Exception:
        return {}


def current_uid() -> str:
    uid = str(_control().get("engine_uid") or DEFAULT_UID).strip().lower()
    return uid if get_book(uid) else DEFAULT_UID


def current_book() -> dict:
    return get_book(current_uid()) or get_book(DEFAULT_UID) or {
        "uid": DEFAULT_UID, "name": "A2#09", "title": "A2#09 Squeeze Momentum",
    }


def engine_info() -> dict:
    b = current_book()
    return {
        "uid": b.get("uid") or DEFAULT_UID,
        "name": b.get("name") or b.get("uid"),
        "title": b.get("title") or b.get("name") or "",
    }


def set_engine_uid(uid: str) -> dict:
    book = get_book((uid or "").strip().lower())
    if not book:
        return {"ok": False, "error": "unknown_book"}
    from bin_b103_binance import load_control, save_control
    c = load_control()
    prev = str(c.get("engine_uid") or DEFAULT_UID)
    c["engine_uid"] = book["uid"]
    save_control(c)
    return {
        "ok": True,
        "uid": book["uid"],
        "name": book.get("name"),
        "title": book.get("title"),
        "prev": prev,
        "changed": prev != book["uid"],
    }


def pick_tf(sig1: str, sig4: str) -> tuple[str, str]:
    if sig1 in ("UP", "DOWN"):
        return "1h", sig1
    if sig4 in ("UP", "DOWN"):
        return "4h", sig4
    return "1h", "NEUTRAL"


def resolve(kl1: list, kl4: list) -> dict:
    book = current_book()
    s1 = signal_for_book(book, kl1)
    s4 = signal_for_book(book, kl4)
    tf, sig = pick_tf(s1, s4)
    return {
        "direction": sig,
        "tf": tf,
        "sig_1h": s1,
        "sig_4h": s4,
        "engine": book.get("uid"),
        "name": book.get("name"),
        "title": book.get("title"),
        "is_stable": sig in ("UP", "DOWN"),
        "confidence": 1.0 if sig in ("UP", "DOWN") else 0.0,
    }


def side_of(sig: str) -> str | None:
    if sig == "UP":
        return "buy"
    if sig == "DOWN":
        return "sell"
    return None

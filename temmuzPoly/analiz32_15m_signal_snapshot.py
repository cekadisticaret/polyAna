"""110'un hesapladığı 15m sinyali 111/210 ile paylaşır (aynı kline/skor)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import fields
from typing import TYPE_CHECKING, Optional

_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_FILE = os.path.join(_DIR, "poly_trader_5m_110_signal_snapshot.json")

if TYPE_CHECKING:
    from analiz32_15m_adapter import Signal15m


def _read_payload() -> dict:
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    try:
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_payload(payload: dict) -> None:
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _signal_to_dict(sig: "Signal15m") -> dict:
    d = {f.name: getattr(sig, f.name) for f in fields(sig)}
    d["opened"] = None
    d["open_skip_reason"] = ""
    return d


def _signal_from_dict(data: dict, cls) -> "Signal15m":
    names = {f.name for f in fields(cls)}
    return cls(**{k: data[k] for k in names if k in data})


def _empty_signal(symbol: str, skip_reason: str) -> "Signal15m":
    from analiz32_15m_adapter import Signal15m

    return Signal15m(
        symbol=symbol,
        direction=None,
        entry_price=0.0,
        confidence=0.0,
        up_score=0,
        down_score=0,
        factors=[],
        htf_bias="",
        skip_reason=skip_reason,
    )


def save_snapshot(ts_period: int, symbol: str, sig: "Signal15m") -> None:
    payload: dict = {"ts_period": ts_period, "saved_at": time.time(), "symbols": {}}
    existing = _read_payload()
    if existing.get("ts_period") == ts_period:
        payload = existing
    payload["ts_period"] = ts_period
    payload.setdefault("symbols", {})[symbol] = _signal_to_dict(sig)
    payload["saved_at"] = time.time()
    _write_payload(payload)


def set_snapshot_opened(
    ts_period: int,
    symbol: str,
    opened: bool,
    *,
    reason: str = "",
) -> None:
    """110 işlem kararı — 210 yalnızca opened=True iken açar."""
    payload = _read_payload()
    if payload.get("ts_period") != ts_period:
        payload = {"ts_period": ts_period, "saved_at": time.time(), "symbols": {}}
    sym_data = payload.setdefault("symbols", {}).setdefault(symbol, {})
    sym_data["opened"] = opened
    sym_data["open_skip_reason"] = reason
    payload["saved_at"] = time.time()
    _write_payload(payload)


def load_snapshot(ts_period: int, symbol: str) -> Optional["Signal15m"]:
    payload = _read_payload()
    if payload.get("ts_period") != ts_period:
        return None
    raw = payload.get("symbols", {}).get(symbol)
    if not raw:
        return None
    from analiz32_15m_adapter import Signal15m

    return _signal_from_dict(raw, Signal15m)


def analyze_15m_from_110(symbol: str, ts_period: int) -> Optional["Signal15m"]:
    """210: 110'un kaydettiği sinyali aynen kullanır (ek filtre yok)."""
    base = load_snapshot(ts_period, symbol)
    if base is None:
        return _empty_signal(symbol, "110 snapshot yok (110 henüz çalışmadı)")
    return base


def wait_for_110_snapshot(
    symbol: str,
    ts_period: int,
    timeout: float = 20.0,
    poll: float = 0.5,
) -> "Signal15m":
    """110 snapshot gelene kadar bekle (sinyal; opened kararı gerekmez)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        base = load_snapshot(ts_period, symbol)
        if base is not None:
            return base
        time.sleep(poll)
    return _empty_signal(symbol, "110 snapshot yok (timeout)")


def wait_for_110_open_decision(
    symbol: str,
    ts_period: int,
    timeout: float = 20.0,
    poll: float = 0.5,
) -> tuple["Signal15m", bool, str]:
    """210: 110'un açılış kararı (opened true/false) finalize olana kadar bekle."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = _read_payload()
        if payload.get("ts_period") != ts_period:
            time.sleep(poll)
            continue
        raw = payload.get("symbols", {}).get(symbol)
        if raw and raw.get("opened") is not None:
            from analiz32_15m_adapter import Signal15m

            sig = _signal_from_dict(raw, Signal15m)
            opened = bool(raw["opened"])
            reason = raw.get("open_skip_reason") or ""
            return sig, opened, reason
        time.sleep(poll)
    return _empty_signal(symbol, "110 açılış kararı timeout"), False, "110 açılış kararı timeout"

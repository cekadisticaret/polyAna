"""110'un hesapladığı 15m sinyali 111 ile paylaşır (aynı kline/skor)."""
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


def _signal_to_dict(sig: "Signal15m") -> dict:
    return {f.name: getattr(sig, f.name) for f in fields(sig)}


def _signal_from_dict(data: dict, cls) -> "Signal15m":
    names = {f.name for f in fields(cls)}
    return cls(**{k: data[k] for k in names if k in data})


def save_snapshot(ts_period: int, symbol: str, sig: "Signal15m") -> None:
    payload: dict = {"ts_period": ts_period, "saved_at": time.time(), "symbols": {}}
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE) as f:
                payload = json.load(f)
        except Exception:
            pass
    if payload.get("ts_period") != ts_period:
        payload = {"ts_period": ts_period, "saved_at": time.time(), "symbols": {}}
    payload["symbols"][symbol] = _signal_to_dict(sig)
    payload["saved_at"] = time.time()
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_snapshot(ts_period: int, symbol: str) -> Optional["Signal15m"]:
    if not os.path.exists(SNAPSHOT_FILE):
        return None
    try:
        with open(SNAPSHOT_FILE) as f:
            payload = json.load(f)
    except Exception:
        return None
    if payload.get("ts_period") != ts_period:
        return None
    raw = payload.get("symbols", {}).get(symbol)
    if not raw:
        return None
    from analiz32_15m_adapter import Signal15m

    return _signal_from_dict(raw, Signal15m)

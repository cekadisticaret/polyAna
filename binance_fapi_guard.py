"""Binance Futures (fapi) IP ban — ortak devre kesici.

418 / -1003 gelince `until` yazılır; süre dolana kadar fapi'ye yeni istek yok.
Public veri spot/data-api'ye düşer; canlı emir ban bitene kadar bekler.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_FILE = Path("/tmp/binance_fapi_ban.json")
_RE = re.compile(r"banned until (\d+)", re.I)


def ban_until() -> float:
    try:
        d = json.loads(_FILE.read_text())
        return float(d.get("until") or 0)
    except Exception:
        return 0.0


def fapi_blocked() -> bool:
    return time.time() < ban_until()


def ban_msg() -> str:
    left = max(0, int(ban_until() - time.time()))
    if left <= 0:
        return "Binance fapi ban bitti"
    m, s = divmod(left, 60)
    return f"Binance fapi IP ban · {m}dk {s}sn kaldı"


def note_418(text: str = "", extra_sec: float = 90.0) -> float:
    until = 0.0
    m = _RE.search(str(text or ""))
    if m:
        raw = int(m.group(1))
        until = raw / 1000.0 if raw > 10_000_000_000 else float(raw)
    if until <= time.time():
        until = time.time() + extra_sec
    try:
        _FILE.write_text(json.dumps({
            "until": until,
            "at": time.time(),
            "note": str(text)[:240],
        }))
    except OSError:
        pass
    return until

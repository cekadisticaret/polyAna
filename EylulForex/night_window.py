"""Gece sessiz penceresi — şu an kapalı.

GPSUSDT ve BIN_XAUUSDT yeni açılışı 22:00–08:00 kesmez.
Ayar `EylulForex/data/night_window.json`.
"""
from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Istanbul")
_CFG = Path(__file__).resolve().parent / "data" / "night_window.json"

_DEFAULT: dict = {
    "enabled": False,
    "start": "22:00",
    "end": "08:00",
    "books": [],
}


def _load() -> dict:
    cfg = dict(_DEFAULT)
    if not _CFG.exists():
        return cfg
    try:
        data = json.loads(_CFG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return cfg
    if isinstance(data, dict):
        cfg.update(data)
    return cfg


def _hhmm(raw, fallback: time) -> time:
    try:
        parts = str(raw).split(":")
        return time(int(parts[0]) % 24, int(parts[1]) % 60)
    except (AttributeError, IndexError, TypeError, ValueError):
        return fallback


def is_quiet(book: str, now: datetime | None = None) -> bool:
    cfg = _load()
    if not cfg.get("enabled"):
        return False
    books = cfg.get("books")
    if isinstance(books, list) and book not in books:
        return False
    start = _hhmm(cfg.get("start"), time(22, 0))
    end = _hhmm(cfg.get("end"), time(8, 0))
    if start == end:
        return False
    cur = (now or datetime.now(_TZ)).time()
    if start < end:
        return start <= cur < end
    # pencere gece yarısını geçiyor (22:00 → 08:00)
    return cur >= start or cur < end


def label() -> str:
    cfg = _load()
    return f"{cfg.get('start', '22:00')}–{cfg.get('end', '08:00')}"

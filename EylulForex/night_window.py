"""Gece sessiz penceresi — canlı Binance defterlerinde yeni açılışı durdurur.

Yalnız `open` yolunu keser. close / trail / ATR stopu / reverse kapanışı
çalışmaya devam eder — açık pozisyon gece boyunca korumasız kalmaz.

Ayar `EylulForex/data/night_window.json`; kod değişikliği gerekmez.
"""
from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Istanbul")
_CFG = Path(__file__).resolve().parent / "data" / "night_window.json"

_DEFAULT: dict = {
    "enabled": True,
    "start": "22:00",
    "end": "08:00",
    "books": ["gps", "binb103"],
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

"""F1#01 HMM rejim — REF05 onay filtresi.

Kaynak: /tmp/f1_signals.json (cron f1_signal.py :01 + :04:40).
Dosya yoksa veya NEUTRAL ise None döner (nötr = engel yok).
"""
from __future__ import annotations

import json
import os

_F1_SIGNALS = "/tmp/f1_signals.json"
_F1_NUM = "1"


def resolve_direction(symbol: str) -> str | None:
    """Sembol yönü: 'UP', 'DOWN' veya None (nötr / okunamadı)."""
    short = (symbol or "").replace("USDT", "").upper()
    if not short:
        return None
    if not os.path.exists(_F1_SIGNALS):
        return None
    try:
        with open(_F1_SIGNALS, encoding="utf-8") as f:
            data = json.load(f)
        row = (data.get("signals") or {}).get(_F1_NUM) or {}
        d = str(row.get(short) or row.get(short.lower()) or "").upper()
        if d in ("UP", "DOWN"):
            return d
        return None
    except Exception:
        return None

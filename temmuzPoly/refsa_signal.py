"""REFSA — saatlik yol UÇ NOKTA DÖNÜŞÜ (SAF / filtresiz).

REF04 ile aynı parametreler, hiçbir onay filtresi yok.
Amaç: F16 / A2#05 gibi filtrelerin gerçek katkısını ölçmek.
REF04 dosyasına dokunulmaz — mantık ref04_signal'den import edilir.
"""
from __future__ import annotations

from ref04_signal import (  # noqa: F401
    ASK_MAX,
    ASK_MIN,
    ENTRY_AFTER,
    ENTRY_BEFORE,
    EXCLUDED_SYMBOLS,
    EXTREME_BPS,
    PULLBACK_BPS,
    SYMBOLS,
    decide,
)

"""REF05 — saatlik yol UÇ NOKTA DÖNÜŞÜ (REF04 ile aynı yol mantığı).

F1#01 filtresi trader'da uygulanır (bu modül yalnız yol verisine bakar).
REF04 dosyasına dokunulmaz — mantık ref04_signal'den import edilir.
"""
from __future__ import annotations

from ref04_signal import (  # noqa: F401
    ASK_MAX,
    ASK_MIN,
    ENTRY_AFTER,
    ENTRY_BEFORE,
    EXTREME_BPS,
    PULLBACK_BPS,
    SYMBOLS,
    decide,
)

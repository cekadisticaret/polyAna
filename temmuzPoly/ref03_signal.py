"""REF03 — REF01 yol mantığı (trend + fade), yalnız ask ≤ 0.55.

REF01 koduna tek satır dokunulmaz; `decide` sarmalanır ve
`ask_max` alanı 0.55 olarak ezilir. Trader'da bu eşik filtre olarak kullanılır.

Kaynak: `ref01_signal.path_series` (hourly_path). Emir yok.
"""
from __future__ import annotations

import ref01_signal as _r1

SYMBOLS = _r1.SYMBOLS
ASK_MAX = 0.55  # REF01'den tek fark


def decide(symbol: str, minute: int | None = None, hour_key: str | None = None) -> dict:
    """REF01 decide() → ask_max 0.55 olarak ezilir."""
    d = _r1.decide(symbol, minute, hour_key)
    d["ask_max"] = ASK_MAX
    return d

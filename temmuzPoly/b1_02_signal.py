"""B1#02 — sabit sembol→motor: BTC→A15, ETH→A6, SOL→A2#01."""
from __future__ import annotations

from b1_01_signal import SYMBOLS, resolve_from_book

# Ekran / best-by-symbol kartı ile aynı sabit eşleme
_FIXED_MAPPING: dict[str, tuple[str, str]] = {
    "BTC": ("analiz15", "A15"),
    "ETH": ("analiz6", "A6"),
    "SOL": ("a2_01", "A2#01"),
}


def load_mapping() -> dict[str, dict]:
    return {
        sym: {"book": book, "label": label, "wr": None, "w": 0, "t": 0}
        for sym, (book, label) in _FIXED_MAPPING.items()
    }


def engine_label(symbol: str) -> str:
    sym = symbol.replace("USDT", "")
    row = _FIXED_MAPPING.get(sym)
    if row:
        return f"B1←{row[1]}"
    return "B1#02"


async def resolve_live_signal(symbol: str) -> tuple[str | None, float | None, str]:
    sym = symbol.replace("USDT", "")
    book, label = _FIXED_MAPPING.get(sym, ("analiz6", "A6"))
    sig, price, algo_name = await resolve_from_book(book, symbol)
    return sig, price, f"B1←{label} · {algo_name}"

"""COMBO2 — kart eşlemesi: BTC→C1#01 · ETH/SOL→COMBO.

Kaynak defterin o saatteki açık pozisyonunu kopyalar. Sinyal üretmez.
C101 :02, COMBO :02:25 açar; COMBO2 :02:40'ta okur.
"""
from __future__ import annotations

from pathlib import Path

from e01_signal import _dir_of, _load_state, norm_symbol

_DIR = Path(__file__).resolve().parent

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
# coin → (defter, etiket, state)
MAP = {
    "BTCUSDT": ("c101", "C1#01", _DIR / "poly_trader_c101_state.json"),
    "ETHUSDT": ("combo", "COMBO", _DIR / "poly_trader_combo_state.json"),
    "SOLUSDT": ("combo", "COMBO", _DIR / "poly_trader_combo_state.json"),
}


def decide(symbol: str, hour_tr: int) -> dict:
    sym = norm_symbol(symbol)
    spec = MAP.get(sym)
    if not spec:
        return {
            "allow": False, "symbol": sym, "direction": None,
            "votes": 0, "reason": "sembol_yok", "detail": sym,
            "source": None, "source_label": None,
        }
    key, lab, path = spec
    direction = None
    st = _load_state(path)
    for pos in st.get("open_positions") or []:
        if int(pos.get("entry_hour_tr") or -1) != int(hour_tr):
            continue
        if norm_symbol(pos.get("symbol") or "") != sym:
            continue
        direction = _dir_of(pos)
        if direction:
            break
    if not direction:
        return {
            "allow": False, "symbol": sym, "direction": None,
            "votes": 0, "reason": "kaynak_sessiz",
            "detail": f"{lab}=sessiz",
            "source": key, "source_label": lab,
        }
    return {
        "allow": True, "symbol": sym, "direction": direction,
        "votes": 1, "reason": "ayna",
        "detail": f"{lab}={direction}",
        "source": key, "source_label": lab,
    }

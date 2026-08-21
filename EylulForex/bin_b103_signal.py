"""BIN_B1#03 sinyal — `/forex/algoritma-islemler/a2_09` ile aynı.

A2#09 Squeeze Momentum (BB+KC) · `fx_algo_signals._a2(9)` + 1h/4h seçimi.
Eski motor / GPSUSDT / CEM01 dokunulmaz.
"""
from __future__ import annotations

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from fx_algo_signals import _a2  # noqa: E402

ENGINE = "a2_09"
ENGINE_LABEL = "A2#09 Squeeze Momentum (BB+KC)"
A2_NUM = 9


def pick_tf(sig1: str, sig4: str) -> tuple[str, str]:
    if sig1 in ("UP", "DOWN"):
        return "1h", sig1
    if sig4 in ("UP", "DOWN"):
        return "4h", sig4
    return "1h", "NEUTRAL"


def resolve(kl1: list, kl4: list) -> dict:
    s1 = _a2(A2_NUM, kl1)
    s4 = _a2(A2_NUM, kl4)
    tf, sig = pick_tf(s1, s4)
    return {
        "direction": sig,
        "tf": tf,
        "sig_1h": s1,
        "sig_4h": s4,
        "engine": ENGINE,
        "name": ENGINE_LABEL,
        "is_stable": sig in ("UP", "DOWN"),
        "confidence": 1.0 if sig in ("UP", "DOWN") else 0.0,
    }


def side_of(sig: str) -> str | None:
    if sig == "UP":
        return "buy"
    if sig == "DOWN":
        return "sell"
    return None

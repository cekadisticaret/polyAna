"""
KALEM — 5M 102 deneysel filtreler (çıkarmak için bu dosyayı sil + 102'deki KALEM blokları).

1. Fitil: son N mumda alt fitil uçları (low) ardışık düşüyorsa UP yok;
           üst fitil uçları (high) ardışık yükseliyorsa DOWN yok.
2. Dinlenme: arka arkaya 3 UP veya 3 DOWN açıldıysa 4. işlem aynı yönde açılmaz.

Kapat: PM_5M_102_KALEM=false
"""

from __future__ import annotations

import os

KALEM_ENABLED = os.getenv("PM_5M_102_KALEM", "true").lower() in ("1", "true", "yes")
KALEM_WICK_BARS = int(os.getenv("PM_5M_102_KALEM_WICK_BARS", "5"))
KALEM_WICK_CONSEC = int(os.getenv("PM_5M_102_KALEM_WICK_CONSEC", "3"))
KALEM_WICK_MIN_PCT = float(os.getenv("PM_5M_102_KALEM_WICK_MIN_PCT", "0.03"))
KALEM_STREAK_MAX = int(os.getenv("PM_5M_102_KALEM_STREAK", "3"))


def _closed_bars(klines: list[dict], n: int) -> list[dict]:
    """Son n kapanmış mum (açık mum hariç)."""
    if len(klines) < n + 1:
        return []
    return klines[-(n + 1):-1]


def _has_consecutive_lower_lows(lows: list[float], consec: int) -> bool:
    if len(lows) < consec:
        return False
    for i in range(len(lows) - consec + 1):
        window = lows[i:i + consec]
        if all(window[j] > window[j + 1] for j in range(consec - 1)):
            return True
    return False


def _has_consecutive_higher_highs(highs: list[float], consec: int) -> bool:
    if len(highs) < consec:
        return False
    for i in range(len(highs) - consec + 1):
        window = highs[i:i + consec]
        if all(window[j] < window[j + 1] for j in range(consec - 1)):
            return True
    return False


def _meaningful_wick(k: dict, side: str) -> bool:
    """Fitil en az KALEM_WICK_MIN_PCT ise say."""
    body_lo = min(k["open"], k["close"])
    body_hi = max(k["open"], k["close"])
    ref = k["close"] or k["open"] or 1.0
    if side == "lower":
        wick = body_lo - k["low"]
    else:
        wick = k["high"] - body_hi
    return wick / ref * 100 >= KALEM_WICK_MIN_PCT


def kalem_wick_skip(direction: str | None, klines: list[dict]) -> str | None:
    if not KALEM_ENABLED or not direction:
        return None

    bars = _closed_bars(klines, KALEM_WICK_BARS)
    if len(bars) < KALEM_WICK_CONSEC:
        return None

    if direction == "UP":
        lows = [k["low"] for k in bars if _meaningful_wick(k, "lower")]
        if len(lows) >= KALEM_WICK_CONSEC and _has_consecutive_lower_lows(lows, KALEM_WICK_CONSEC):
            tail = " → ".join(f"{x:,.0f}" for x in lows[-KALEM_WICK_CONSEC:])
            return (
                f"KALEM fitil: son {KALEM_WICK_BARS} mumda alt fitil uçları düşüyor ({tail}), UP yok"
            )

    if direction == "DOWN":
        highs = [k["high"] for k in bars if _meaningful_wick(k, "upper")]
        if len(highs) >= KALEM_WICK_CONSEC and _has_consecutive_higher_highs(highs, KALEM_WICK_CONSEC):
            tail = " → ".join(f"{x:,.0f}" for x in highs[-KALEM_WICK_CONSEC:])
            return (
                f"KALEM fitil: son {KALEM_WICK_BARS} mumda üst fitil uçları yükseliyor ({tail}), DOWN yok"
            )

    return None


def kalem_streak_skip(direction: str | None, history: list[dict]) -> str | None:
    if not KALEM_ENABLED or not direction:
        return None

    dirs = [t["predicted_dir"] for t in history if t.get("predicted_dir") in ("UP", "DOWN")]
    if len(dirs) < KALEM_STREAK_MAX:
        return None

    last = dirs[-KALEM_STREAK_MAX:]
    if all(d == direction for d in last):
        tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
        return (
            f"KALEM dinlenme: arka arkaya {KALEM_STREAK_MAX} {tr} ({direction}), "
            f"{KALEM_STREAK_MAX + 1}. işlem yok"
        )
    return None

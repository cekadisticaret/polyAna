"""REF02 — REF01 yol verisi, yalnız TREND (fade yok).

TREND: ilk |6| bps yönü, ref kesişi yok, şu an aynı yönde ≥18 bps.
Kesiş varsa işlem açılmaz — fade dalı kullanılmaz.

Kaynak: `ref01_signal.path_series` (hourly_path). REF01 dosyasına dokunulmaz.
"""
from __future__ import annotations

from ref01_signal import (
    ASK_MAX,
    FIRST_BPS,
    TREND_BPS,
    _deny,
    _first_side,
    _cross_min,
    norm_symbol,
    path_series,
)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def decide(symbol: str, minute: int | None = None, hour_key: str | None = None) -> dict:
    sym = norm_symbol(symbol)
    if minute is not None and (minute < 1 or minute > 50):
        return _deny(sym, "dakika", f"dk {minute} giriş dışı")
    path = path_series(sym, hour_key)
    bps = path.get("bps")
    pts = path.get("pts") or []
    first = _first_side(pts, FIRST_BPS)
    if not first:
        return _deny(sym, "yol düz", f"ilk {FIRST_BPS:.0f} bps yok · şimdi {bps}")
    first_m, _first_b, first_side = first
    cross = _cross_min(pts, first_m, first_side)
    extra = {"path_bps": bps, "first_side": first_side, "cross_min": cross}

    if bps is None:
        return _deny(sym, "yol yok", "bps yok", **extra)

    if cross is not None:
        return _deny(
            sym, "kesiş",
            f"fade kapalı · kesiş :{cross:02d} · trend yok",
            **extra,
        )

    now_side = "UP" if bps > 0 else ("DOWN" if bps < 0 else None)
    if now_side == first_side and abs(bps) >= TREND_BPS:
        return {
            "allow": True,
            "symbol": sym,
            "direction": first_side,
            "mode": "trend",
            "ask_max": ASK_MAX,
            "path_bps": bps,
            "first_side": first_side,
            "cross_min": None,
            "reason": "trend",
            "detail": f"trend {first_side} {bps:+.1f}bps kesişsiz",
        }
    return _deny(
        sym, "trend bekliyor",
        f"{first_side} · şimdi {bps:+.1f}bps · {TREND_BPS:.0f} yok",
        **extra,
    )

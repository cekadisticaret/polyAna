"""15M 114 — 110 tabanlı + 1h ALFA/A8 hizası, gece filtresi, kayıp serisi mola."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Callable, Optional

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if os.path.join(_ROOT, "jesse") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "jesse"))

from analiz32_15m_adapter import Signal15m, analyze_15m

_PERIOD_SECS = 900

LOSS_STREAK_LIMIT = 3
COOLDOWN_SLOTS = 4
NIGHT_OPEN_START = 9   # 09:00 dahil
NIGHT_OPEN_END = 23    # 23:00 hariç


def _hourly_a8_dir(symbol: str) -> str | None:
    try:
        from analiz8_signal import predict_pm_direction
        sig = predict_pm_direction(symbol)
        if sig and sig.predicted_dir in ("UP", "DOWN"):
            return sig.predicted_dir
    except Exception as exc:
        print(f"[114] 1h A8 hata {symbol}: {exc}")
    return None


def _hourly_alfa_dir(symbol: str) -> str | None:
    try:
        from chart_hourly_signals import compute_hourly_chart_signals
        from alfa_signal import chart_current_from_hourly
        hs = compute_hourly_chart_signals(symbol, lookback_bars=2)
        if not hs.get("ok"):
            return None
        alfa = chart_current_from_hourly(hs.get("current") or {}, symbol)
        d = alfa.get("dir")
        return d if d in ("UP", "DOWN") else None
    except Exception as exc:
        print(f"[114] 1h ALFA hata {symbol}: {exc}")
    return None


def _check_hourly_alignment(symbol: str, direction: str) -> str | None:
    refs: list[tuple[str, str]] = []
    a8 = _hourly_a8_dir(symbol)
    if a8:
        refs.append(("A8", a8))
    alfa = _hourly_alfa_dir(symbol)
    if alfa:
        refs.append(("ALFA", alfa))
    if not refs:
        return "1h A8/ALFA sinyal yok"
    for name, ref_dir in refs:
        if ref_dir != direction:
            return f"1h {name} ters ({ref_dir})"
    return None


def analyze_114_15m(symbol: str = "SOLUSDT") -> Optional[Signal15m]:
    """110 15m sinyali + 1h ALFA/A8 ile aynı yön şart."""
    sig = analyze_15m(symbol=symbol)
    if sig is None:
        return None
    if sig.direction is None:
        return sig

    misalign = _check_hourly_alignment(symbol, sig.direction)
    if misalign:
        factors = list(sig.factors or [])
        factors.append("15M 114")
        return Signal15m(
            symbol=symbol,
            direction=None,
            entry_price=sig.entry_price,
            confidence=sig.confidence,
            up_score=sig.up_score,
            down_score=sig.down_score,
            factors=factors,
            htf_bias=sig.htf_bias,
            skip_reason=misalign,
        )

    return Signal15m(
        symbol=symbol,
        direction=sig.direction,
        entry_price=sig.entry_price,
        confidence=sig.confidence,
        up_score=sig.up_score,
        down_score=sig.down_score,
        factors=["15M 114", "110+1h"],
        htf_bias=sig.htf_bias,
    )


def make_114_on_close(ts_period: int) -> Callable[[dict, list, bool], None]:
    def _on_close(state: dict, history: list, win: bool) -> None:
        if win:
            state["loss_streak"] = 0
            return
        streak = int(state.get("loss_streak") or 0) + 1
        state["loss_streak"] = streak
        if streak >= LOSS_STREAK_LIMIT:
            state["loss_streak"] = 0
            state["cooldown_until"] = ts_period + COOLDOWN_SLOTS * _PERIOD_SECS
            print(
                f"[114] {LOSS_STREAK_LIMIT} kayıp serisi — "
                f"{COOLDOWN_SLOTS} slot mola (until ts={state['cooldown_until']})"
            )
    return _on_close


def slot_filter_114(state: dict, history: list, now_tr: datetime, ts_period: int) -> str | None:
    hour = now_tr.hour
    if hour < NIGHT_OPEN_START or hour >= NIGHT_OPEN_END:
        return f"gece saati ({NIGHT_OPEN_START:02d}:00–{NIGHT_OPEN_END:02d}:00 İST dışı)"
    cooldown_until = int(state.get("cooldown_until") or 0)
    if ts_period < cooldown_until:
        slots_left = max(1, (cooldown_until - ts_period + _PERIOD_SECS - 1) // _PERIOD_SECS)
        return f"kayıp serisi mola (~{slots_left} slot)"
    return None


def on_close_114(state: dict, history: list, win: bool, ts_period: int) -> None:
    make_114_on_close(ts_period)(state, history, win)

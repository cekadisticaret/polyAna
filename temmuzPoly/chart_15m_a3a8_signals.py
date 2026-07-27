"""Grafik overlay — 15m A8 (112) + A3 (113) UP/DOWN okları (1h A3/A8 mantığı, 15m mum)."""
from __future__ import annotations

from typing import Any

from btc_5m_105_algo import fetch_klines_15m
from chart_hourly_signals import _a3_direction, _jesse_direction

SYMBOL_DEFAULT = "SOLUSDT"


def compute_15m_chart_signals(
    symbol: str,
    t0: int | None = None,
    t1: int | None = None,
    *,
    lookback_bars: int = 48,
) -> dict[str, Any]:
    """15m A8→112, A3→113 sinyalleri — grafik marker listesi."""
    try:
        klines = fetch_klines_15m(symbol, max(120, lookback_bars + 40))
    except Exception as e:
        return {"ok": False, "error": str(e), "signals": [], "current": {}}

    if len(klines) < 35:
        return {"ok": False, "error": "yetersiz 15m veri", "signals": [], "current": {}}

    closed = klines[:-1]
    start_i = max(30, len(closed) - lookback_bars)
    signals: list[dict] = []

    for i in range(start_i, len(closed)):
        slice_k = closed[: i + 1]
        bar = closed[i]
        ts = int(bar["open_time"] // 1000)
        if t0 is not None and ts < t0 - 60:
            continue
        if t1 is not None and ts > t1 + 60:
            continue

        a8 = _jesse_direction(slice_k)
        if a8:
            signals.append({"time": ts, "dir": a8, "tag": "112"})

        a3 = _a3_direction(slice_k)
        if a3:
            signals.append({"time": ts, "dir": a3, "tag": "113"})

    current: dict[str, Any] = {}
    if closed:
        last_slice = closed
        a8_now = _jesse_direction(last_slice)
        a3_now = _a3_direction(last_slice)
        if a8_now:
            current["a112"] = {"dir": a8_now, "label": f"112 {'↑' if a8_now == 'UP' else '↓'}"}
        if a3_now:
            current["a113"] = {"dir": a3_now, "label": f"113 {'↑' if a3_now == 'UP' else '↓'}"}

    return {"ok": True, "signals": signals, "current": current}

"""Grafik overlay — 1. Analiz (A1) saatlik UP/DOWN okları."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import poly_predictor_analysis as ppa  # noqa: E402


def _fetch_1h_klines(symbol: str, limit: int = 72) -> list[dict]:
    url = (
        f"https://fapi.binance.com/fapi/v1/klines?"
        f"symbol={symbol}&interval=1h&limit={limit}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.load(resp)
    out: list[dict] = []
    for k in raw:
        out.append({
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "taker_buy": float(k[9]),
        })
    return out


def _a1_direction(klines: list[dict], slot_open_ms: int) -> str | None:
    if len(klines) < 30:
        return None
    old_slot = ppa._slot_utc_ms
    try:
        ppa._slot_utc_ms = slot_open_ms
        closes = [k["close"] for k in klines]
        rsi_val = ppa._rsi(closes)
        ema50 = ppa._ema(closes, 50)[-1]
        ema50_dev_pct = (closes[-1] - ema50) / ema50 * 100 if ema50 else 0.0
        mr_up_gate, mr_down_gate = 45, 40  # A1 — Kill Zone yok (yalnızca A2)

        conf_up, _ = ppa._mr_confluence_score(klines, rsi_val, 0.0, 0.0)
        conf_down, _ = ppa._mr_confluence_down_score(klines, rsi_val, 0.0, 0.0)
        sweep_up, sweep_down = ppa._liquidity_sweep_score(klines)
        conf_up += sweep_up
        conf_down += sweep_down
        if ema50_dev_pct < ppa._CRASH_EMA50_PCT:
            conf_up = -999

        if conf_up >= mr_up_gate or conf_down >= mr_down_gate:
            if conf_up >= conf_down and conf_up >= mr_up_gate:
                return "UP"
            if conf_down > conf_up and conf_down >= mr_down_gate:
                return "DOWN"
        return None
    finally:
        ppa._slot_utc_ms = old_slot


def compute_hourly_chart_signals(
    symbol: str,
    t0: int | None = None,
    t1: int | None = None,
    *,
    lookback_bars: int = 24,
) -> dict[str, Any]:
    """Saatlik A1 sinyalleri — grafik marker listesi."""
    try:
        klines = _fetch_1h_klines(symbol, limit=max(72, lookback_bars + 40))
    except Exception as e:
        return {"ok": False, "error": str(e), "signals": [], "current": {}}

    if len(klines) < 35:
        return {"ok": False, "error": "yetersiz 1h veri", "signals": [], "current": {}}

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

        a1 = _a1_direction(slice_k, bar["open_time"])
        if a1:
            signals.append({"time": ts, "dir": a1, "tag": "A1"})

    current: dict[str, Any] = {}
    last_slice = closed
    if last_slice:
        last_ms = last_slice[-1]["open_time"]
        a1_now = _a1_direction(last_slice, last_ms)
        if a1_now:
            current["a1"] = {"dir": a1_now, "label": f"A1 {'↑' if a1_now == 'UP' else '↓'}"}

    return {"ok": True, "signals": signals, "current": current}

"""XAUUSD mumlarını confluence_signal_engine ile skorlar — grafik overlay."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from confluence_signal_engine import EngineConfig, ShadowLogger, SignalEngine, SignalResult

_DIR = Path(__file__).resolve().parent
_SHADOW = str(_DIR / "shadow_signals.jsonl")

# Grafik TF → trend filtresi (üst dilim)
_HTF = {
    "1m": "1h",
    "5m": "1h",
    "15m": "1h",
    "30m": "1h",
    "1h": "4h",
    "4h": "1d",
    "1d": "1d",
}


def _to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    return pd.DataFrame({
        "open": [c["open"] for c in rows],
        "high": [c["high"] for c in rows],
        "low": [c["low"] for c in rows],
        "close": [c["close"] for c in rows],
    })


def _pack(res: SignalResult) -> dict:
    return {
        "direction": res.direction,
        "confidence": round(float(res.confidence), 1),
        "raw_score": round(float(res.raw_score), 1),
        "is_stable": bool(res.is_stable),
        "layers": {k: round(float(v), 1) for k, v in (res.layer_scores or {}).items()},
    }


def _neutral() -> dict:
    return {
        "direction": "NEUTRAL",
        "confidence": 0.0,
        "raw_score": 0.0,
        "is_stable": False,
        "layers": {"trend": 0.0, "momentum": 0.0, "pattern": 0.0},
    }


def overlay_signals(tf: str, candles: list[dict]) -> tuple[dict, list[dict]]:
    """Mevcut sinyal + kararlı yön değişimlerinde mum işaretleri."""
    if len(candles) < 30:
        return _neutral(), []

    from forex_data import get_xau_klines

    htf_tf = _HTF.get(tf, "1h")
    htf_rows, _ = get_xau_klines(htf_tf, 80)
    htf_df = _to_df(htf_rows) if htf_rows else None
    m1_df = _to_df(candles)

    engine = SignalEngine(EngineConfig(shadow_log_path="/dev/null"))
    start = 60 if len(candles) > 70 else max(26, len(candles) // 3)
    last: SignalResult | None = None
    last_stable: str | None = None
    markers: list[dict] = []

    for i in range(start, len(candles)):
        last = engine.process_candle(m1_df.iloc[: i + 1], htf_df)
        if last.is_stable and last.direction != last_stable:
            last_stable = last.direction
            markers.append({
                "time": int(candles[i]["time"]),
                "direction": last.direction,
                "confidence": round(float(last.confidence), 1),
            })

    if last is None:
        last = engine.process_candle(m1_df, htf_df)

    try:
        ShadowLogger(EngineConfig(shadow_log_path=_SHADOW)).log(last)
    except OSError:
        pass

    return _pack(last), markers[-48:]

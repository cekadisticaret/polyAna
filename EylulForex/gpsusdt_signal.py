"""GPSUSDT Kalman+VWAP + S/R — CEM01 forex_signal ile aynı motor, ayrı veri.

forex_signal.py / CEM01 gölge günlüğüne yazmaz.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from confluence_signal_engine import EngineConfig, SignalEngine, SignalResult

_HTF = {
    "1m": "1h", "5m": "1h", "15m": "1h", "30m": "1h",
    "1h": "4h", "4h": "1d", "1d": "1d",
}
_RAIL_CFG = EngineConfig(
    shadow_log_path="/dev/null",
    weight_trend=40.0, weight_momentum=35.0, weight_pattern=25.0,
    weight_tick=0.0, signal_threshold=55.0, stability_window=2,
)
_FAST_CFG = EngineConfig(
    shadow_log_path="/dev/null",
    weight_trend=0.0, weight_momentum=40.0, weight_pattern=15.0,
    weight_tick=45.0, signal_threshold=40.0, stability_window=1,
)
_TICK_LEAD = 50.0
_PX = 6


def _to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.DataFrame({
        "open": [c["open"] for c in rows],
        "high": [c["high"] for c in rows],
        "low": [c["low"] for c in rows],
        "close": [c["close"] for c in rows],
        "volume": [float(c.get("volume") or 0) for c in rows],
    })


def _pack(res: SignalResult, threshold: float = 55.0) -> dict:
    raw = float(res.raw_score)
    conf = abs(raw)
    if raw > 4:
        lean = "UP"
    elif raw < -4:
        lean = "DOWN"
    else:
        lean = "FLAT"
    return {
        "direction": res.direction,
        "confidence": round(conf, 1),
        "raw_score": round(raw, 1),
        "is_stable": bool(res.is_stable),
        "lean": lean,
        "fill": round(min(100.0, conf / threshold * 100.0), 1),
        "threshold": threshold,
        "layers": {k: round(float(v), 1) for k, v in (res.layer_scores or {}).items()},
        "engine": "kalman_vwap",
    }


def _neutral() -> dict:
    return {
        "direction": "NEUTRAL", "confidence": 0.0, "raw_score": 0.0,
        "is_stable": False, "lean": "FLAT", "fill": 0.0, "threshold": 55.0,
        "layers": {"trend": 0.0, "momentum": 0.0, "pattern": 0.0, "tick": 0.0},
        "engine": "kalman_vwap",
    }


def _apply_rail_veto(sig: dict, rail: dict | None) -> dict:
    if not rail or not sig:
        return sig
    direction = sig.get("direction") or "NEUTRAL"
    votes = []
    for tf in ("5m", "15m"):
        d = (rail.get(tf) or {}).get("direction")
        if d in ("UP", "DOWN"):
            votes.append(d)
    out = dict(sig)
    if direction not in ("UP", "DOWN"):
        return out
    opp = "DOWN" if direction == "UP" else "UP"
    if opp in votes and direction not in votes:
        out["direction"] = "NEUTRAL"
        out["is_stable"] = False
        out["veto"] = "rail"
        return out
    if opp in votes and direction in votes:
        out["is_stable"] = False
        out["veto"] = "rail_split"
        return out
    if direction in votes:
        out["is_stable"] = True
        out["rail_confirm"] = True
    return out


def _apply_tick_lead(sig: dict, tick: dict | None) -> dict:
    if not sig or not tick:
        return sig
    score = float(tick.get("score") or 0.0)
    n = int(tick.get("n") or 0)
    if n < 8 or abs(score) < _TICK_LEAD:
        return sig
    out = dict(sig)
    out["direction"] = "UP" if score > 0 else "DOWN"
    out["confidence"] = round(max(float(out.get("confidence") or 0), abs(score)), 1)
    out["tick_lead"] = True
    return out


def _price_impulse(df) -> float:
    if df is None or len(df) < 8:
        return 0.0
    c = [float(x) for x in df["close"].tolist()]
    hi = [float(x) for x in df["high"].tolist()]
    lo = [float(x) for x in df["low"].tolist()]
    n = min(14, len(c))
    floor = max(abs(c[-1]) * 0.00008, 1e-8)
    atr = max(sum(hi[-n + i] - lo[-n + i] for i in range(n)) / n, floor)
    ret5 = c[-1] - c[max(0, len(c) - 6)]
    drop = c[-1] - max(c[-12:])
    return max(-100.0, min(100.0, (ret5 / atr) * 45.0 + (drop / atr) * 20.0))


def _apply_price_lead(sig: dict, impulse: float) -> dict:
    if not sig or impulse > -40:
        return sig
    out = dict(sig)
    out["direction"] = "DOWN"
    out["confidence"] = round(max(float(out.get("confidence") or 0), abs(impulse)), 1)
    out["price_lead"] = True
    out.pop("tick_lead", None)
    return out


def _fetch_rows(tf: str, n: int, klines_fn=None) -> list[dict]:
    if klines_fn is not None:
        return list(klines_fn(tf, n) or [])
    from gpsusdt_data import gps_klines
    return gps_klines(tf, n)


def latest_signal(tf: str, candles: list[dict] | None = None, klines_fn=None) -> dict:
    if candles is None:
        candles = _fetch_rows(tf, 120, klines_fn)
    if len(candles) < 30:
        return _neutral()
    htf_df = _to_df(_fetch_rows(_HTF.get(tf, "1h"), 80, klines_fn))
    df = _to_df(candles)
    engine = SignalEngine(_RAIL_CFG)
    last = None
    for i in range(max(30, len(candles) - 3), len(candles)):
        last = engine.process_candle(df.iloc[: i + 1], htf_df)
    return _pack(last, _RAIL_CFG.signal_threshold) if last else _neutral()


def live_signal(tf: str, candles: list[dict] | None = None, klines_fn=None, tick: dict | None = None) -> dict:
    if candles is None:
        candles = _fetch_rows(tf, 120, klines_fn)
    if len(candles) < 30:
        return _neutral()
    htf_df = _to_df(_fetch_rows(_HTF.get(tf, "1h"), 80, klines_fn))
    df = _to_df(candles)
    engine = SignalEngine(_FAST_CFG)
    last = None
    score = float((tick or {}).get("score") or 0.0)
    for i in range(max(30, len(candles) - 2), len(candles)):
        last = engine.process_candle(
            df.iloc[: i + 1], htf_df,
            tick_score=score if i == len(candles) - 1 else 0.0,
        )
    packed = _pack(last, _FAST_CFG.signal_threshold) if last else _neutral()
    packed["engine"] = "kalman_vwap_tick"
    packed = _apply_tick_lead(packed, tick or {})
    packed = _apply_price_lead(packed, _price_impulse(df))
    return _apply_rail_veto(packed, rail_signals(klines_fn=klines_fn))


def overlay_signals(tf: str, candles: list[dict], klines_fn=None, tick: dict | None = None) -> tuple[dict, list[dict]]:
    if len(candles) < 30:
        return _neutral(), []
    htf_df = _to_df(_fetch_rows(_HTF.get(tf, "1h"), 80, klines_fn))
    m1_df = _to_df(candles)
    engine = SignalEngine(_RAIL_CFG)
    start = 60 if len(candles) > 70 else max(26, len(candles) // 3)
    last_stable = None
    markers = []
    last = None
    for i in range(start, len(candles)):
        last = engine.process_candle(m1_df.iloc[: i + 1], htf_df)
        if last.is_stable and last.direction != last_stable:
            last_stable = last.direction
            markers.append({
                "time": int(candles[i]["time"]),
                "direction": last.direction,
                "confidence": round(float(last.confidence), 1),
            })
    live = SignalEngine(_FAST_CFG)
    last = live.process_candle(m1_df, htf_df, tick_score=float((tick or {}).get("score") or 0))
    packed = _pack(last, _FAST_CFG.signal_threshold)
    packed["engine"] = "kalman_vwap_tick"
    packed = _apply_tick_lead(packed, tick or {})
    packed = _apply_price_lead(packed, _price_impulse(m1_df))
    rail = rail_signals(klines_fn=klines_fn)
    packed = _apply_rail_veto(packed, rail)
    packed["rail"] = rail
    return packed, markers[-48:]


def sr_levels(candles: list[dict]) -> dict:
    empty = {
        "ok": False, "nearest_support": None, "nearest_resistance": None,
        "support": [], "resistance": [], "ref": None,
    }
    if len(candles) < 8:
        return empty
    try:
        import sys
        sonnet = str(Path(__file__).resolve().parent.parent / "Sonnet")
        if sonnet not in sys.path:
            sys.path.insert(0, sonnet)
        import numpy as np
        from candle_pattern_engine1 import CandleEngine

        o = np.array([float(c["open"]) for c in candles], dtype=float)
        h = np.array([float(c["high"]) for c in candles], dtype=float)
        l = np.array([float(c["low"]) for c in candles], dtype=float)
        cl = np.array([float(c["close"]) for c in candles], dtype=float)
        engine = CandleEngine(o, h, l, cl)
        result = engine.confluence_score()
        levels = engine.detect_levels()

        def _level(lv):
            return {
                "price": round(float(lv.price), _PX),
                "kind": lv.kind,
                "touches": int(lv.touches),
                "strength": float(lv.strength),
            }

        def _prox(prox):
            if not prox:
                return None
            lv, dist = prox
            return {
                "price": round(float(lv.price), _PX),
                "strength": float(lv.strength),
                "dist_pct": float(dist),
            }

        day0 = int(candles[-1]["time"]) - (int(candles[-1]["time"]) % 86400)
        ref = None
        for c in candles:
            if int(c["time"]) >= day0:
                ref = round(float(c["open"]), _PX)
                break
        if ref is None:
            ref = round(float(candles[0]["open"]), _PX)
        return {
            "ok": True,
            "engine": "candle_pattern_engine1",
            "nearest_support": _prox(result.nearest_support),
            "nearest_resistance": _prox(result.nearest_resistance),
            "support": [_level(lv) for lv in levels["support"][:5]],
            "resistance": [_level(lv) for lv in levels["resistance"][:5]],
            "ref": ref,
        }
    except Exception as e:
        empty["error"] = str(e)[:160]
        return empty


def rail_signals(klines_fn=None) -> dict:
    from forex_data import bar_remaining

    out: dict[str, dict] = {}
    for tf, lab in (("5m", "M5"), ("15m", "M15")):
        rows = _fetch_rows(tf, 120, klines_fn)
        sig = latest_signal(tf, rows, klines_fn=klines_fn)
        closed = latest_signal(tf, rows[:-1], klines_fn=klines_fn) if len(rows) > 31 else sig
        sig["closed_direction"] = closed.get("direction")
        sig["closed_confidence"] = closed.get("confidence")
        sig["tf"] = tf
        sig["label"] = lab
        sig["bar_left"] = bar_remaining(tf)
        sig["bar_sec"] = 300 if tf == "5m" else 900
        out[tf] = sig
    return out

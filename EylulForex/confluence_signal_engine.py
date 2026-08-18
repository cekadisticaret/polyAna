"""
confluence_signal_engine.py
----------------------------
Anlik fiyat grafigi icin "kararli" yon tahmini ureten sinyal motoru.
(Cem'in Cursor'da adapte ettigi guncel versiyon - Kalman + VWAP)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Optional, Deque, List

import pandas as pd
import numpy as np


@dataclass
class EngineConfig:
    weight_trend: float = 40.0
    weight_momentum: float = 35.0
    weight_pattern: float = 25.0
    weight_tick: float = 0.0

    signal_threshold: float = 55.0
    stability_window: int = 2

    kalman_q: float = 8e-5
    kalman_r: float = 2e-2

    atr_period: int = 14
    atr_low_vol_percentile: float = 20.0
    low_vol_dampening: float = 0.5

    pattern_lookback: int = 5
    shadow_log_path: str = "shadow_signals.jsonl"


def _kalman_velocity(close: np.ndarray, q: float, r: float) -> float:
    if close.size < 8:
        return 0.0
    x = np.array([float(close[0]), 0.0])
    P = np.eye(2)
    F = np.array([[1.0, 1.0], [0.0, 1.0]])
    H = np.array([1.0, 0.0])
    Q = np.array([[q, 0.0], [0.0, q]])
    I = np.eye(2)
    for z in close:
        x = F @ x
        P = F @ P @ F.T + Q
        y = float(z) - float(H @ x)
        S = float(H @ P @ H.T) + r
        K = (P @ H) / S
        x = x + K * y
        P = (I - np.outer(K, H)) @ P
    return float(x[1])


def _vwap_z(df: pd.DataFrame) -> float:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    if "volume" in df.columns:
        vol = df["volume"].astype(float).clip(lower=0.0)
        if float(vol.sum()) <= 0:
            vol = pd.Series(1.0, index=df.index)
    else:
        vol = pd.Series(1.0, index=df.index)
    vwap = (tp * vol).cumsum() / vol.replace(0, np.nan).cumsum()
    vwap = vwap.ffill().fillna(df["close"])
    resid = df["close"] - vwap
    sig = float(resid.tail(min(40, len(resid))).std(ddof=0) or 0.0)
    if sig < 1e-6:
        return 0.0
    return float((df["close"].iloc[-1] - vwap.iloc[-1]) / sig)


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


class TrendFilter:
    def __init__(self, config: EngineConfig):
        self.cfg = config

    def score(self, htf_df: pd.DataFrame) -> float:
        if htf_df is None or len(htf_df) < 20:
            return 0.0
        close = htf_df["close"]
        ema_fast = close.ewm(span=20, adjust=False).mean()
        ema_slow = close.ewm(span=50, adjust=False).mean() if len(close) >= 50 else close.ewm(span=20).mean()
        last_fast, last_slow = ema_fast.iloc[-1], ema_slow.iloc[-1]
        spread_pct = (last_fast - last_slow) / last_slow * 100
        score = float(np.clip(spread_pct * 500, -100, 100))
        return score


class MomentumVolumeFilter:
    def __init__(self, config: EngineConfig):
        self.cfg = config
        self._atr_history: Deque[float] = deque(maxlen=500)

    def score(self, df: pd.DataFrame) -> float:
        if len(df) < 20:
            return 0.0
        close = df["close"].to_numpy(dtype=float)
        vel = _kalman_velocity(close, self.cfg.kalman_q, self.cfg.kalman_r)
        atr = _atr(df, self.cfg.atr_period)
        atr_last = float(atr.iloc[-1]) if len(atr) and not np.isnan(atr.iloc[-1]) else 0.4
        scale = max(atr_last, 0.15)
        kalman_score = float(np.clip(vel / scale * 55.0, -100, 100))

        z = _vwap_z(df)
        if vel > 0:
            vwap_score = float(np.clip(30.0 - z * 25.0, -80, 90))
        elif vel < 0:
            vwap_score = float(np.clip(-30.0 - z * 25.0, -90, 80))
        else:
            vwap_score = float(np.clip(-z * 20.0, -40, 40))

        raw_score = kalman_score * 0.60 + vwap_score * 0.40

        if not np.isnan(atr_last):
            self._atr_history.append(atr_last)
        if len(self._atr_history) >= 20:
            percentile = float((np.array(self._atr_history) < atr_last).mean() * 100)
            if percentile < self.cfg.atr_low_vol_percentile:
                raw_score *= self.cfg.low_vol_dampening

        return float(np.clip(raw_score, -100, 100))


class PatternFilter:
    def __init__(self, config: EngineConfig):
        self.cfg = config

    def score(self, df: pd.DataFrame) -> float:
        n = self.cfg.pattern_lookback
        if len(df) < n:
            return 0.0
        recent = df.tail(n)
        bodies = recent["close"] - recent["open"]
        bullish_ratio = (bodies > 0).sum() / n
        weighted = (bodies / recent["close"]).sum() * 10000
        directional_bias = (bullish_ratio - 0.5) * 200
        momentum_component = float(np.clip(weighted, -60, 60))
        score = (directional_bias * 0.6) + (momentum_component * 0.4)
        return float(np.clip(score, -100, 100))


@dataclass
class SignalResult:
    timestamp: float
    raw_score: float
    confidence: float
    direction: str
    is_stable: bool
    layer_scores: dict = field(default_factory=dict)


class SignalStabilizer:
    def __init__(self, config: EngineConfig):
        self.cfg = config
        self._history: Deque[str] = deque(maxlen=config.stability_window)

    def update(self, direction: str) -> bool:
        self._history.append(direction)
        if len(self._history) < self.cfg.stability_window:
            return False
        return len(set(self._history)) == 1 and direction != "NEUTRAL"


class ConfluenceEngine:
    def __init__(self, config: EngineConfig):
        self.cfg = config
        self.trend = TrendFilter(config)
        self.momentum = MomentumVolumeFilter(config)
        self.pattern = PatternFilter(config)

    def compute(self, m1_df, htf_df, tick_score: float = 0.0) -> SignalResult:
        trend_score = self.trend.score(htf_df)
        momentum_score = self.momentum.score(m1_df)
        pattern_score = self.pattern.score(m1_df)
        tick = float(np.clip(tick_score, -100, 100))

        cfg = self.cfg
        w_tick = cfg.weight_tick if cfg.weight_tick > 0 else 0.0
        parts = [
            (trend_score, cfg.weight_trend),
            (momentum_score, cfg.weight_momentum),
            (pattern_score, cfg.weight_pattern),
        ]
        if w_tick > 0:
            parts.append((tick, w_tick))
        total_weight = sum(w for _, w in parts) or 1.0
        raw = sum(s * w for s, w in parts) / total_weight

        confidence = abs(raw)
        direction = "NEUTRAL" if confidence < cfg.signal_threshold else ("UP" if raw > 0 else "DOWN")

        layers = {"trend": trend_score, "momentum": momentum_score, "pattern": pattern_score}
        if w_tick > 0:
            layers["tick"] = tick

        return SignalResult(
            timestamp=time.time(), raw_score=raw, confidence=confidence,
            direction=direction, is_stable=False, layer_scores=layers,
        )


class ShadowLogger:
    def __init__(self, config: EngineConfig):
        self.path = config.shadow_log_path

    def log(self, result: SignalResult):
        record = {
            "ts": result.timestamp, "raw_score": round(result.raw_score, 2),
            "confidence": round(result.confidence, 2), "direction": result.direction,
            "is_stable": result.is_stable,
            "layers": {k: round(v, 2) for k, v in result.layer_scores.items()},
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class SignalEngine:
    def __init__(self, config: Optional[EngineConfig] = None):
        self.cfg = config or EngineConfig()
        self.confluence = ConfluenceEngine(self.cfg)
        self.stabilizer = SignalStabilizer(self.cfg)
        self.shadow_logger = ShadowLogger(self.cfg)

    def process_candle(self, m1_df, htf_df=None, tick_score: float = 0.0) -> SignalResult:
        result = self.confluence.compute(m1_df, htf_df, tick_score=tick_score)
        result.is_stable = self.stabilizer.update(result.direction)
        self.shadow_logger.log(result)
        return result

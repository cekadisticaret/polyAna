"""ALFA — A1 + A3 + A8 konsensüs sinyali (BTC/SOL, saatlik PM).

Mevcut analiz modüllerinin koduna dokunmaz; yalnizca import/read-only history.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "freqtrade") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "freqtrade"))
if os.path.join(_ROOT, "jesse") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "jesse"))

MIN_AGREE = 2          # en az 2/3 ayni yon
MIN_SCORE = 52.0       # agirlikli puan esigi (0-100)
DEFAULT_WR = 0.5       # motor gecmisi yoksa

ENGINE_META = (
    ("a1", "A1", os.path.join(_ROOT, "temmuzPoly", "poly_trader_analiz1_history.json")),
    ("a3", "A3", os.path.join(_ROOT, "freqtrade", "user_data", "analiz3_freqtrade_history.json")),
    ("a8", "A8", os.path.join(_ROOT, "jesse", "storage", "analiz8_jesse_history.json")),
)


@dataclass
class EngineVote:
    key: str
    label: str
    predicted_dir: str | None
    confidence: float
    wr_weight: float
    detail: str = ""


@dataclass
class AlfaDecision:
    symbol: str
    predicted_dir: str | None
    score: float
    votes: list[EngineVote] = field(default_factory=list)
    agree_count: int = 0
    skip_reason: str = ""

    @property
    def should_trade(self) -> bool:
        return self.predicted_dir is not None and not self.skip_reason


def _load_history(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def engine_wr(history_path: str, symbol: str) -> float:
    trades = [t for t in _load_history(history_path) if t.get("symbol") == symbol]
    if len(trades) < 3:
        return DEFAULT_WR
    wins = sum(1 for t in trades if t.get("win"))
    return wins / len(trades)


async def _vote_a1(symbol: str) -> EngineVote:
    from poly_predictor_analysis import predict

    path = ENGINE_META[0][2]
    try:
        pred = await predict(symbol)
    except Exception as exc:
        return EngineVote("a1", "A1", None, 0.0, engine_wr(path, symbol), f"hata:{exc}")

    if pred is None or not pred.predicted_dir:
        return EngineVote("a1", "A1", None, 0.0, engine_wr(path, symbol), "sinyal yok")

    conf = max(pred.prob_up, pred.prob_down)
    return EngineVote(
        "a1", "A1", pred.predicted_dir, conf, engine_wr(path, symbol),
        f"RSI:{pred.rsi:.0f} {pred.trend}",
    )


def _vote_a3(symbol: str) -> EngineVote:
    path = ENGINE_META[1][2]
    try:
        from analiz3_signal import predict_pm_direction
        sig = predict_pm_direction(symbol)
    except Exception as exc:
        return EngineVote("a3", "A3", None, 0.0, engine_wr(path, symbol), f"hata:{exc}")

    if sig is None:
        return EngineVote("a3", "A3", None, 0.0, engine_wr(path, symbol), "sinyal yok")

    conf = max(sig.prob_up, sig.prob_down)
    return EngineVote(
        "a3", "A3", sig.predicted_dir, conf, engine_wr(path, symbol),
        f"RSI:{sig.rsi:.0f} TEMA:{'↑' if sig.tema_rising else '↓'}",
    )


def _vote_a8(symbol: str) -> EngineVote:
    path = ENGINE_META[2][2]
    try:
        from analiz8_signal import predict_pm_direction
        sig = predict_pm_direction(symbol)
    except Exception as exc:
        return EngineVote("a8", "A8", None, 0.0, engine_wr(path, symbol), f"hata:{exc}")

    if sig is None:
        return EngineVote("a8", "A8", None, 0.0, engine_wr(path, symbol), "sinyal yok")

    conf = max(sig.prob_up, sig.prob_down)
    cross = "Golden✓" if sig.golden_cross else "Golden✗"
    return EngineVote(
        "a8", "A8", sig.predicted_dir, conf, engine_wr(path, symbol),
        f"RSI:{sig.rsi:.0f} {cross}",
    )


def _score_votes(votes: list[EngineVote]) -> tuple[str | None, float, int, str]:
    valid = [v for v in votes if v.predicted_dir in ("UP", "DOWN")]
    if len(valid) < MIN_AGREE:
        return None, 0.0, 0, f"yetersiz motor ({len(valid)}/3)"

    up_pts = sum(v.wr_weight * v.confidence for v in valid if v.predicted_dir == "UP")
    down_pts = sum(v.wr_weight * v.confidence for v in valid if v.predicted_dir == "DOWN")
    predicted = "UP" if up_pts >= down_pts else "DOWN"
    agree = [v for v in valid if v.predicted_dir == predicted]
    if len(agree) < MIN_AGREE:
        return None, 0.0, len(agree), "konsensüs yok (2/3 gerekli)"

    total_w = sum(v.wr_weight for v in valid) or 1.0
    win_pts = max(up_pts, down_pts)
    score = (win_pts / total_w) * 100.0
    if score < MIN_SCORE:
        return None, score, len(agree), f"puan dusuk ({score:.0f}<{MIN_SCORE:.0f})"

    return predicted, score, len(agree), ""


async def analyze_symbol(symbol: str) -> AlfaDecision:
    votes = [
        await _vote_a1(symbol),
        _vote_a3(symbol),
        _vote_a8(symbol),
    ]
    predicted, score, agree, reason = _score_votes(votes)
    return AlfaDecision(
        symbol=symbol,
        predicted_dir=predicted,
        score=round(score, 1),
        votes=votes,
        agree_count=agree,
        skip_reason=reason,
    )


def amount_for_decision(base_amount: float, decision: AlfaDecision) -> float:
    """Konsensüs gücüne göre tutar (ALFA kendi WR tabanını kullanır)."""
    if not decision.should_trade:
        return 0.0
    amt = base_amount
    if decision.agree_count >= 3:
        amt = min(base_amount * 1.15, 20.0)
    elif decision.score < 58:
        amt = max(base_amount * 0.85, 12.0)
    return round(amt, 2)

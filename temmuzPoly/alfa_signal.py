"""ALFA — A1 + A3 + A8 (+ SOL Markov #35) konsensüs sinyali.

SOL: 4 motor — 2/4→$6, 3/4→$12, 4/4→$24
BTC/ETH: 3 motor — 2/3→$8, 3/3→$16
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_DIR_POLY = os.path.join(_ROOT, "temmuzPoly")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _DIR_POLY not in sys.path:
    sys.path.insert(0, _DIR_POLY)
if os.path.join(_ROOT, "freqtrade") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "freqtrade"))
if os.path.join(_ROOT, "jesse") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "jesse"))

AMOUNT_2 = 8.0
AMOUNT_3 = 16.0
AMOUNT_SOL_2 = 6.0
AMOUNT_SOL_3 = 12.0
AMOUNT_SOL_4 = 24.0
DEFAULT_WR = 0.5
MARKOV_SOL_WR = 0.568

ENGINE_META = (
    ("a1", "A1", os.path.join(_DIR_POLY, "poly_trader_analiz1_history.json")),
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
    engine_total: int = 3
    skip_reason: str = ""
    amount_usd: float = 0.0
    consensus_mode: str = ""

    @property
    def should_trade(self) -> bool:
        return (
            self.predicted_dir in ("UP", "DOWN")
            and self.amount_usd > 0
            and not self.skip_reason
        )


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


def _vote_markov(symbol: str) -> EngineVote:
    if symbol != "SOLUSDT":
        return EngineVote("m35", "M35", None, 0.0, MARKOV_SOL_WR, "SOL harici")
    try:
        from algo_signals import fetch_klines, markov_chain
        kl = fetch_klines("SOLUSDT", "1h", 80)
        sig = markov_chain(kl)
        if sig not in ("UP", "DOWN"):
            return EngineVote("m35", "M35", None, 0.0, MARKOV_SOL_WR, "nötr")
        return EngineVote(
            "m35", "M35", sig, MARKOV_SOL_WR, MARKOV_SOL_WR,
            f"Markov#35 {sig}",
        )
    except Exception as exc:
        return EngineVote("m35", "M35", None, 0.0, MARKOV_SOL_WR, f"hata:{exc}")


def _resolve_decision(
    votes: list[EngineVote], symbol: str,
) -> tuple[str | None, float, int, str, float, str, int]:
    """Oy çokluğu; SOL 4'lü, diğerleri 3'lü panel."""
    is_sol = symbol == "SOLUSDT"
    pool = 4 if is_sol else 3
    up = sum(1 for v in votes if v.predicted_dir == "UP")
    down = sum(1 for v in votes if v.predicted_dir == "DOWN")

    if up == 0 and down == 0:
        return None, 0.0, 0, "motor sinyali yok", 0.0, "", pool
    if up == down:
        return None, 0.0, max(up, down), f"beraberlik ({up}-{down})", 0.0, "", pool

    if up > down:
        direction, agree = "UP", up
    else:
        direction, agree = "DOWN", down

    if agree < 2:
        return None, 0.0, agree, f"uyum yetersiz ({agree}/{pool})", 0.0, "", pool

    if is_sol:
        if agree >= 4:
            amount, mode = AMOUNT_SOL_4, "4of4"
        elif agree == 3:
            amount, mode = AMOUNT_SOL_3, "3of4"
        else:
            amount, mode = AMOUNT_SOL_2, "2of4"
    elif agree >= 3:
        amount, mode = AMOUNT_3, "3of3"
    else:
        amount, mode = AMOUNT_2, "2of3"

    score = round(agree / pool * 100.0, 1)
    return direction, score, agree, "", amount, mode, pool


async def analyze_symbol(symbol: str) -> AlfaDecision:
    votes = [
        await _vote_a1(symbol),
        _vote_a3(symbol),
        _vote_a8(symbol),
    ]
    if symbol == "SOLUSDT":
        votes.append(_vote_markov(symbol))
    predicted, score, agree, reason, amount, mode, pool = _resolve_decision(votes, symbol)
    return AlfaDecision(
        symbol=symbol,
        predicted_dir=predicted,
        score=score,
        votes=votes,
        agree_count=agree,
        engine_total=pool,
        skip_reason=reason,
        amount_usd=amount,
        consensus_mode=mode,
    )


def amount_for_decision(decision: AlfaDecision) -> float:
    if not decision.should_trade:
        return 0.0
    return round(float(decision.amount_usd), 2)


def consensus_mode_label(dec: AlfaDecision) -> str:
    if not dec.consensus_mode:
        return "—"
    return _mode_amount_label(dec.consensus_mode)


def _mode_amount_label(mode: str | None) -> str:
    mapping = {
        "2of4": f"2/4 ${AMOUNT_SOL_2:.0f}",
        "3of4": f"3/4 ${AMOUNT_SOL_3:.0f}",
        "4of4": f"4/4 ${AMOUNT_SOL_4:.0f}",
        "2of3": f"2/3 ${AMOUNT_2:.0f}",
        "3of3": f"3/3 ${AMOUNT_3:.0f}",
    }
    return mapping.get(mode or "", "—")


def chart_current_from_hourly(hourly_current: dict, symbol: str) -> dict:
    """Dashboard 1h rozeti — görünen A1/A3/A8 + SOL Markov ile ALFA kararı."""
    votes: list[EngineVote] = []
    for key, label in (("a1", "A1"), ("a3", "A3"), ("a8", "A8")):
        cur = hourly_current.get(key) or {}
        d = cur.get("dir")
        d = d if d in ("UP", "DOWN") else None
        votes.append(EngineVote(key, label, d, 0.5, DEFAULT_WR))
    if symbol == "SOLUSDT":
        votes.append(_vote_markov(symbol))
    predicted, score, agree, reason, amount, mode, pool = _resolve_decision(votes, symbol)
    if predicted:
        arrow = "↑" if predicted == "UP" else "↓"
        return {
            "dir": predicted,
            "label": f"ALFA {arrow}",
            "detail": _mode_amount_label(mode),
            "amount": amount,
            "mode": mode,
            "agree": agree,
            "engines": pool,
            "score": score,
        }
    return {
        "dir": None,
        "label": "ALFA —",
        "detail": reason or "—",
        "amount": 0,
        "mode": "",
        "agree": agree,
        "engines": pool,
        "score": 0,
    }

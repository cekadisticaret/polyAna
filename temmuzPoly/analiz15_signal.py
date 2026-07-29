"""15. Analiz — sembol bazlı en iyi motor birleşimi.

BTC → A6 MACD Histogram Divergence (#26)
ETH → A8 Jesse GoldenCross EMA 8/21 (sıkı mod, kesişim)
SOL → A2 poly_predictor_analysis (standard, fallback kapalı)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from algo_signals import fetch_klines as _algo_fetch_klines, macd_histogram_div
from a3a8_signal_mode import a8_direction

# A15 ETH: her zaman sıkı A8 (EMA8/21 kesişim) — global a3a8_signal_strict'ten bağımsız
A15_ETH_A8_STRICT = True
from backtest_common import to_algo21_klines
from backtest_analiz2 import _neutral_preloaded
from poly_predictor_analysis import predict

import poly_predictor_analysis as pa

_TZ_TR = ZoneInfo("Europe/Istanbul")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

SYMBOL_ENGINE: dict[str, tuple[str, str]] = {
    "BTCUSDT": ("a6", "MACD Hist. Div"),
    "ETHUSDT": ("a8", "Jesse EMA8/21"),
    "SOLUSDT": ("a2", "Poly Predictor"),
}


def engine_label(symbol: str) -> str:
    return SYMBOL_ENGINE.get(symbol, ("?", "?"))[1]


def _klines_to_predict(klines: list[dict]) -> list[dict]:
    return [
        {
            "open_time": k.get("open_time", 0),
            "open": k["open"],
            "high": k["high"],
            "low": k["low"],
            "close": k["close"],
            "volume": k.get("volume", 0),
            "taker_buy": k.get("taker_buy", 0),
        }
        for k in klines
    ]


def direction_a6(klines: list[dict]) -> str | None:
    sig = macd_histogram_div(to_algo21_klines(klines))
    return sig if sig in ("UP", "DOWN") else None


def direction_a8(klines: list[dict], *, strict: bool | None = None) -> str | None:
    return a8_direction(klines, strict=strict)


async def direction_a2(klines: list[dict], symbol: str, open_ms: int | None = None) -> str | None:
    """Canlı/backtest: yalnızca predict() — fallback yok (A2 ALLOW_FALLBACK=False)."""
    if open_ms is not None:
        pa._slot_utc_ms = open_ms
    try:
        pred = await predict(symbol, preloaded=_neutral_preloaded(_klines_to_predict(klines)))
    finally:
        if open_ms is not None:
            pa._slot_utc_ms = None
    if pred is None:
        return None
    d = getattr(pred, "predicted_dir", None)
    return d if d in ("UP", "DOWN") else None


async def resolve_direction(
    symbol: str,
    klines: list[dict] | None = None,
    open_ms: int | None = None,
    *,
    a8_strict: bool | None = None,
) -> str | None:
    key = SYMBOL_ENGINE.get(symbol, ("", ""))[0]
    if key == "a6":
        if not klines:
            return None
        return direction_a6(klines)
    if key == "a8":
        if not klines:
            return None
        strict = A15_ETH_A8_STRICT if a8_strict is None else a8_strict
        return direction_a8(klines, strict=strict)
    if key == "a2":
        if not klines:
            kl = await asyncio.to_thread(_algo_fetch_klines, symbol, "1h", 80)
            klines = [
                {
                    "open_time": 0,
                    "open": x["o"], "high": x["h"], "low": x["l"],
                    "close": x["c"], "volume": x.get("v", 0), "taker_buy": 0,
                }
                for x in kl
            ]
        return await direction_a2(klines, symbol, open_ms)
    return None


async def resolve_live_signal(symbol: str) -> tuple[str | None, float | None, str]:
    """Canlı trader: (direction, price, engine_label)."""
    engine = engine_label(symbol)
    try:
        kl_raw = await asyncio.to_thread(_algo_fetch_klines, symbol, "1h", 80)
    except Exception:
        return None, None, engine
    if len(kl_raw) < 30:
        return None, None, engine
    price = float(kl_raw[-1]["c"])
    klines = [
        {
            "open_time": 0,
            "open": x["o"], "high": x["h"], "low": x["l"],
            "close": x["c"], "volume": x.get("v", 0), "taker_buy": 0,
        }
        for x in kl_raw
    ]
    direction = await resolve_direction(symbol, klines)
    if direction not in ("UP", "DOWN"):
        return None, price, engine
    return direction, price, engine

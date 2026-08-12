#!/usr/bin/env python3
"""Test sinyal motorları — Poly kaynaklarından okur, mevcut trader'lara dokunmaz."""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
_ALGO_DIR = os.path.join(_ROOT, "AgustosKripto", "Algoritmalar")
for p in (_POLY, _ALGO_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from algo_signals import macd_histogram_div, mean_reversion, rsi_divergence_strict  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "agustos_algo_catalog",
    os.path.join(_ALGO_DIR, "catalog.py"),
)
_algo_cat = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_algo_cat)

from backtest_common import to_algo21_klines  # noqa: E402
from backtest_analiz2 import _neutral_preloaded  # noqa: E402


def _bars_ohlc(kl: list) -> list:
    return _algo_cat._bars_ohlc(kl)


def _kl_to_predict(kl: list) -> list:
    return [
        {
            "open_time": 0,
            "open": x.get("o", x.get("open", 0)),
            "high": x.get("h", x.get("high", 0)),
            "low": x.get("l", x.get("low", 0)),
            "close": x.get("c", x.get("close", 0)),
            "volume": x.get("v", x.get("volume", 0)),
            "taker_buy": 0,
        }
        for x in kl
    ]


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ── Poly islemler sinyalleri ─────────────────────────────────

_ANALIZ6_ALGOS = {
    "BTCUSDT": macd_histogram_div,
    "SOLUSDT": macd_histogram_div,
    "ETHUSDT": rsi_divergence_strict,
}
_ANALIZ6_V2_ALGOS = {
    "BTCUSDT": macd_histogram_div,
    "ETHUSDT": rsi_divergence_strict,
}


def _poly_analiz1_2(kl_by_symbol: dict[str, list]) -> dict[str, str]:
    from poly_predictor_analysis import predict  # noqa: E402

    out = {sym: "NEUTRAL" for sym in kl_by_symbol}

    async def _one(sym: str, kl: list):
        if len(kl) < 30:
            return sym, "NEUTRAL"
        try:
            pred = await predict(sym, preloaded=_neutral_preloaded(_kl_to_predict(kl)))
            d = getattr(pred, "predicted_dir", None) if pred else None
            return sym, d if d in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test A1/A2] {sym}: {e}")
            return sym, "NEUTRAL"

    async def _all():
        return await asyncio.gather(*[_one(s, kl) for s, kl in kl_by_symbol.items()])

    for sym, d in _run_async(_all()):
        out[sym] = d
    return out


def _poly_analiz6(key: str, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    algos = _ANALIZ6_V2_ALGOS if key == "analiz6_v2" else _ANALIZ6_ALGOS
    default = macd_histogram_div
    out = {}
    for sym, kl in kl_by_symbol.items():
        if len(kl) < 30:
            out[sym] = "NEUTRAL"
            continue
        fn = algos.get(sym, default)
        try:
            bars = to_algo21_klines(kl) if key != "analiz6_v3" else kl
            sig = fn(bars) if callable(fn) else "NEUTRAL"
            out[sym] = sig if sig in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test {key}] {sym}: {e}")
            out[sym] = "NEUTRAL"
    return out


def _poly_analiz6_v3(kl_by_symbol: dict[str, list]) -> dict[str, str]:
    from analiz6_v3_signal import resolve_live_signal, SYMBOLS as _A6V3_SYMBOLS  # noqa: E402

    out = {sym: "NEUTRAL" for sym in kl_by_symbol}
    # A6V3 sadece BTC/ETH/SOL destekler — diğer 17 coin için gereksiz
    # Binance çağrısı yapmayı (rate-limit gürültüsü) önle; sinyal aynı kalır.
    supported = [s for s in kl_by_symbol if s in _A6V3_SYMBOLS]

    async def _one(sym: str):
        try:
            d, _, _ = await resolve_live_signal(sym)
            return sym, d if d in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test A6V3] {sym}: {e}")
            return sym, "NEUTRAL"

    async def _all():
        return await asyncio.gather(*[_one(s) for s in supported])

    for sym, d in _run_async(_all()):
        out[sym] = d
    return out


def _poly_melez(kl_by_symbol: dict[str, list]) -> dict[str, str]:
    """MELEZ — BTC: MACD Hist. Div (A6V3 bacağı) · diğer: Mean Reversion (A2#05 bacağı).

    Poly tarafında melez yalnız BTC/ETH/SOL işler; 30 coin evreninde ETH/SOL
    motoru (mean reversion) altlara da uygulanır ki diğer defterlerle
    karşılaştırılabilir olsun.
    """
    out = {}
    for sym, kl in kl_by_symbol.items():
        if len(kl) < 30:
            out[sym] = "NEUTRAL"
            continue
        fn = macd_histogram_div if sym == "BTCUSDT" else mean_reversion
        try:
            sig = fn(kl)
            out[sym] = sig if sig in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test MELEZ] {sym}: {e}")
            out[sym] = "NEUTRAL"
    return out


def _poly_analiz15(kl_by_symbol: dict[str, list]) -> dict[str, str]:
    from analiz15_signal import resolve_direction  # noqa: E402

    out = {sym: "NEUTRAL" for sym in kl_by_symbol}

    async def _one(sym: str, kl: list):
        try:
            d = await resolve_direction(sym, kl)
            return sym, d if d in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test A15] {sym}: {e}")
            return sym, "NEUTRAL"

    async def _all():
        return await asyncio.gather(*[_one(s, kl) for s, kl in kl_by_symbol.items()])

    for sym, d in _run_async(_all()):
        out[sym] = d
    return out


def _poly_b1_mum(kl_by_symbol: dict[str, list]) -> dict[str, str]:
    from b1_mum_signal import resolve_direction  # noqa: E402

    out = {sym: "NEUTRAL" for sym in kl_by_symbol}
    for sym, kl in kl_by_symbol.items():
        if len(kl) < 30:
            continue
        try:
            d = resolve_direction(sym, kl)
            if d in ("UP", "DOWN"):
                out[sym] = d
        except Exception as e:
            print(f"[Test b1_mum] {sym}: {e}")
    return out


def _poly_b1(source_key: str, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    mod = __import__(
        "b1_02_signal" if source_key == "b1_02" else "b1_01_signal",
        fromlist=["resolve_live_signal"],
    )
    out = {sym: "NEUTRAL" for sym in kl_by_symbol}

    async def _one(sym: str):
        try:
            d, _, _ = await mod.resolve_live_signal(sym)
            return sym, d if d in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test {source_key}] {sym}: {e}")
            return sym, "NEUTRAL"

    async def _all():
        return await asyncio.gather(*[_one(s) for s in kl_by_symbol])

    for sym, d in _run_async(_all()):
        out[sym] = d
    return out


def _poly_islemler(book: dict, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    key = book["source_key"]
    if key in ("analiz1", "analiz2"):
        return _poly_analiz1_2(kl_by_symbol)
    if key == "analiz6_v3":
        return _poly_analiz6_v3(kl_by_symbol)
    if key == "melez":
        return _poly_melez(kl_by_symbol)
    if key in ("analiz6", "analiz6_v2"):
        return _poly_analiz6(key, kl_by_symbol)
    if key == "analiz15":
        return _poly_analiz15(kl_by_symbol)
    if key == "b1_mum":
        return _poly_b1_mum(kl_by_symbol)
    if key in ("b1_01", "b1_02"):
        return _poly_b1(key, kl_by_symbol)
    return {sym: "NEUTRAL" for sym in kl_by_symbol}


def signal_for_book(book: dict, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    src = book.get("source") or ""
    if src == "islemler_poly":
        return _poly_islemler(book, kl_by_symbol)
    if src == "islemler_a2":
        return _algo_cat.signal_for_book(book, kl_by_symbol)
    if src == "algo1":
        return _algo_cat.signal_for_book(book, kl_by_symbol)
    return {sym: "NEUTRAL" for sym in kl_by_symbol}


def pick_candidates(signals: dict[str, str], *, max_n: int = 6) -> list[dict]:
    return _algo_cat.pick_candidates(signals, max_n=max_n)

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
_ANALIZ_DIR = os.path.join(_ROOT, "AgustosKripto", "Analizler")
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

_an_spec = importlib.util.spec_from_file_location(
    "agustos_analiz_signals",
    os.path.join(_ANALIZ_DIR, "signals.py"),
)
_an_sig = importlib.util.module_from_spec(_an_spec)
assert _an_spec.loader is not None
_an_spec.loader.exec_module(_an_sig)

from backtest_common import to_algo21_klines  # noqa: E402
from backtest_analiz2 import _neutral_preloaded  # noqa: E402

_ST_EXCLUDE = frozenset({"BTCUSDT", "ETHUSDT"})
_ST_SLOW = frozenset({"SOLUSDT"})


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


_B1_MUM_SKIP = frozenset({"KAITOUSDT"})


def _poly_b1_mum(kl_by_symbol: dict[str, list]) -> dict[str, str]:
    from b1_mum_signal import resolve_direction  # noqa: E402

    out = {sym: "NEUTRAL" for sym in kl_by_symbol}
    for sym, kl in kl_by_symbol.items():
        if (sym or "").upper() in _B1_MUM_SKIP:
            continue
        if len(kl) < 30:
            continue
        try:
            d = resolve_direction(sym, kl)
            if d in ("UP", "DOWN"):
                out[sym] = d
        except Exception as e:
            print(f"[Test b1_mum] {sym}: {e}")
    return out


# B1#04 ve B1#05 kendi evrenleriyle (BTC/ETH/SOL) sınırlı tutulur: #04'ün küme
# ağırlıkları ve #05'in coin→motor eşlemesi Poly geçmişinden geliyor ve o geçmiş
# yalnız bu üç coin için var. 30 coine açmak turu 2 sn'den 34 sn'ye çıkarıyor
# (ölçüldü) ve tur saatte 6 kez koşuyor — A6V3'teki aynı gerekçe. b1_01/b1_02
# 30 coinde koşmaya devam ediyor, davranışları bilerek değiştirilmedi.
_B1_MAJORS_ONLY = {"b1_04", "b1_05"}


def _poly_b1(source_key: str, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    mod = __import__(f"{source_key}_signal", fromlist=["resolve_live_signal"])
    out = {sym: "NEUTRAL" for sym in kl_by_symbol}
    syms = list(kl_by_symbol)
    if source_key in _B1_MAJORS_ONLY:
        supported = set(getattr(mod, "SYMBOLS", ()) or ())
        syms = [s for s in syms if s in supported]

    async def _one(sym: str):
        try:
            d, _, _ = await mod.resolve_live_signal(sym)
            return sym, d if d in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test {source_key}] {sym}: {e}")
            return sym, "NEUTRAL"

    async def _all():
        return await asyncio.gather(*[_one(s) for s in syms])

    for sym, d in _run_async(_all()):
        out[sym] = d
    return out


def _poly_c101(kl_by_symbol: dict[str, list], *, band: float | None = None) -> dict[str, str]:
    """C1#01 modelinin yön görüşü — Polymarket kotasyonu olmadan.

    Poly'de C1#01 "piyasa yanlış fiyatlamış mı" diye sorar: model olasılığını
    bilet fiyatıyla karşılaştırıp aradaki farkı arar. Kripto futures'ta
    karşılaştırılacak bir bilet yok, o yüzden burada modelin **kendi görüşü**
    ölçülüyor: P(UP) yazı-turadan (0,50) en az `band` kadar uzaksa o yöne
    girilir. Eşik uydurma değil, defterlerin kendi sabitleri — C1#01 5 puan,
    C1#01 V2 3 puan. Kriptoya taşınabilen tek fark bu: V2'nin asıl ayrımı
    (gerçek ask vs bayat mid) futures'ta karşılıksız, ama "daha düşük çıtayla
    daha sık işlem" iddiası aynen sınanabilir.

    Bu yüzden ayna "C1#01 kâr eder mi"yi değil, projedeki tek emir-akışı
    beslemeli modelin (derinlik · funding · OI · CVD) yönü tutturup
    tutturmadığını sınar.

    `update_baseline=False` şart: derinlik referansı EWMA'sı Poly defterinin
    dosyasında tutuluyor, ayna onu kirletmemeli.
    """
    from datetime import datetime, timedelta, timezone

    import c101_signal as cs  # noqa: E402

    now_tr = datetime.now(timezone(timedelta(hours=3)))
    supported = set(getattr(cs, "SYMBOLS", ()) or ())
    if band is None:
        band = float(getattr(cs, "EDGE_MIN", 0.05))
    out = {sym: "NEUTRAL" for sym in kl_by_symbol}
    for sym in kl_by_symbol:
        if sym not in supported:
            continue
        try:
            model = cs.fair_probability(sym, now_tr, update_baseline=False)
            if not model:
                continue
            p_up = float(model["p_up"])
            if p_up >= 0.5 + band:
                out[sym] = "UP"
            elif p_up <= 0.5 - band:
                out[sym] = "DOWN"
        except Exception as e:
            print(f"[Test C101] {sym}: {e}")
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
    if key in ("b1_01", "b1_02", "b1_04", "b1_05"):
        return _poly_b1(key, kl_by_symbol)
    if key == "c101":
        return _poly_c101(kl_by_symbol)
    if key == "c101_v2":
        # Eşik V2 trader'ıyla aynı kaynaktan; `poly_trader_c101_v2` **import
        # edilmez** çünkü o modül `poly_trader_c101`'in globallerini ezer ve
        # aynı süreçte iki defter birlikte koşamaz.
        return _poly_c101(kl_by_symbol, band=float(os.environ.get("C101_V2_EDGE_MIN") or 0.03))
    return {sym: "NEUTRAL" for sym in kl_by_symbol}


def _analiz_a10(kl_by_symbol: dict[str, list]) -> dict[str, str]:
    out = {}
    for sym, kl in kl_by_symbol.items():
        try:
            d = _an_sig.signal_a10(sym, kl)
            out[sym] = d if d in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test A10] {sym}: {e}")
            out[sym] = "NEUTRAL"
    return out


def _analiz_st(kl_by_symbol: dict[str, list]) -> dict[str, str]:
    out = {}
    for sym, kl in kl_by_symbol.items():
        try:
            d, _sc = _an_sig.supertrend_scored(kl)
            out[sym] = d if d in ("UP", "DOWN") else "NEUTRAL"
        except Exception as e:
            print(f"[Test A6 ST] {sym}: {e}")
            out[sym] = "NEUTRAL"
    return out


def build_supertrend_candidates(kl_1h: dict[str, list], *, max_n: int = 4) -> list[dict]:
    """Analizler A6 Supertrend — BTC/ETH yok, skor sırası, SOL en son, max 4."""
    rows: list[dict] = []
    for sym, kl in kl_1h.items():
        if sym in _ST_EXCLUDE:
            continue
        try:
            d, sc = _an_sig.supertrend_scored(kl)
        except Exception:
            continue
        if d not in ("UP", "DOWN"):
            continue
        rows.append({
            "symbol": sym,
            "side": "LONG" if d == "UP" else "SHORT",
            "signal": d,
            "score": float(sc),
            "interval": "1h",
            "slow": sym in _ST_SLOW,
        })
    fast = [c for c in rows if not c.get("slow")]
    slow = [c for c in rows if c.get("slow")]
    fast.sort(key=lambda x: (-float(x["score"]), x["symbol"]))
    slow.sort(key=lambda x: (-float(x["score"]), x["symbol"]))
    return (fast + slow)[:max_n]


def _source_signal_for_book(book: dict, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    """JARVIS_V1 hariç kaynak defter sinyali."""
    src = book.get("source") or ""
    if src == "islemler_poly":
        return _poly_islemler(book, kl_by_symbol)
    if src == "islemler_a2":
        return _algo_cat.signal_for_book(book, kl_by_symbol)
    if src == "algo1":
        return _algo_cat.signal_for_book(book, kl_by_symbol)
    if src == "analizler":
        key = book.get("source_key") or ""
        if key == "a10":
            return _analiz_a10(kl_by_symbol)
        if key == "a6":
            return _analiz_st(kl_by_symbol)
    return {sym: "NEUTRAL" for sym in kl_by_symbol}


def signal_for_book(book: dict, kl_by_symbol: dict[str, list]) -> dict[str, str]:
    src = book.get("source") or ""
    if src == "jarvis_v1":
        from jarvis_v1 import resolve_signals  # noqa: WPS433

        return resolve_signals(kl_by_symbol, _get_all_books(), _source_signal_for_book)
    if src == "cebu":
        from cebu import resolve_signals as _cebu_resolve  # noqa: WPS433

        return _cebu_resolve(kl_by_symbol, _get_all_books(), _source_signal_for_book)
    return _source_signal_for_book(book, kl_by_symbol)


def _get_all_books() -> list[dict]:
    import importlib.util as _ilu2
    import os as _os

    _cat_path = _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)), "catalog.py",
    )
    _spec2 = _ilu2.spec_from_file_location("kripto_test_catalog_sig", _cat_path)
    _mod = _ilu2.module_from_spec(_spec2)
    assert _spec2.loader is not None
    _spec2.loader.exec_module(_mod)
    return _mod.ALL_BOOKS


def pick_candidates(signals: dict[str, str], *, max_n: int = 6) -> list[dict]:
    return _algo_cat.pick_candidates(signals, max_n=max_n)

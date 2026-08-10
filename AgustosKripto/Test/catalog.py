#!/usr/bin/env python3
"""Test defter kataloğu — algoritma-islemler (26) + /algoritma ALGO1."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
_AGUSTOS = os.path.join(_ROOT, "AgustosKripto")
_ALGO_DIR = os.path.join(_AGUSTOS, "Algoritmalar")
for p in (_POLY, _ALGO_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from algo_signals_v2 import ALGO_V2_META  # noqa: E402

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "agustos_algo_catalog",
    os.path.join(_ALGO_DIR, "catalog.py"),
)
_agc = _ilu.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_agc)
ALGOS_V1 = _agc.ALGOS_V1

# 30 coin — işlem bekleyen tarama evreni (Binance Futures hacmine göre güncel + likit)
TEST_SYMBOLS: list[str] = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT", "ARBUSDT",
    "OPUSDT", "INJUSDT", "TIAUSDT", "FILUSDT", "ATOMUSDT",
    "HYPEUSDT", "ZECUSDT", "KAITOUSDT", "ENAUSDT", "WLDUSDT",
    "TAOUSDT", "ONDOUSDT", "UNIUSDT", "AAVEUSDT", "XLMUSDT",
]

_ISLEMLER_POLY: list[tuple[str, str, str]] = [
    ("analiz1",    "A1",    "1. Analiz · RSI+MACD+EMA"),
    ("analiz2",    "A2",    "2. Analiz · A1 motoru SOL"),
    ("analiz6",    "A6",    "6. Analiz · MACD+RSI"),
    ("analiz6_v2", "A6V2",  "6. Analiz V2 · BTC+ETH"),
    ("analiz6_v3", "A6V3",  "6. Analiz V3 · BTC/ETH A6 · SOL A2"),
    ("analiz15",   "A15",   "15. Analiz · BTC A6 · ETH A8 · SOL A2"),
    ("b1_01",      "B1#01", "B1#01 · en iyi motor"),
    ("b1_02",      "B1#02", "B1#02 · BTC A15 · ETH A6 · SOL A2#01"),
    ("b1_mum",     "B1#03", "B1#03 MUM · Sonnet mum confluence 1h ±15"),
]

_ISLEMLER_A2: list[tuple[str, str, str]] = [
    (f"a2_{n:02d}", f"A2#{n:02d}", f"A2#{n:02d} {name}")
    for n, name, *_ in ALGO_V2_META
]

ALL_BOOKS: list[dict] = []

for key, short, title in _ISLEMLER_POLY:
    ALL_BOOKS.append({
        "uid": key,
        "book_key": f"test_{key}",
        "name": short,
        "title": title,
        "category": "Poly→Kripto Test",
        "source": "islemler_poly",
        "source_key": key,
    })

for key, short, title in _ISLEMLER_A2:
    num = int(key.split("_")[1])
    ALL_BOOKS.append({
        "uid": key,
        "book_key": f"test_{key}",
        "name": short,
        "title": title,
        "category": "Poly→Kripto Test",
        "source": "islemler_a2",
        "source_key": key,
        "id": num,
        "panel": "v2",
    })

for book in ALGOS_V1:
    uid = f"a1_{book['id']:02d}"
    ALL_BOOKS.append({
        "uid": uid,
        "book_key": f"test_{uid}",
        "name": f"A1#{book['id']:02d}",
        "title": book.get("title") or book["name"],
        "category": book.get("category") or "ALGO1",
        "source": "algo1",
        "source_key": uid,
        "id": book["id"],
        "panel": "v1",
        "kind": book.get("kind"),
    })

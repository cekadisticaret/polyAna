"""Forex Algoritma işlemler kataloğu — Poly listesinin XAUUSD kopyası.

CEM01 / Poly trader / Kripto Test dosyalarına dokunmaz.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_POLY = os.path.join(_ROOT, "temmuzPoly")
if _POLY not in sys.path:
    sys.path.insert(0, _POLY)

from algo_signals_v2 import ALGO_V2_META  # noqa: E402

SYMBOL = "XAUUSD"
INIT_BAL = 1000.0
MARGIN = 200.0
LEVERAGE = 100
COMMISSION_SIDE = 0.35
MAX_OPEN = 1

_POLY_BASE: list[tuple[str, str, str]] = [
    ("analiz1", "A1", "1. Analiz · RSI+MACD+EMA"),
    ("analiz2", "A2", "2. Analiz · A1 motoru"),
    ("analiz6", "A6", "6. Analiz · MACD Div"),
    ("analiz6_v2", "A6V2", "6. Analiz V2 · RSI Div"),
    ("analiz6_v3", "A6V3", "6. Analiz V3 · MACD Div"),
    ("melez", "MELEZ", "A2#05 X A6V3 · Mean Rev"),
    ("analiz15", "A15", "15. Analiz"),
    ("b1_01", "B1#01", "B1#01 · XAU en iyi motor"),
    ("b1_02", "B1#02", "B1#02 · A15 / A6 / A2#01"),
    ("b1_mum", "B1#03", "B1#03 MUM"),
    ("b1_04", "B1#04", "B1#04 · küme konsensüsü"),
    ("b1_05", "B1#05", "B1#05 · en iyi motor"),
    ("c101", "C1#01", "C1#01 · PTB vs %50 · 5 puan"),
    ("c101_v2", "C1#01V2", "C1#01 V2 · 3 puan"),
    ("x101", "X1#01", "X1#01 · 13 katman çoğunluk"),
    ("a2_05_v2", "A2#05 V2", "A2#05 + 1,0 ≤ |z| < 1,5"),
]

ALL_BOOKS: list[dict] = []

for key, short, title in _POLY_BASE:
    ALL_BOOKS.append({
        "uid": key,
        "name": short,
        "title": title,
        "source": "poly",
        "source_key": key,
    })

for n, name, cat, kind, _fn in ALGO_V2_META:
    ALL_BOOKS.append({
        "uid": f"a2_{n:02d}",
        "name": f"A2#{n:02d}",
        "title": f"A2#{n:02d} {name}",
        "source": "a2",
        "source_key": f"a2_{n:02d}",
        "id": n,
        "kind": kind,
        "category": cat,
    })

_D_FAMILY: list[tuple[str, str, str]] = [
    ("d101", "D101", "D101 · Trend / momentum · EMA+Donchian+ADX"),
    ("d102", "D102", "D102 · Mean reversion · BB+VWAP-z+RSI · range"),
    ("d103", "D103", "D103 · Volatilite kırılımı · ATR+squeeze+ORB"),
    ("d104", "D104", "D104 · Akış vekili · OBV+profil+MFI+süpürme"),
    ("d105", "D105", "D105 · Kalman + Hurst rejim"),
    ("d106", "D106", "D106 · Çok faktör · D101–D105 ≥3"),
]

for key, short, title in _D_FAMILY:
    ALL_BOOKS.append({
        "uid": key,
        "name": short,
        "title": title,
        "source": "d_family",
        "source_key": key,
    })

BOOKS_BY_UID = {b["uid"]: b for b in ALL_BOOKS}


def get_book(uid: str) -> dict | None:
    return BOOKS_BY_UID.get((uid or "").strip().lower())

#!/usr/bin/env python3
"""Test defter kataloğu — algoritma-islemler + ALGO1 + Analizler A10/ST."""
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

# 28 coin — BTC/ETH yok (2026-08-22); işlem bekleyen tarama evreni
TEST_SYMBOLS: list[str] = [
    "SOLUSDT", "BNBUSDT", "XRPUSDT",
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
    ("melez",      "MELEZ", "A2#05 X A6V3 MELEZ · BTC MACD Div · diğer Mean Rev"),
    ("analiz15",   "A15",   "15. Analiz · BTC A6 · ETH A8 · SOL A2"),
    ("b1_01",      "B1#01", "B1#01 · en iyi motor"),
    ("b1_02",      "B1#02", "B1#02 · BTC A15 · ETH A6 · SOL A2#01"),
    ("b1_mum",     "B1#03", "B1#03 MUM · Sonnet mum confluence 1h ±15 · KAITO pasif"),
    ("b1_04",      "B1#04", "B1#04 · edge-ağırlıklı küme konsensüsü · 23 motor"),
    ("b1_05",      "B1#05", "B1#05 · coin başına en iyi motor · MUM+MELEZ dahil"),
    ("c101",       "C1#01", "C1#01 · PTB+volatilite olasılık modeli · yön = P(UP) vs %50"),
    ("c101_v2",    "C1#01V2", "C1#01 V2 · aynı model, gevşek eşik (3 puan vs 5)"),
]

_ISLEMLER_A2: list[tuple[str, str, str]] = [
    (f"a2_{n:02d}", f"A2#{n:02d}", f"A2#{n:02d} {name}")
    for n, name, *_ in ALGO_V2_META
]

ALL_BOOKS: list[dict] = []

for key, short, title in _ISLEMLER_POLY:
    row = {
        "uid": key,
        "book_key": f"test_{key}",
        "name": short,
        "title": title,
        "category": "Poly→Kripto Test",
        "source": "islemler_poly",
        "source_key": key,
    }
    if key == "b1_mum":
        row["skip_symbols"] = ["KAITOUSDT"]
    ALL_BOOKS.append(row)

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


# Analizler sayfasında olup Test'te karşılığı olmayan motorlar.
# a1/a2 = Test analiz1/analiz2 (aynı predictor). Algoritmalar A1/A2 = a1_*/a2_*.
# A10 Dual ve A6 Supertrend başka sinyal — eklenmezse kaybolur.
ALL_BOOKS.append({
    "uid": "analiz10",
    "book_key": "test_analiz10",
    "name": "A10",
    "title": "10. Analiz Dual · Poly dual core",
    "category": "Analizler→Kripto Test",
    "source": "analizler",
    "source_key": "a10",
})
ALL_BOOKS.append({
    "uid": "analiz_st",
    "book_key": "test_analiz_st",
    "name": "A6 ST",
    "title": "Analizler Supertrend · alt (BTC/ETH yok) · skor seçimi · max 4",
    "category": "Analizler→Kripto Test",
    "source": "analizler",
    "source_key": "a6",
    "max_opens": 4,
})


# ── PRO defterleri ───────────────────────────────────────────
# Dashboard "Algoritma Durumu" en iyi 4'ü (A2#05 · A6V3 · B1#03 MUM · MELEZ)
# aynı sinyallerle ama kripto'ya uygun çıkış rejimiyle: saatlik zorunlu kapanış
# yok, pozisyon sinyal dönene / ATR stopa / süre sınırına kadar tutulur ve
# `edge_gate` ölçülen kenarı komisyonu aşmayan (defter, coin) çiftini hiç
# açmaz. Orijinal defterler dokunulmaz — ikisi yan yana birikip farkı gösterir.
PRO_SOURCE_UIDS = ["a2_05", "analiz6_v3", "b1_mum", "melez"]

_by_uid = {b["uid"]: b for b in ALL_BOOKS}
for _uid in PRO_SOURCE_UIDS:
    _base = _by_uid.get(_uid)
    if not _base:
        continue
    ALL_BOOKS.append({
        **_base,
        "uid": f"pro_{_uid}",
        "book_key": f"test_pro_{_uid}",
        "name": f"{_base['name']} PRO",
        "title": f"{_base.get('title') or _base['name']} · kenar kapılı, saatlik kapanış yok",
        "category": "Poly→Kripto PRO",
        "mode": "pro",
        "pro_of": _uid,
    })

# ── JARVIS V1 ────────────────────────────────────────────────
# Lider Analizi'nden coin→en iyi motor; ARB→A1#33, OP→B1#03 sabit pin.
ALL_BOOKS.append({
    "uid": "jarvis_v1",
    "book_key": "test_jarvis_v1",
    "name": "JARVIS_V1",
    "title": "JARVIS V1 · lider analiz motor seçimi · ARB→A1#33 · OP→B1#03 · max 10",
    "category": "Poly→Kripto JARVIS",
    "source": "jarvis_v1",
    "source_key": "jarvis_v1",
    "max_opens": 10,
})

# ── CEBU ─────────────────────────────────────────────────────
# Sabit coin→motor; kota yok (18 aktif coin). BTC/ETH/KAITO/HYPE pasif.
ALL_BOOKS.append({
    "uid": "cebu",
    "book_key": "test_cebu",
    "name": "CEBU",
    "title": "CEBU · sabit coin→motor · sinyal gelince aç · max 18 · BTC/ETH/KAITO/HYPE pasif · 24s · 3×ATR · ATR kilit",
    "category": "Poly→Kripto CEBU",
    "source": "cebu",
    "source_key": "cebu",
    "max_opens": 18,
})

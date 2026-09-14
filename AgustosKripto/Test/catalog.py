#!/usr/bin/env python3
"""Test defter kataloğu — algoritma-islemler + ALGO1 + Analizler A10/ST."""
from __future__ import annotations

import json
import os
import sys
import time

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

_UNIVERSE_FILE = os.path.join(os.path.dirname(__file__), "um_universe.txt")
_MOVERS_FILE = os.path.join(os.path.dirname(__file__), "data", "day_movers.json")
_MOVERS_MAX_AGE = float(os.environ.get("TEST_MOVERS_MAX_AGE", str(90 * 60)))
_SCAN_N = int(os.environ.get("TEST_SCAN_N", "60"))
_SCAN_FALLBACK = [
    "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT",
    "DOTUSDT", "LTCUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT", "ARBUSDT",
    "OPUSDT", "INJUSDT", "TIAUSDT", "FILUSDT", "ATOMUSDT", "HYPEUSDT",
    "ZECUSDT", "KAITOUSDT", "ENAUSDT", "WLDUSDT", "TAOUSDT", "ONDOUSDT",
    "UNIUSDT", "AAVEUSDT", "XLMUSDT", "CRVUSDT", "SEIUSDT", "NEARUSDT",
]


def _load_universe() -> list[str]:
    try:
        with open(_UNIVERSE_FILE) as f:
            raw = f.read()
    except OSError:
        raw = ""
    out: list[str] = []
    seen: set[str] = set()
    for tok in raw.replace(",", " ").split():
        base = tok.strip().upper()
        if not base or base.startswith("#"):
            continue
        if base.endswith("USDT"):
            sym = base
        else:
            sym = base + "USDT"
        if sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


TEST_UNIVERSE: list[str] = _load_universe()


def _marks_rows() -> dict:
    try:
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        from binance_fapi_guard import _load_marks  # noqa: WPS433
        rows = (_load_marks().get("rows") or {})
        return rows if isinstance(rows, dict) else {}
    except Exception:
        return {}


def _is_active(sym: str, marks: dict, last: float = 0.0) -> bool:
    """Futures’ta kotasyon veya 24s last varsa aktif."""
    if last > 0:
        return True
    row = marks.get(sym) if marks else None
    if not isinstance(row, dict):
        return False
    try:
        return float(row.get("mark") or row.get("last") or 0) > 0
    except (TypeError, ValueError):
        return False


def _movers_scan(cap: int, allow: set[str], marks: dict) -> list[str]:
    """*/30 day_movers — 24s artan+azalan, yalnız aktif."""
    try:
        age = time.time() - os.path.getmtime(_MOVERS_FILE)
        if age > _MOVERS_MAX_AGE:
            return []
        with open(_MOVERS_FILE) as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    last_by: dict[str, float] = {}
    rows = list(data.get("up") or []) + list(data.get("down") or [])
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            last_by[str(r.get("symbol") or "").upper()] = float(r.get("last") or 0)
        except (TypeError, ValueError):
            pass
    ordered: list[str] = []
    for s in data.get("scan") or []:
        if isinstance(s, str) and s not in ordered:
            ordered.append(s.upper())
    if not ordered:
        rows.sort(key=lambda r: abs(float(r.get("pct") or 0)), reverse=True)
        for r in rows:
            if isinstance(r, dict):
                ordered.append(str(r.get("symbol") or "").upper())
    out: list[str] = []
    for sym in ordered:
        if not sym or sym not in allow or sym in out:
            continue
        if not _is_active(sym, marks, last_by.get(sym, 0.0)):
            continue
        out.append(sym)
        if len(out) >= cap:
            break
    return out


def scan_symbols(n: int | None = None) -> list[str]:
    """Yeni açık / sinyal taraması — 24s hareket (aktif), tavan TEST_SCAN_N.

    Kaynak: `day_movers.json` (*/30). Dosya yok/bayatsa hacim yedeği.
    """
    cap = _SCAN_N if n is None else int(n)
    allow = set(TEST_UNIVERSE)
    marks = _marks_rows()
    movers = _movers_scan(cap, allow, marks)
    if len(movers) >= 10:
        return movers
    scored: list[tuple[float, str]] = []
    for sym in TEST_UNIVERSE:
        row = marks.get(sym)
        if not isinstance(row, dict):
            continue
        try:
            qv = float(row.get("quote_vol") or 0)
        except (TypeError, ValueError):
            qv = 0.0
        if qv > 0:
            scored.append((qv, sym))
    scored.sort(reverse=True)
    top = [s for _qv, s in scored[:cap]]
    if len(top) >= max(8, cap // 2):
        return top
    have_px = []
    for sym in TEST_UNIVERSE:
        row = marks.get(sym)
        if isinstance(row, dict) and (row.get("mark") or row.get("last")):
            have_px.append(sym)
    mixed: list[str] = []
    for s in _SCAN_FALLBACK + have_px:
        if s in allow and s not in mixed:
            mixed.append(s)
        if len(mixed) >= cap:
            break
    return mixed or list(TEST_UNIVERSE[:cap])


# Canlı tarama evreni (hacim dilimi). Tam liste: TEST_UNIVERSE.
TEST_SYMBOLS: list[str] = scan_symbols()

_ISLEMLER_POLY: list[tuple[str, str, str]] = [
    ("analiz1",    "F16",   "F16 · RSI+MACD+EMA"),
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
    "title": "Analizler Supertrend · alt (BTC/ETH yok) · skor seçimi · max 8",
    "category": "Analizler→Kripto Test",
    "source": "analizler",
    "source_key": "a6",
    "max_opens": 8,
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
# Lider Analiz 1. sıra; eşzamanlı max 8. BTC/ETH/KAITO/HYPE pasif.
ALL_BOOKS.append({
    "uid": "cebu",
    "book_key": "test_cebu",
    "name": "CEBU",
    "title": "CEBU · Lider Analiz 1. sıra · sinyal gelince aç · max 8 · BTC/ETH/KAITO/HYPE pasif · 24s · 3×ATR · ATR kilit",
    "category": "Poly→Kripto CEBU",
    "source": "cebu",
    "source_key": "cebu",
    "max_opens": 8,
})

# /kripto/test — 2026-09-04: bakiye < $1005 olanlar ekranda yok, cron açmaz.
_KEEP_UIDS = {
    "melez", "analiz10",
    "a2_01", "a2_02", "a2_04", "a2_06", "a2_07", "a2_10", "a2_14",
    "a1_03", "a1_07", "a1_11", "a1_16", "a1_33",
}
ALL_BOOKS[:] = [b for b in ALL_BOOKS if b.get("uid") in _KEEP_UIDS]

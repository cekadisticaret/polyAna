#!/usr/bin/env python3
"""CEBU — coin başına sabit motor. Sinyal gelince açar; 4-slot kotası yok.

Çıkış Test runner politikası: ATR kâr kilidi · 24s tavan · 3×ATR zarar.
Saatlik 1s/4s settle yok. DOGE/XLM JARVIS_V1 eşlemesini o anki motora çözer.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

CEBU_UID = "cebu"
# BTC / ETH / KAITO / HYPE pasif — eşlemede durur, sinyal/açılış yok.
DISABLED_SYMBOLS = frozenset({"BTC", "ETH", "KAITO", "HYPE"})
# Aktif eşlenen her coin aynı anda açık kalabilir — kota yok, sinyal = aday.
MAX_OPENS = 18

# USDT'siz sembol → Test defter uid. JARVIS_V1 runtime'da çözülür.
MAPPING: dict[str, str] = {
    "BTC": "a1_32",
    "ETH": "a1_20",
    "SOL": "a1_08",
    "XRP": "b1_mum",
    "DOGE": "jarvis_v1",
    "ADA": "a1_09",
    "LINK": "pro_b1_mum",
    "DOT": "a1_19",
    "SUI": "a1_31",
    "APT": "a1_33",
    "ARB": "a1_25",
    "OP": "a1_30",
    "INJ": "a1_34",
    "TIA": "a1_32",
    "FIL": "b1_mum",
    "HYPE": "analiz6",
    "KAITO": "a1_36",
    "ENA": "a1_28",
    "WLD": "a2_01",
    "UNI": "a1_10",
    "AAVE": "a1_10",
    "XLM": "jarvis_v1",
}

def _base(sym: str) -> str:
    return (sym or "").upper().replace("USDT", "")


def is_disabled(sym: str) -> bool:
    return _base(sym) in DISABLED_SYMBOLS


CEBU_SYMBOLS: list[str] = [
    f"{base}USDT" for base in MAPPING if base not in DISABLED_SYMBOLS
]
_META_UIDS = frozenset({CEBU_UID, "jarvis_v1"})


def is_cebu_book(book: dict) -> bool:
    return (book.get("uid") or "") == CEBU_UID or (book.get("source") or "") == "cebu"


def max_opens() -> int:
    return MAX_OPENS


def _load_runner():
    import importlib.util as _ilu

    path = os.path.join(_DIR, "runner.py")
    spec = _ilu.spec_from_file_location("kripto_test_runner_cebu", path)
    mod = _ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _jarvis_mapping() -> dict[str, str]:
    from jarvis_v1 import build_mapping  # noqa: WPS433

    return build_mapping()


def disabled_open_symbols(opens: list | None) -> set[str]:
    """Pasif coinlerde hâlâ açık kalan sanal pozisyonlar — kapatılacak."""
    out: set[str] = set()
    for pos in opens or []:
        sym = (pos.get("symbol") or "").upper()
        if sym and is_disabled(sym):
            out.add(sym)
    return out


def resolve_motor_uid(base: str) -> str | None:
    """Pin → gerçek motor uid. JARVIS_V1 pinleri lider eşlemesine açılır."""
    key = _base(base)
    if key in DISABLED_SYMBOLS:
        return None
    uid = MAPPING.get(key)
    if not uid:
        return None
    if uid == "jarvis_v1":
        resolved = _jarvis_mapping().get(key)
        if not resolved or resolved in _META_UIDS:
            return None
        return resolved
    return uid


def _label_for(uid: str, book_by_uid: dict[str, dict]) -> str:
    book = book_by_uid.get(uid) or {}
    return book.get("name") or uid


def resolve_signals(
    kl_by_symbol: dict[str, list],
    all_books: list[dict],
    signal_fn: Callable[[dict, dict[str, list]], dict[str, str]],
) -> dict[str, str]:
    """Yalnız eşlenen coinlerde kaynak motorun sinyalini birleştir."""
    book_by_uid = {b["uid"]: b for b in all_books}
    by_uid: dict[str, list[str]] = {}
    for sym in kl_by_symbol:
        base = _base(sym)
        if base not in MAPPING or base in DISABLED_SYMBOLS:
            continue
        uid = resolve_motor_uid(base)
        if uid and uid in book_by_uid:
            by_uid.setdefault(uid, []).append(sym)

    out = {sym: "NEUTRAL" for sym in kl_by_symbol}
    for uid, syms in by_uid.items():
        src = book_by_uid[uid]
        sub = {s: kl_by_symbol[s] for s in syms if s in kl_by_symbol}
        if not sub:
            continue
        try:
            sigs = signal_fn(src, sub)
        except Exception as e:
            print(f"[CEBU] {uid}: {e}")
            continue
        for s, d in sigs.items():
            if d in ("UP", "DOWN"):
                out[s] = d
    return out


def mapping_display_rows() -> list[dict]:
    r = _load_runner()
    book_by_uid = {b["uid"]: b for b in r.ALL_BOOKS}
    jmap = _jarvis_mapping()
    rows: list[dict] = []
    for base, pin in MAPPING.items():
        off = base in DISABLED_SYMBOLS
        resolved = None if off else resolve_motor_uid(base)
        pin_name = _label_for(pin, book_by_uid) if pin != "jarvis_v1" else "JARVIS_V1"
        rows.append({
            "symbol": base,
            "pin_uid": pin,
            "pin_name": pin_name,
            "uid": resolved,
            "algo": "PASİF" if off else (_label_for(resolved, book_by_uid) if resolved else pin_name),
            "disabled": off,
            "jarvis_live": (not off) and pin == "jarvis_v1",
            "jarvis_src": jmap.get(base) if (not off and pin == "jarvis_v1") else None,
        })
    return rows


def mapping_summary() -> dict:
    return {
        "uid": CEBU_UID,
        "max_opens": MAX_OPENS,
        "mapped_coins": len(MAPPING) - len(DISABLED_SYMBOLS),
        "disabled": sorted(DISABLED_SYMBOLS),
        "mapping": {k: v for k, v in MAPPING.items() if k not in DISABLED_SYMBOLS},
        "rows": mapping_display_rows(),
    }


def build_cebu_candidates(
    book: dict,
    kl_1h: dict[str, list],
    kl_4h: dict[str, list],
    history: list,
    *,
    symbols: list[str],
    signal_for_book,
) -> list[dict]:
    """Kaynak defterin 1h/4h seçimi + sinyali — CEBU kendi geçmişine bakmaz."""
    from engine import MIN_TF_TRADES, _tf_score, _tf_stats, choose_timeframe

    r = _load_runner()
    book_by_uid = {b["uid"]: b for b in r.ALL_BOOKS}
    sig1_cache: dict[str, dict[str, str]] = {}
    sig4_cache: dict[str, dict[str, str]] = {}
    hist_cache: dict[str, list] = {}
    rows: list[dict] = []

    want = [s for s in symbols if _base(s) in MAPPING and _base(s) not in DISABLED_SYMBOLS]
    for sym in want:
        base = _base(sym)
        src_uid = resolve_motor_uid(base)
        if not src_uid:
            continue
        src_book = book_by_uid.get(src_uid)
        if not src_book:
            continue

        if src_uid not in sig1_cache:
            sig1_cache[src_uid] = signal_for_book(src_book, kl_1h)
            sig4_cache[src_uid] = signal_for_book(src_book, kl_4h)

        if src_uid not in hist_cache:
            hp = r._history_path_for_book(src_book)
            try:
                hist = r.load_history(hp) if hp else []
            except Exception:
                hist = []
            if not hist and src_book.get("pro_of"):
                base_book = book_by_uid.get(src_book["pro_of"])
                if base_book:
                    hp2 = r._history_path_for_book(base_book)
                    try:
                        hist = r.load_history(hp2) if hp2 else []
                    except Exception:
                        hist = []
            hist_cache[src_uid] = hist

        src_hist = hist_cache[src_uid]
        tf, sig = choose_timeframe(
            sym,
            sig1_cache[src_uid].get(sym, "NEUTRAL"),
            sig4_cache[src_uid].get(sym, "NEUTRAL"),
            src_hist,
        )
        if sig not in ("UP", "DOWN"):
            continue
        wr, pnl, n = _tf_stats(src_hist, sym, tf)
        score = _tf_score(wr, pnl, n) if n >= MIN_TF_TRADES else 50.0
        pin = MAPPING.get(base) or src_uid
        rows.append({
            "symbol": sym,
            "side": "LONG" if sig == "UP" else "SHORT",
            "signal": sig,
            "score": round(score, 2),
            "interval": tf,
            "cebu_src": src_uid,
            "cebu_src_name": src_book.get("name") or src_uid,
            "cebu_pin": pin,
        })

    rows.sort(key=lambda x: (-x["score"], x["symbol"]))
    return rows

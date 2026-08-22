#!/usr/bin/env python3
"""JARVIS_V1 — coin başına lider analiz motoru seçimi.

Lider Analizi (/kripto/lider-analiz) ile **aynı modül** (`leader_mapping.py`):
PnL → WR → işlem sayısı. Tablo değişince bir sonraki open/scan turunda eşleme
yenilenir (geçmiş dosyası mtime izlenir). Sabit pinler:
  ARB → A1#33 (a1_33)
  OP  → B1#03 MUM (b1_mum)
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

from leader_mapping import MIN_TRADES, build_jarvis_coin_mapping

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
MAPPING_FILE = os.path.join(DATA, "jarvis_v1_mapping.json")

JARVIS_UID = "jarvis_v1"
MAX_OPENS = 10

PINNED: dict[str, str] = {
    "ARB": "a1_33",
    "OP": "b1_mum",
}

_cache: dict = {"fp": 0.0, "map": {}, "meta": {}}


def is_jarvis_book(book: dict) -> bool:
    return (book.get("uid") or "") == JARVIS_UID or (book.get("source") or "") == "jarvis_v1"


def max_opens() -> int:
    return MAX_OPENS


def _load_runner():
    import importlib.util as _ilu

    path = os.path.join(_DIR, "runner.py")
    spec = _ilu.spec_from_file_location("kripto_test_runner_jv1", path)
    mod = _ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _history_path_for_book(book: dict, runner_mod) -> str | None:
    return runner_mod._history_path_for_book(book)


def _history_fingerprint(runner_mod) -> float:
    """Herhangi bir defter geçmişi değişince eşleme yenilensin."""
    latest = 0.0
    for book in runner_mod.ALL_BOOKS:
        uid = book.get("uid") or ""
        if uid in (JARVIS_UID, "cebu"):
            continue
        hp = _history_path_for_book(book, runner_mod)
        if hp and os.path.isfile(hp):
            latest = max(latest, os.path.getmtime(hp))
    return latest


def build_mapping(*, force: bool = False) -> dict[str, str]:
    """USDT'siz sembol → kaynak defter uid (lider analiz 1. sıra + pinler)."""
    r = _load_runner()
    fp = _history_fingerprint(r)
    if not force and _cache["map"] and _cache.get("fp") == fp:
        return dict(_cache["map"])

    mapping, meta, _rows = build_jarvis_coin_mapping(
        r.ALL_BOOKS,
        r.TEST_SYMBOLS,
        PINNED,
        history_path_for_book=lambda b: _history_path_for_book(b, r),
        load_history=r.load_history,
    )
    meta = {
        **meta,
        "updated_at_tr": r.now_tr(),
        "pinned": PINNED,
        "min_trades": MIN_TRADES,
        "history_fingerprint": fp,
    }
    _cache["fp"] = fp
    _cache["map"] = mapping
    _cache["meta"] = meta
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump({"mapping": mapping, **meta}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return dict(mapping)


def resolve_signals(
    kl_by_symbol: dict[str, list],
    all_books: list[dict],
    signal_fn: Callable[[dict, dict[str, list]], dict[str, str]],
) -> dict[str, str]:
    """Her coin için seçilen motorun sinyalini birleştir."""
    mapping = build_mapping()
    book_by_uid = {b["uid"]: b for b in all_books}
    by_uid: dict[str, list[str]] = {}
    for sym in kl_by_symbol:
        base = sym.upper().replace("USDT", "")
        uid = mapping.get(base)
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
            print(f"[JARVIS_V1] {uid}: {e}")
            continue
        for s, d in sigs.items():
            if d in ("UP", "DOWN"):
                out[s] = d
    return out


def mapping_summary() -> dict:
    build_mapping()
    return {
        "uid": JARVIS_UID,
        "max_opens": MAX_OPENS,
        "min_trades": MIN_TRADES,
        "pinned": dict(PINNED),
        "mapping": dict(_cache.get("map") or {}),
        "labels": dict((_cache.get("meta") or {}).get("labels") or {}),
        "mapped_coins": len(_cache.get("map") or {}),
    }


def mapping_display_rows() -> list[dict]:
    """Dashboard — coin başına seçilen motor + PnL/WR."""
    build_mapping()
    meta = _cache.get("meta") or {}
    labels = meta.get("labels") or {}
    stats = meta.get("coin_stats") or {}
    rows: list[dict] = []
    for sym in meta.get("symbols") or []:
        st = stats.get(sym)
        if not st:
            continue
        uid = st.get("uid") or (_cache.get("map") or {}).get(sym)
        rows.append({
            "symbol": sym,
            "algo": labels.get(sym) or uid or "—",
            "uid": uid,
            "pnl": st.get("pnl"),
            "trades": st.get("trades"),
            "wr": st.get("wr"),
            "pinned": bool(st.get("pinned")),
        })
    rows.sort(key=lambda x: (-float(x.get("pnl") or 0), x["symbol"]))
    return rows


def build_jarvis_candidates(
    book: dict,
    kl_1h: dict[str, list],
    kl_4h: dict[str, list],
    history: list,
    *,
    symbols: list[str],
    signal_for_book,
) -> list[dict]:
    """Kaynak defterin 1h/4h seçimi + sinyali — JARVIS kendi geçmişine bakmaz."""
    from engine import MIN_TF_TRADES, _tf_score, _tf_stats, choose_timeframe

    r = _load_runner()
    mapping = build_mapping()
    book_by_uid = {b["uid"]: b for b in r.ALL_BOOKS}
    sig1_cache: dict[str, dict[str, str]] = {}
    sig4_cache: dict[str, dict[str, str]] = {}
    hist_cache: dict[str, list] = {}
    rows: list[dict] = []

    for sym in symbols:
        base = sym.upper().replace("USDT", "")
        src_uid = mapping.get(base)
        if not src_uid:
            continue
        src_book = book_by_uid.get(src_uid)
        if not src_book:
            continue

        if src_uid not in sig1_cache:
            sig1_cache[src_uid] = signal_for_book(src_book, kl_1h)
            sig4_cache[src_uid] = signal_for_book(src_book, kl_4h)

        if src_uid not in hist_cache:
            hp = _history_path_for_book(src_book, r)
            try:
                hist_cache[src_uid] = r.load_history(hp) if hp else []
            except Exception:
                hist_cache[src_uid] = []

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
        rows.append({
            "symbol": sym,
            "side": "LONG" if sig == "UP" else "SHORT",
            "signal": sig,
            "score": round(score, 2),
            "interval": tf,
            "jarvis_src": src_uid,
            "jarvis_src_name": src_book.get("name") or src_uid,
        })

    rows.sort(key=lambda x: (-x["score"], x["symbol"]))
    return rows

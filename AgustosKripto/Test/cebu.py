#!/usr/bin/env python3
"""CEBU — Lider Analiz 1. sıra motor. Sinyal gelince açar; max 8 eşzamanlı.

`/kripto/lider-analiz` ile aynı kural (`leader_mapping`): coin bazında
PnL → WR → işlem. Evren day_movers aktif 60. Pin yok.
BTC / ETH / KAITO / HYPE pasif. Çıkış: ATR kilit · 24s · 3×ATR.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Callable

from leader_mapping import MIN_TRADES, build_jarvis_coin_mapping

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

DATA = os.path.join(_DIR, "data")
MAPPING_FILE = os.path.join(DATA, "cebu_mapping.json")

CEBU_UID = "cebu"
DISABLED_SYMBOLS = frozenset({"BTC", "ETH", "KAITO", "HYPE"})
MAX_OPENS = 8
_META_UIDS = frozenset({CEBU_UID, "jarvis_v1"})

_cache: dict = {"fp": None, "map": {}, "meta": {}}


def _base(sym: str) -> str:
    return (sym or "").upper().replace("USDT", "")


def is_disabled(sym: str) -> bool:
    return _base(sym) in DISABLED_SYMBOLS


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


def _fingerprint(runner_mod) -> float:
    latest = 0.0
    movers = os.path.join(_DIR, "data", "day_movers.json")
    if os.path.isfile(movers):
        latest = os.path.getmtime(movers)
    for book in runner_mod.ALL_BOOKS:
        uid = book.get("uid") or ""
        if uid in _META_UIDS:
            continue
        hp = runner_mod._history_path_for_book(book)
        if hp and os.path.isfile(hp):
            latest = max(latest, os.path.getmtime(hp))
    return latest


def build_mapping(*, force: bool = False) -> dict[str, str]:
    """USDT'siz sembol → Lider Analiz 1. sıra uid. Pin yok."""
    r = _load_runner()
    fp = _fingerprint(r)
    if not force and _cache["map"] and _cache.get("fp") == fp:
        return dict(_cache["map"])

    symbols = list(r.scan_symbols())
    mapping, meta, _rows = build_jarvis_coin_mapping(
        r.ALL_BOOKS,
        symbols,
        {},
        history_path_for_book=r._history_path_for_book,
        load_history=r.load_history,
    )
    mapping = {
        k: v for k, v in mapping.items()
        if k not in DISABLED_SYMBOLS and v not in _META_UIDS
    }
    meta = {
        **meta,
        "updated_at_tr": str(r.now_tr()),
        "min_trades": MIN_TRADES,
        "source": "lider_analiz",
        "history_fingerprint": fp,
        "disabled": sorted(DISABLED_SYMBOLS),
    }
    meta["labels"] = {k: v for k, v in (meta.get("labels") or {}).items() if k in mapping}
    meta["coin_stats"] = {k: v for k, v in (meta.get("coin_stats") or {}).items() if k in mapping}
    meta["symbols"] = [s.replace("USDT", "") for s in symbols if _base(s) not in DISABLED_SYMBOLS]
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


def cebu_symbols() -> list[str]:
    """Açık aday evreni — lideri olan aktif coinler."""
    return [f"{base}USDT" for base in build_mapping()]


# Eski import adı — her çağrıda taze liste için cebu_symbols() kullan.
CEBU_SYMBOLS = []


def resolve_motor_uid(base: str) -> str | None:
    key = _base(base)
    if key in DISABLED_SYMBOLS:
        return None
    uid = build_mapping().get(key)
    if not uid or uid in _META_UIDS:
        return None
    return uid


def disabled_open_symbols(opens: list | None) -> set[str]:
    out: set[str] = set()
    for pos in opens or []:
        sym = (pos.get("symbol") or "").upper()
        if sym and is_disabled(sym):
            out.add(sym)
    return out


def _label_for(uid: str, book_by_uid: dict[str, dict]) -> str:
    book = book_by_uid.get(uid) or {}
    return book.get("name") or uid


def resolve_signals(
    kl_by_symbol: dict[str, list],
    all_books: list[dict],
    signal_fn: Callable[[dict, dict[str, list]], dict[str, str]],
) -> dict[str, str]:
    mapping = build_mapping()
    book_by_uid = {b["uid"]: b for b in all_books}
    by_uid: dict[str, list[str]] = {}
    for sym in kl_by_symbol:
        base = _base(sym)
        if base in DISABLED_SYMBOLS:
            continue
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
            print(f"[CEBU] {uid}: {e}")
            continue
        for s, d in sigs.items():
            if d in ("UP", "DOWN"):
                out[s] = d
    return out


def mapping_display_rows() -> list[dict]:
    mapping = build_mapping()
    meta = _cache.get("meta") or {}
    labels = meta.get("labels") or {}
    stats = meta.get("coin_stats") or {}
    r = _load_runner()
    book_by_uid = {b["uid"]: b for b in r.ALL_BOOKS}
    rows: list[dict] = []
    for base in meta.get("symbols") or list(mapping):
        off = base in DISABLED_SYMBOLS
        uid = None if off else mapping.get(base)
        st = stats.get(base) or {}
        name = "PASİF" if off else (labels.get(base) or _label_for(uid or "", book_by_uid) or "—")
        rows.append({
            "symbol": base,
            "pin_uid": uid,
            "pin_name": name,
            "uid": uid,
            "algo": name,
            "disabled": off,
            "jarvis_live": False,
            "jarvis_src": None,
            "pnl": st.get("pnl"),
            "wr": st.get("wr"),
            "trades": st.get("trades") or st.get("total"),
        })
    rows.sort(key=lambda x: (
        0 if x.get("uid") else 1,
        -float(x.get("pnl") or 0),
        x["symbol"],
    ))
    return rows


def mapping_summary() -> dict:
    mapping = build_mapping()
    meta = _cache.get("meta") or {}
    return {
        "uid": CEBU_UID,
        "max_opens": MAX_OPENS,
        "mapped_coins": len(mapping),
        "disabled": sorted(DISABLED_SYMBOLS),
        "source": "lider_analiz",
        "min_trades": MIN_TRADES,
        "mapping": dict(mapping),
        "rows": mapping_display_rows(),
        "updated_at_tr": meta.get("updated_at_tr"),
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
    mapping = build_mapping()
    book_by_uid = {b["uid"]: b for b in r.ALL_BOOKS}
    sig1_cache: dict[str, dict[str, str]] = {}
    sig4_cache: dict[str, dict[str, str]] = {}
    hist_cache: dict[str, list] = {}
    rows: list[dict] = []

    want = symbols or cebu_symbols()
    for sym in want:
        base = _base(sym)
        if base in DISABLED_SYMBOLS:
            continue
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
        rows.append({
            "symbol": sym,
            "side": "LONG" if sig == "UP" else "SHORT",
            "signal": sig,
            "score": round(score, 2),
            "interval": tf,
            "cebu_src": src_uid,
            "cebu_src_name": src_book.get("name") or src_uid,
            "cebu_pin": src_uid,
        })

    rows.sort(key=lambda x: (-x["score"], x["symbol"]))
    return rows

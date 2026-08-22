#!/usr/bin/env python3
"""Lider Analiz (/kripto/lider-analiz) ile JARVIS_V1 ortak coin→motor seçimi.

Tek sıralama kuralı: sembol bazında PnL → WR → işlem sayısı (yüksekten düşüğe).
"""
from __future__ import annotations

from typing import Callable

MIN_TRADES = 5


def build_leader_rows(
    books: list[dict],
    *,
    test_symbols: list[str],
    history_path_for_book: Callable[[dict], str | None],
    load_history: Callable[[str], list],
    exclude_uids: tuple[str, ...] | frozenset[str] = (),
) -> list[dict]:
    """Kripto Test defterleri — genel + sembol bazlı WR/PnL (lider analiz API)."""
    skip = set(exclude_uids or ())
    allowed_syms = {s.replace("USDT", "") for s in test_symbols}
    rows: list[dict] = []
    for book in books:
        uid = book.get("uid") or ""
        if uid in skip:
            continue
        hp = history_path_for_book(book)
        if not hp:
            continue
        try:
            hist = load_history(hp)
        except Exception:
            continue
        resolved = [t for t in hist if t.get("win") is not None]
        if len(resolved) < MIN_TRADES:
            continue
        wins = sum(1 for t in resolved if t.get("win"))
        wr = round(100.0 * wins / len(resolved), 1)
        pnl = round(sum(float(t.get("pnl") or 0) for t in resolved), 2)
        sym_map: dict[str, dict] = {}
        for t in resolved:
            sym = (t.get("symbol") or "").upper().replace("USDT", "")
            if sym not in allowed_syms:
                continue
            if sym not in sym_map:
                sym_map[sym] = {"w": 0, "t": 0, "pnl": 0.0}
            sym_map[sym]["t"] += 1
            if t.get("win"):
                sym_map[sym]["w"] += 1
            sym_map[sym]["pnl"] += float(t.get("pnl") or 0)
        sym_stats = {
            sym: {
                "wr": round(v["w"] / v["t"] * 100, 1),
                "total": v["t"],
                "pnl": round(v["pnl"], 2),
            }
            for sym, v in sym_map.items()
            if v["t"] >= MIN_TRADES
        }
        rows.append({
            "key": uid,
            "short": book.get("name") or uid,
            "wr": wr,
            "total": len(resolved),
            "pnl": pnl,
            "sym_stats": sym_stats,
        })
    return rows


def leader_board(
    rows: list[dict],
    *,
    sym: str | None = None,
    limit: int = 8,
) -> list[dict]:
    if sym:
        picked: list[dict] = []
        for row in rows:
            st = row.get("sym_stats", {}).get(sym)
            if not st:
                continue
            picked.append({
                "key": row["key"],
                "label": row["short"],
                "wr": st["wr"],
                "total": st["total"],
                "pnl": st["pnl"],
            })
        picked.sort(key=lambda x: (x["pnl"], x["wr"], x["total"]), reverse=True)
        return picked[:limit]
    overall = [{
        "key": r["key"],
        "label": r["short"],
        "wr": r["wr"],
        "total": r["total"],
        "pnl": r["pnl"],
    } for r in rows]
    overall.sort(key=lambda x: (x["pnl"], x["wr"], x["total"]), reverse=True)
    return overall[:limit]


def pick_leader_for_symbol(rows: list[dict], sym: str) -> dict | None:
    """Lider analiz kartının 1. sırası — aynı kural."""
    board = leader_board(rows, sym=sym, limit=1)
    return board[0] if board else None


def _stats_for_uid(rows: list[dict], sym: str, uid: str) -> dict | None:
    for row in rows:
        if row.get("key") != uid:
            continue
        st = row.get("sym_stats", {}).get(sym)
        if not st:
            return None
        return {
            "uid": uid,
            "pnl": st["pnl"],
            "trades": st["total"],
            "wr": st["wr"],
        }
    return None


def build_jarvis_coin_mapping(
    books: list[dict],
    test_symbols: list[str],
    pins: dict[str, str],
    *,
    history_path_for_book: Callable[[dict], str | None],
    load_history: Callable[[str], list],
) -> tuple[dict[str, str], dict[str, dict], list[dict]]:
    """JARVIS_V1 eşlemesi — lider tablosu + pin override (yalnız kendini hariç tutar)."""
    rows = build_leader_rows(
        books,
        test_symbols=test_symbols,
        history_path_for_book=history_path_for_book,
        load_history=load_history,
        exclude_uids=("jarvis_v1", "cebu"),
    )
    book_by_uid = {b["uid"]: b for b in books}
    mapping: dict[str, str] = {}
    coin_stats: dict[str, dict] = {}
    symbols = [s.replace("USDT", "") for s in test_symbols]

    for sym in symbols:
        if sym in pins:
            uid = pins[sym]
            mapping[sym] = uid
            st = _stats_for_uid(rows, sym, uid) or {"uid": uid}
            st["pinned"] = True
            coin_stats[sym] = st
            continue
        top = pick_leader_for_symbol(rows, sym)
        if not top:
            continue
        uid = top["key"]
        mapping[sym] = uid
        coin_stats[sym] = {
            "uid": uid,
            "pnl": top["pnl"],
            "trades": top["total"],
            "wr": top["wr"],
            "pinned": False,
        }

    labels = {
        sym: (book_by_uid.get(uid) or {}).get("name") or uid
        for sym, uid in mapping.items()
    }
    meta = {
        "mapped": len(mapping),
        "symbols": symbols,
        "labels": labels,
        "coin_stats": coin_stats,
        "leader_rows_n": len(rows),
    }
    return mapping, meta, rows

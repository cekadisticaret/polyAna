#!/usr/bin/env python3
"""Algoritmalar — ALGO2 Top-17 + ALGO1 (Poly) sanal futures.

Tüm 17 defter sanalda $30×10x işlem açar (komisyon dahil net PnL).
4 defter (A2#05/#06/#07 + A1#11) ayrıca gerçek Binance işlemi de açar
(crypto_futures_cr6.py → Algoritmalar Live, $7×20x) — sanal defterleri
bundan bağımsız kendi $30×10x boyutunda kalır.

  python3 AgustosKripto/Algoritmalar/runner.py close
  python3 AgustosKripto/Algoritmalar/runner.py open
  python3 AgustosKripto/Algoritmalar/runner.py trail
  python3 AgustosKripto/Algoritmalar/runner.py status
  python3 AgustosKripto/Algoritmalar/runner.py reset
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGUSTOS = os.path.dirname(_DIR)
_ROOT = os.path.dirname(_AGUSTOS)
sys.path.insert(0, _AGUSTOS)
sys.path.insert(0, _DIR)

from virtual_book import (  # noqa: E402
    DEPOSIT,
    MAX_OPENS_PER_HOUR,
    SYMBOLS,
    book_status,
    cached_status,
    close_all_positions,
    flatten_all_positions,
    fetch_all_klines,
    in_weekend_pause_tr,
    load_history,
    load_state,
    open_signals,
    refresh_status,
    reset_book,
    trail_positions,
    write_snapshot,
    now_tr,
)
from exit_policy import policy_for  # noqa: E402
from catalog import ALL_BOOKS, pick_candidates, signal_for_book  # noqa: E402

EXIT_POLICY = policy_for("Algoritmalar")
from algo_tg_notify import notify_close, notify_open, _format_close_trade, _format_open_pos, _wr  # noqa: E402

DATA = os.path.join(_DIR, "data")

# Tüm 17 defter sanalda işlem açar — $30 × 10x · max 6 (gerçek data için).
VIRTUAL_MARGIN_USD = 30.0
VIRTUAL_LEVERAGE = 10

# Bu 4 defter aynı zamanda gerçek Binance işlemi de açıyor (crypto_futures_cr6.py
# → Algoritmalar Live, $7×20x). Sanal defterleri farklı boyutlandırılır (yukarıdaki
# varsayılan); yalnızca dashboard'da canlı nokta göstermek için işaretleniyor.
REAL_LIVE_KEYS = frozenset({"algo_05", "algo_06", "algo_07", "algo1_11"})
REAL_LIVE_MARGIN_USD = 7.0
REAL_LIVE_LEVERAGE = 20


def _paths(book: dict) -> tuple[str, str]:
    tag = book["book_key"]
    return (
        os.path.join(DATA, f"{tag}_state.json"),
        os.path.join(DATA, f"{tag}_history.json"),
    )


def _cfg(book: dict) -> dict:
    return {
        "margin_usd": VIRTUAL_MARGIN_USD,
        "leverage": VIRTUAL_LEVERAGE,
        "max_opens": int(MAX_OPENS_PER_HOUR),
        "open_active": True,
    }


def label(book: dict) -> str:
    panel = "A2" if book.get("panel") == "v2" else "A1"
    return f"{panel}#{int(book['id']):02d} {book.get('title') or book.get('name')}"


def find_book(book_id: str) -> dict | None:
    """UID, book_key veya algo numarası ile defter bul."""
    if not book_id:
        return None
    bid = str(book_id).lower().strip()
    for book in ALL_BOOKS:
        uid = str(book.get("uid", "")).lower()
        bk = str(book.get("book_key", "")).lower()
        num = str(book.get("id", ""))
        if bid in (uid, bk, num):
            return book
        if num.isdigit():
            if bid in (f"algo_{int(num):02d}", f"a{num}", f"a1_{num}", f"a2_{num}"):
                return book
            if bid.lstrip("0") == num.lstrip("0"):
                return book
    return None


def book_detail(book_id: str, *, recent_limit: int = 30, with_marks: bool = True) -> dict | None:
    """Tek defter — açık pozisyonlar + son kapanmış işlemler."""
    book = find_book(book_id)
    if not book:
        return None
    sp, hp = _paths(book)
    kl = {}
    if with_marks:
        opens = load_state(sp).get("open_positions") or []
        syms = sorted({p.get("symbol") for p in opens if p.get("symbol")})
        if syms:
            kl = fetch_all_klines(syms, limit=2)
    cfg = _cfg(book)
    st = book_status(
        sp, hp,
        label=label(book),
        kl_cache=kl,
        live_marks=with_marks,
        recent_limit=recent_limit,
    )
    st["id"] = book["uid"]
    st["name"] = book["name"]
    st["title"] = book.get("title") or book["name"]
    st["category"] = book.get("category") or ""
    st["panel"] = book["panel"]
    st["algo_num"] = book["id"]
    st["book_key"] = book["book_key"]
    st["margin_usd"] = cfg["margin_usd"]
    st["leverage"] = cfg["leverage"]
    st["max_opens"] = cfg["max_opens"]
    st["open_active"] = bool(cfg["open_active"])
    st["real_live"] = book["book_key"] in REAL_LIVE_KEYS
    st["deposit"] = DEPOSIT
    return st


# Hafta sonu duraklaması KALDIRILDI (2026-08-15) — open/close/trail 7/24 koşar.
# Kripto 7/24 işlem görüyor; duraklama Poly/BIST takviminden miras kalmıştı ve
# Cuma 22:00'de açık kalan pozisyonları Pazartesi 11:00'e kadar (61 saat) ATR
# stopu olmadan bırakıyordu. Test grubu (`TEST_WEEKEND_PAUSE = False`) zaten
# 7/24 çalışıyordu, artık üç grup da aynı.
# Karar anındaki veri tek hafta sonuna dayanıyordu ve kesin değildi: Test'te
# hafta sonu girişleri brüt −$662 · SKILL −0,0138 · t=−1,80, hafta içi
# brüt +$643 · SKILL +0,0014 · t=+0,86. Duraklatmak yerine ölçülebilir veri
# toplamak tercih edildi. Geri açmak için: WEEKEND_PAUSE = True.
WEEKEND_PAUSE = False


def _skip_weekend(cmd: str) -> dict | None:
    if not WEEKEND_PAUSE or not in_weekend_pause_tr():
        return None
    print(f"[Algoritmalar] hafta sonu — {cmd} skip (Cum 22:00 – Pzt 11:00 İST)")
    return {"ok": True, "skipped": "weekend_pause", "cmd": cmd, "results": []}


def _close_tg_block(book: dict, closed_n: int, hp: str, tur_pnl: float, balance: float) -> str | None:
    if closed_n <= 0:
        return None
    history = load_history(hp)
    trades = history[-closed_n:] if closed_n <= len(history) else history
    lines = [_format_close_trade(t) for t in trades]
    wins = sum(1 for t in trades if t.get("win"))
    genel = _wr(wins, len(trades))
    return (
        f"<b>{label(book)}</b>\n"
        + "\n".join(lines)
        + f"\nBu tur: {'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$  |  Bakiye: ${balance:.2f}\n"
        f"Genel (bu tur): {genel}"
    )


def _open_tg_block(book: dict, positions: list[dict], balance: float, open_n: int) -> str | None:
    if not positions:
        return None
    lines = [_format_open_pos(p) for p in positions]
    return (
        f"<b>{label(book)}</b>\n"
        + "\n".join(lines)
        + f"\n💰 Bakiye: ${balance:.2f}  |  📂 Açık: {open_n}"
    )


def run_close() -> dict:
    skipped = _skip_weekend("close")
    if skipped:
        return skipped
    kl = fetch_all_klines(SYMBOLS, limit=5)
    results = []
    tg_blocks: list[str] = []
    tur_pnl_total = 0.0
    closed_total = 0
    held_total = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        r = close_all_positions(sp, hp, label=label(book), kl_cache=kl,
                                policy=EXIT_POLICY)
        results.append({"id": book["uid"], "name": book["name"], "panel": book["panel"], **r})
        closed_n = int(r.get("closed") or 0)
        if closed_n > 0:
            block = _close_tg_block(
                book, closed_n, hp,
                float(r.get("pnl") or 0),
                float(r.get("balance") or 0),
            )
            if block:
                tg_blocks.append(block)
        tur_pnl_total += float(r.get("pnl") or 0)
        closed_total += closed_n
        held_total += int(r.get("held") or 0)
    ntr = now_tr()
    saat_round = f"{ntr.hour:02d}:00"
    notify_close(
        saat_round=saat_round,
        blocks=tg_blocks,
        tur_pnl=tur_pnl_total,
        total_closed=closed_total,
        total_held=held_total,
    )
    return {"ok": True, "results": results}


def run_flatten() -> dict:
    kl = fetch_all_klines(SYMBOLS, limit=5)
    results = []
    total_closed = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        r = flatten_all_positions(sp, hp, label=label(book), kl_cache=kl)
        results.append({"id": book["uid"], "name": book["name"], "panel": book["panel"], **r})
        total_closed += int(r.get("closed") or 0)
    try:
        write_snapshot("algoritmalar", refresh_status_block(with_marks=False))
    except Exception:
        pass
    print(f"[Algoritmalar] flatten → {total_closed} pozisyon kapandı")
    return {"ok": True, "results": results, "total_closed": total_closed}


def run_open() -> dict:
    skipped = _skip_weekend("open")
    if skipped:
        return skipped
    kl = fetch_all_klines(SYMBOLS, limit=80)
    results = []
    tg_blocks: list[str] = []
    opened_total = 0
    open_positions_total = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        cfg = _cfg(book)
        if not cfg["open_active"]:
            results.append({
                "id": book["uid"],
                "name": book["name"],
                "panel": book["panel"],
                "ok": True,
                "skipped": "not_in_active_open",
                "opened": 0,
            })
            continue
        sigs = signal_for_book(book, kl)
        max_n = int(cfg["max_opens"])
        cands = pick_candidates(sigs, max_n=max_n)
        for c in cands:
            c["algo"] = book["name"]
        r = open_signals(
            sp, hp,
            label=label(book),
            candidates=cands,
            kl_cache=kl,
            margin_usd=float(cfg["margin_usd"]),
            leverage=int(cfg["leverage"]),
            max_opens=max_n,
            entry_price_mode="live",
        )
        results.append({
            "id": book["uid"],
            "name": book["name"],
            "panel": book["panel"],
            "margin_usd": cfg["margin_usd"],
            "leverage": cfg["leverage"],
            **r,
        })
        opened_n = int(r.get("opened") or 0)
        if opened_n > 0:
            st = load_state(sp)
            block = _open_tg_block(
                book,
                list(r.get("positions") or []),
                float(r.get("balance") or st.get("balance") or 0),
                int(r.get("open") or 0),
            )
            if block:
                tg_blocks.append(block)
        opened_total += opened_n
        open_positions_total += int(r.get("open") or 0)
    active_n = sum(1 for r in results if not r.get("skipped"))
    print(
        f"[Algoritmalar] open aktif {active_n}/{len(ALL_BOOKS)} "
        f"· ${VIRTUAL_MARGIN_USD:.0f}×{VIRTUAL_LEVERAGE}x "
        f"(gerçek Binance: {', '.join(sorted(REAL_LIVE_KEYS))} · ${REAL_LIVE_MARGIN_USD:.0f}×{REAL_LIVE_LEVERAGE}x)"
    )
    ntr = now_tr()
    saat = ntr.strftime("%H:%M")
    next_h = f"{(ntr.hour + 1) % 24:02d}:00"
    notify_open(
        saat=saat,
        next_h=next_h,
        blocks=tg_blocks,
        total_opened=opened_total,
        total_open=open_positions_total,
    )
    return {"ok": True, "active_keys": [b["book_key"] for b in ALL_BOOKS], "results": results}


def run_trail() -> dict:
    skipped = _skip_weekend("trail")
    if skipped:
        return skipped
    open_syms: set[str] = set()
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    kl = fetch_all_klines(sorted(open_syms) or SYMBOLS[:1], limit=80) if open_syms else {}
    results = []
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        r = trail_positions(sp, hp, label=label(book), kl_cache=kl,
                            policy=EXIT_POLICY)
        results.append({"id": book["uid"], "name": book["name"], "panel": book["panel"], **r})
    return {"ok": True, "results": results}


def _build_status(*, with_marks: bool = True) -> dict:
    open_syms: set[str] = set()
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    kl = fetch_all_klines(sorted(open_syms), limit=2) if with_marks and open_syms else {}
    books = []
    tot_bal = 0.0
    tot_pnl = 0.0
    tot_open = 0
    n_v1 = 0
    n_v2 = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        cfg = _cfg(book)
        st = book_status(
            sp, hp,
            label=label(book),
            kl_cache=kl,
            live_marks=with_marks,
            recent_limit=30,
        )
        st["id"] = book["uid"]
        st["name"] = book["name"]
        st["title"] = book.get("title") or book["name"]
        st["category"] = book.get("category") or ""
        st["panel"] = book["panel"]
        st["algo_num"] = book["id"]
        st["book_key"] = book["book_key"]
        st["margin_usd"] = cfg["margin_usd"]
        st["leverage"] = cfg["leverage"]
        st["max_opens"] = cfg["max_opens"]
        st["open_active"] = bool(cfg["open_active"])
        st["real_live"] = book["book_key"] in REAL_LIVE_KEYS
        books.append(st)
        tot_bal += float(st.get("balance") or 0)
        tot_pnl += float(st.get("total_pnl") or 0)
        tot_open += int(st.get("open_count") or 0)
        if book["panel"] == "v1":
            n_v1 += 1
        else:
            n_v2 += 1
    return {
        "ok": True,
        "kind": "algoritmalar",
        "count": len(books),
        "count_v1": n_v1,
        "count_v2": n_v2,
        "margin_usd": VIRTUAL_MARGIN_USD,
        "leverage": VIRTUAL_LEVERAGE,
        "active_open_keys": sorted(REAL_LIVE_KEYS),
        "active_open_margin_usd": REAL_LIVE_MARGIN_USD,
        "active_open_leverage": REAL_LIVE_LEVERAGE,
        "deposit_each": 300,
        "max_opens": MAX_OPENS_PER_HOUR,
        "total_balance": round(tot_bal, 2),
        "total_pnl": round(tot_pnl, 4),
        "total_open": tot_open,
        "books": books,
    }


def status_block(*, with_marks: bool = True) -> dict:
    return cached_status("algoritmalar", lambda: _build_status(with_marks=with_marks))


def refresh_status_block(*, with_marks: bool = True) -> dict:
    return refresh_status("algoritmalar", lambda: _build_status(with_marks=with_marks))


def run_reset(*, balance: float = DEPOSIT) -> dict:
    """Tüm ALGO1+ALGO2 defterlerini kapat + bakiyeyi $300'e çek."""
    results = []
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        st = reset_book(sp, balance=balance)
        results.append({
            "id": book["uid"],
            "name": book["name"],
            "panel": book["panel"],
            "balance": st.get("balance"),
            "open_count": 0,
        })
    out = {
        "ok": True,
        "kind": "algoritmalar",
        "reset_balance": float(balance),
        "count": len(results),
        "results": results,
    }
    try:
        write_snapshot("algoritmalar", refresh_status_block(with_marks=False))
    except Exception:
        pass
    print(f"[Algoritmalar] reset → ${balance:.0f} × {len(results)} defter (A2+A1)")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="AgustosKripto Algoritmalar sanal runner")
    p.add_argument("cmd", choices=["open", "close", "trail", "status", "reset", "flatten"])
    args = p.parse_args()
    if args.cmd == "open":
        r = run_open()
    elif args.cmd == "close":
        r = run_close()
    elif args.cmd == "trail":
        r = run_trail()
    elif args.cmd == "reset":
        r = run_reset()
    elif args.cmd == "flatten":
        r = run_flatten()
    else:
        r = status_block()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

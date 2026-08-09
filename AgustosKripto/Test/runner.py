#!/usr/bin/env python3
"""Kripto Test runner — Poly sinyalleri, sanal Binance futures ($1000 / $100×6x / 30 coin).

Poly trader ve Algoritmalar runner'a dokunmaz; ayrı data/ defterleri.

  python3 AgustosKripto/Test/runner.py close|open|trail|status|reset
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
    book_status,
    cached_status,
    close_all_positions,
    close_reversal_positions,
    fetch_all_klines,
    in_weekend_pause_tr,
    load_history,
    load_state,
    open_signals,
    refresh_status,
    reset_book,
    save_state,
    trail_positions,
    write_snapshot,
    now_tr,
)
import importlib.util as _ilu

_test_cat_spec = _ilu.spec_from_file_location(
    "kripto_test_catalog",
    os.path.join(_DIR, "catalog.py"),
)
_test_cat = _ilu.module_from_spec(_test_cat_spec)
assert _test_cat_spec.loader is not None
_test_cat_spec.loader.exec_module(_test_cat)
ALL_BOOKS = _test_cat.ALL_BOOKS
TEST_SYMBOLS = _test_cat.TEST_SYMBOLS

_test_sig_spec = _ilu.spec_from_file_location(
    "kripto_test_signals",
    os.path.join(_DIR, "signals.py"),
)
_test_sig = _ilu.module_from_spec(_test_sig_spec)
assert _test_sig_spec.loader is not None
_test_sig_spec.loader.exec_module(_test_sig)
signal_for_book = _test_sig.signal_for_book

_test_eng_spec = _ilu.spec_from_file_location(
    "kripto_test_engine",
    os.path.join(_DIR, "engine.py"),
)
_test_eng = _ilu.module_from_spec(_test_eng_spec)
assert _test_eng_spec.loader is not None
_test_eng_spec.loader.exec_module(_test_eng)
build_candidates = _test_eng.build_candidates
klines_for_positions = _test_eng.klines_for_positions
find_reversal_closes = _test_eng.find_reversal_closes
MIN_HOLD_MINUTES = _test_eng.MIN_HOLD_MINUTES

DATA = os.path.join(_DIR, "data")
_ALGO_DATA = os.path.join(_AGUSTOS, "Algoritmalar", "data")
_TEST_SYM_SET = {s.replace("USDT", "") for s in TEST_SYMBOLS}

DEPOSIT = 1000.0
MARGIN_USD = 100.0
LEVERAGE = 6
MAX_OPEN_POSITIONS = 4


def _paths(book: dict) -> tuple[str, str]:
    tag = book["book_key"]
    return (
        os.path.join(DATA, f"{tag}_state.json"),
        os.path.join(DATA, f"{tag}_history.json"),
    )


def _ensure_state(sp: str) -> None:
    if os.path.exists(sp):
        return
    os.makedirs(DATA, exist_ok=True)
    st = {
        "balance": DEPOSIT,
        "deposit": DEPOSIT,
        "open_positions": [],
        "total_pnl": 0.0,
        "total_commission": 0.0,
        "updated_at_tr": "",
        "last_open_slot": "",
        "atr_skip_syms": [],
    }
    save_state(sp, st)


def label(book: dict) -> str:
    return f"{book.get('name') or book['uid']} · {book.get('title') or ''}".strip(" ·")


def find_book(book_id: str) -> dict | None:
    """UID veya book_key ile Test defterini bul."""
    if not book_id:
        return None
    bid = str(book_id)
    for book in ALL_BOOKS:
        if book.get("uid") == bid or book.get("book_key") == bid:
            return book
    return None


def book_detail(book_id: str, *, recent_limit: int = 30, with_marks: bool = True) -> dict | None:
    """Tek defter için (açık pozisyonlar + geçmiş) — detay sayfası API'si."""
    book = find_book(book_id)
    if not book:
        return None
    sp, hp = _paths(book)
    _ensure_state(sp)
    kl = {}
    if with_marks:
        opens = load_state(sp).get("open_positions") or []
        syms = sorted({p.get("symbol") for p in opens if p.get("symbol")})
        if syms:
            kl = fetch_all_klines(syms, limit=2)
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
    st["category"] = book.get("category") or "Kripto Test"
    st["panel"] = "test"
    st["book_key"] = book["book_key"]
    st["margin_usd"] = MARGIN_USD
    st["leverage"] = LEVERAGE
    st["max_opens"] = MAX_OPEN_POSITIONS
    st["deposit"] = DEPOSIT
    return st


def _history_path_for_book(book: dict) -> str | None:
    """Test defteri geçmişi; yoksa aynı motorun Algoritmalar sanal geçmişine bak."""
    _sp, hp = _paths(book)
    if os.path.exists(hp):
        try:
            if load_history(hp):
                return hp
        except Exception:
            pass
    src = book.get("source")
    if src == "islemler_a2":
        num = book.get("id") or int(str(book.get("uid", "a2_0")).split("_")[-1])
        fp = os.path.join(_ALGO_DATA, f"algo_{int(num):02d}_history.json")
        return fp if os.path.exists(fp) else hp
    if src == "algo1":
        num = book.get("id")
        if num is not None:
            fp = os.path.join(_ALGO_DATA, f"algo1_{int(num):02d}_history.json")
            return fp if os.path.exists(fp) else hp
    return hp if os.path.exists(hp) else None


def compute_top_success(*, n: int = 6, min_trades: int = 2) -> list[dict]:
    """Algo+coin bazında en yüksek WR (eşitlikte net PnL) — Kripto overview kutusu."""
    buckets: dict[tuple[str, str], dict] = {}
    for book in ALL_BOOKS:
        hp = _history_path_for_book(book)
        if not hp:
            continue
        try:
            hist = load_history(hp)
        except Exception:
            continue
        algo = (book.get("name") or book["uid"]).lower()
        for t in hist:
            sym = (t.get("symbol") or "").upper().replace("USDT", "")
            if not sym or sym not in _TEST_SYM_SET:
                continue
            key = (algo, sym)
            b = buckets.setdefault(
                key,
                {"algo": algo, "symbol": sym, "wins": 0, "trades": 0, "pnl": 0.0},
            )
            b["trades"] += 1
            if t.get("win"):
                b["wins"] += 1
            b["pnl"] += float(t.get("pnl") or 0)
    rows: list[dict] = []
    for b in buckets.values():
        if b["trades"] < min_trades:
            continue
        wr = round(100.0 * b["wins"] / b["trades"], 1)
        rows.append({
            "algo": b["algo"],
            "symbol": b["symbol"],
            "label": f"{b['algo']} {b['symbol']}",
            "wins": b["wins"],
            "trades": b["trades"],
            "wr": wr,
            "pnl": round(b["pnl"], 4),
        })
    rows.sort(key=lambda x: (-x["wr"], -x["pnl"], -x["trades"]))
    return rows[:n]


def top_success_block(*, n: int = 6) -> list[dict]:
    from virtual_book import read_snapshot

    snap = read_snapshot("test", max_age=900)
    if snap and snap.get("top_success"):
        return list(snap["top_success"])[:n]
    return compute_top_success(n=n)


def compute_coin_leaders(*, min_trades: int = 2) -> list[dict]:
    """20 coin'in her biri için en başarılı algoritma — 'hangi coin'de hangi
    algoritma çok başarılı' sorusuna cevap; algoritma seçimi için lider tablosu.
    """
    buckets: dict[tuple[str, str], dict] = {}
    for book in ALL_BOOKS:
        hp = _history_path_for_book(book)
        if not hp:
            continue
        try:
            hist = load_history(hp)
        except Exception:
            continue
        algo = book.get("name") or book["uid"]
        for t in hist:
            sym = (t.get("symbol") or "").upper().replace("USDT", "")
            if not sym or sym not in _TEST_SYM_SET:
                continue
            key = (sym, algo)
            b = buckets.setdefault(
                key,
                {"symbol": sym, "algo": algo, "wins": 0, "trades": 0, "pnl": 0.0},
            )
            b["trades"] += 1
            if t.get("win"):
                b["wins"] += 1
            b["pnl"] += float(t.get("pnl") or 0)

    by_symbol: dict[str, list[dict]] = {}
    for b in buckets.values():
        if b["trades"] < min_trades:
            continue
        row = {**b, "wr": round(100.0 * b["wins"] / b["trades"], 1), "pnl": round(b["pnl"], 4)}
        by_symbol.setdefault(b["symbol"], []).append(row)

    out: list[dict] = []
    for sym in sorted({s.replace("USDT", "") for s in TEST_SYMBOLS}):
        cands = sorted(
            by_symbol.get(sym) or [],
            key=lambda r: (-r["wr"], -r["pnl"], -r["trades"]),
        )
        if not cands:
            out.append({"symbol": sym, "best": None, "runner_up": None, "candidates": 0})
            continue
        best = cands[0]
        runner_up = cands[1] if len(cands) > 1 else None
        out.append({
            "symbol": sym,
            "best": {
                "algo": best["algo"], "wr": best["wr"],
                "trades": best["trades"], "wins": best["wins"], "pnl": best["pnl"],
            },
            "runner_up": (
                {
                    "algo": runner_up["algo"], "wr": runner_up["wr"],
                    "trades": runner_up["trades"], "pnl": runner_up["pnl"],
                } if runner_up else None
            ),
            "candidates": len(cands),
        })
    out.sort(key=lambda r: (
        -(r["best"]["wr"] if r["best"] else -1),
        -(r["best"]["trades"] if r["best"] else 0),
    ))
    return out


def compute_recent_test_trades(*, limit: int = 12) -> list[dict]:
    """Tüm Test defterlerinden son kapanan işlemler — overview sağ panel."""
    rows: list[dict] = []
    for book in ALL_BOOKS:
        hp = _history_path_for_book(book)
        if not hp:
            continue
        try:
            hist = load_history(hp)
        except Exception:
            continue
        algo = book.get("name") or book["uid"]
        for t in hist[-4:]:
            sym = (t.get("symbol") or "").upper()
            if not sym:
                continue
            rows.append({
                "algo": t.get("algo") or algo,
                "symbol": sym,
                "name": sym.replace("USDT", ""),
                "side": t.get("side"),
                "pnl": round(float(t.get("pnl") or 0), 4),
                "win": bool(t.get("win")),
                "interval": t.get("interval"),
                "exit_time_tr": t.get("exit_time_tr") or "",
                "entry_time_tr": t.get("entry_time_tr") or "",
                "close_reason": t.get("close_reason") or "",
            })
    rows.sort(key=lambda x: x.get("exit_time_tr") or "", reverse=True)
    return rows[:limit]


# Kripto Test'e özel: hafta sonu duraklaması KAPALI — sadece bu ekran 7/24 çalışır.
# Algoritmalar/Analizler/Poly bu değişiklikten etkilenmez (virtual_book.in_weekend_pause_tr
# hâlâ oradaki hafta sonu kısıtını uyguluyor).
TEST_WEEKEND_PAUSE = False


def _skip_weekend(cmd: str) -> dict | None:
    if not TEST_WEEKEND_PAUSE or not in_weekend_pause_tr():
        return None
    print(f"[Kripto Test] hafta sonu — {cmd} skip (Cum 22:00 – Pzt 11:00 İST)")
    return {"ok": True, "skipped": "weekend_pause", "cmd": cmd, "results": []}


def run_close() -> dict:
    skipped = _skip_weekend("close")
    if skipped:
        return skipped
    pos_list: list[dict] = []
    for book in ALL_BOOKS:
        sp, _ = _paths(book)
        pos_list.extend(load_state(sp).get("open_positions") or [])
    kl = klines_for_positions(pos_list, limit=80)
    results = []
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        _ensure_state(sp)
        r = close_all_positions(sp, hp, label=label(book), kl_cache=kl)
        skip_add = set(r.get("closed_atr_syms") or [])
        if skip_add:
            st = load_state(sp)
            skip = {str(s).upper() for s in (st.get("atr_skip_syms") or []) if s}
            skip.update(skip_add)
            st["atr_skip_syms"] = sorted(skip)
            save_state(sp, st)
        results.append({"id": book["uid"], "name": book["name"], **r})
    return {"ok": True, "results": results}


def run_open() -> dict:
    skipped = _skip_weekend("open")
    if skipped:
        return skipped
    kl_1h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="1h")
    kl_4h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="4h")
    results = []
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        _ensure_state(sp)
        st = load_state(sp)
        blocked = {str(s).upper() for s in (st.get("atr_skip_syms") or []) if s}
        st["atr_skip_syms"] = []
        save_state(sp, st)
        history = load_history(hp)
        cands = build_candidates(
            book, kl_1h, kl_4h, history,
            symbols=TEST_SYMBOLS,
            signal_for_book=signal_for_book,
        )
        for c in cands:
            c["algo"] = book["name"]
        r = open_signals(
            sp, hp,
            label=label(book),
            candidates=cands,
            kl_cache={**{f"{s}|1h": kl_1h.get(s, []) for s in TEST_SYMBOLS},
                      **{f"{s}|4h": kl_4h.get(s, []) for s in TEST_SYMBOLS}},
            margin_usd=MARGIN_USD,
            leverage=LEVERAGE,
            max_opens=MAX_OPEN_POSITIONS,
            blocked_syms=blocked,
        )
        results.append({
            "id": book["uid"],
            "name": book["name"],
            "opened": r.get("opened", 0),
            **r,
        })
    print(
        f"[Kripto Test] open {len(ALL_BOOKS)} defter · ${MARGIN_USD:.0f}×{LEVERAGE}x "
        f"· max {MAX_OPEN_POSITIONS} · 1h/4h ATR"
    )
    return {"ok": True, "results": results}


def run_trail() -> dict:
    skipped = _skip_weekend("trail")
    if skipped:
        return skipped
    pos_list: list[dict] = []
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        _ensure_state(sp)
        pos_list.extend(load_state(sp).get("open_positions") or [])
    kl = klines_for_positions(pos_list, limit=80) if pos_list else {}
    results = []
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        r = trail_positions(sp, hp, label=label(book), kl_cache=kl)
        closed_syms = r.get("closed_symbols") or []
        if closed_syms:
            st = load_state(sp)
            skip = {str(s).upper() for s in (st.get("atr_skip_syms") or []) if s}
            skip.update(str(s).upper() for s in closed_syms if s)
            st["atr_skip_syms"] = sorted(skip)
            save_state(sp, st)
        results.append({"id": book["uid"], "name": book["name"], **r})
    return {"ok": True, "results": results}


def run_scan() -> dict:
    """Sık aralıklı tur (cron */10): boş slotu hızlı doldur + gerçek ters sinyalde anında kapat.

    Sinyal formülü değişmez (1h/4h kapanmış mumdan hesaplanan Poly/ALGO1 motorları).
    Bu turda değişen sadece:
      - giriş fiyatı: son oluşan mumun canlı close'u (kapanmış mum beklenmez),
      - saatlik "tek seferlik" açılış kilidi atlanır (boş slot varsa hemen doldurulur),
      - ters sinyal + MIN_HOLD_MINUTES dolduysa ATR beklemeden kapatılır
        (NEUTRAL veya erken an tetiklemez — flip-flop'u engellemek için).
    Hourly open/close (:05/:02) ve ATR trail (*/2) aynen çalışmaya devam eder.
    """
    skipped = _skip_weekend("scan")
    if skipped:
        return skipped
    kl_1h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="1h")
    kl_4h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="4h")
    kl_cache = {
        **{f"{s}|1h": kl_1h.get(s, []) for s in TEST_SYMBOLS},
        **{f"{s}|4h": kl_4h.get(s, []) for s in TEST_SYMBOLS},
    }
    results = []
    total_closed = 0
    total_opened = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        _ensure_state(sp)
        st = load_state(sp)
        opens = list(st.get("open_positions") or [])

        reversed_syms = find_reversal_closes(
            book, opens, kl_1h, kl_4h, signal_for_book=signal_for_book,
        )
        r_close: dict = {"closed": 0, "closed_symbols": []}
        if reversed_syms:
            r_close = close_reversal_positions(
                sp, hp, label=label(book), reversed_symbols=reversed_syms, kl_cache=kl_cache,
            )
            total_closed += int(r_close.get("closed") or 0)

        st = load_state(sp)  # kapanış sonrası taze durum
        blocked = {str(s).upper() for s in (st.get("atr_skip_syms") or []) if s}
        slots_left = MAX_OPEN_POSITIONS - len(st.get("open_positions") or [])

        r_open: dict = {"opened": 0}
        if slots_left > 0:
            history = load_history(hp)
            cands = build_candidates(
                book, kl_1h, kl_4h, history,
                symbols=TEST_SYMBOLS,
                signal_for_book=signal_for_book,
            )
            for c in cands:
                c["algo"] = book["name"]
            r_open = open_signals(
                sp, hp,
                label=label(book),
                candidates=cands,
                kl_cache=kl_cache,
                margin_usd=MARGIN_USD,
                leverage=LEVERAGE,
                max_opens=MAX_OPEN_POSITIONS,
                blocked_syms=blocked,
                entry_price_mode="live",
                bypass_slot_gate=True,
            )
            total_opened += int(r_open.get("opened") or 0)

        results.append({
            "id": book["uid"],
            "name": book["name"],
            "reversal_closed": r_close.get("closed", 0),
            "reversal_symbols": r_close.get("closed_symbols", []),
            "opened": r_open.get("opened", 0),
        })
    print(
        f"[Kripto Test] scan {len(ALL_BOOKS)} defter · ters kapanan={total_closed} "
        f"· yeni açılan={total_opened} · min bekleme {int(MIN_HOLD_MINUTES)}dk"
    )
    return {
        "ok": True,
        "results": results,
        "total_closed": total_closed,
        "total_opened": total_opened,
    }


def _build_waiting(kl: dict[str, list], open_syms: set[str]) -> list[dict]:
    votes: dict[str, dict[str, int]] = {s: {"UP": 0, "DOWN": 0} for s in TEST_SYMBOLS}
    for book in ALL_BOOKS:
        sigs = signal_for_book(book, kl)
        for sym, d in sigs.items():
            if sym not in votes:
                continue
            if d == "UP":
                votes[sym]["UP"] += 1
            elif d == "DOWN":
                votes[sym]["DOWN"] += 1
    rows = []
    for sym in TEST_SYMBOLS:
        kl_list = kl.get(sym) or []
        price = float(kl_list[-1]["c"]) if kl_list else None
        up, dn = votes[sym]["UP"], votes[sym]["DOWN"]
        if up > dn:
            sig, score = "UP", up
        elif dn > up:
            sig, score = "DOWN", dn
        else:
            sig, score = "NEUTRAL", 0
        rows.append({
            "symbol": sym,
            "name": sym.replace("USDT", ""),
            "signal": sig,
            "dir_tr": "YÜKSELİR" if sig == "UP" else "DÜŞER" if sig == "DOWN" else "NÖTR",
            "score": score,
            "price": price,
            "is_open": sym in open_syms,
            "is_top": score >= 8 and sig in ("UP", "DOWN"),
            "waiting": sym not in open_syms and sig in ("UP", "DOWN"),
            "algo": f"konsensüs {up}↑ {dn}↓",
            "tier_label": f"{len(ALL_BOOKS)} algo",
        })
    rows.sort(key=lambda x: (-x["score"], x["symbol"]))
    return rows


def _build_status(*, with_marks: bool = True) -> dict:
    open_syms: set[str] = set()
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        _ensure_state(sp)
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    kl = fetch_all_klines(TEST_SYMBOLS, limit=80) if with_marks else {}
    if with_marks and open_syms:
        kl_open = fetch_all_klines(sorted(open_syms), limit=2)
        kl.update(kl_open)
    # book_status() mutasyonla kl_cache'e "SYM|interval" anahtarları ekler
    # (pozisyon ATR/mark takibi için) — sinyal hesaplaması (signal_for_book)
    # sadece düz sembol anahtarı bekler, kirlenmemiş kopya kullan.
    kl_plain = dict(kl)
    books = []
    tot_bal = 0.0
    tot_pnl = 0.0
    tot_open = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        st = book_status(
            sp, hp,
            label=label(book),
            kl_cache=kl if with_marks else {},
            live_marks=with_marks,
            recent_limit=30,
        )
        st["id"] = book["uid"]
        st["name"] = book["name"]
        st["title"] = book.get("title") or book["name"]
        st["category"] = book.get("category") or "Kripto Test"
        st["panel"] = "test"
        st["book_key"] = book["book_key"]
        st["margin_usd"] = MARGIN_USD
        st["leverage"] = LEVERAGE
        st["max_opens"] = MAX_OPEN_POSITIONS
        st["open_active"] = True
        st["deposit"] = DEPOSIT
        books.append(st)
        tot_bal += float(st.get("balance") or 0)
        tot_pnl += float(st.get("total_pnl") or 0)
        tot_open += int(st.get("open_count") or 0)
    books.sort(
        key=lambda b: (
            -(float(b.get("total_pnl") or 0) + float(b.get("unrealized_pnl") or 0)),
            -(b.get("wr") or 0) if (b.get("history_n") or 0) >= 2 else 0,
            -(b.get("wins") or 0),
        )
    )
    waiting = _build_waiting(kl_plain, open_syms) if with_marks else []
    top_success = compute_top_success(n=6)
    coin_leaders = compute_coin_leaders()
    return {
        "ok": True,
        "kind": "test",
        "count": len(books),
        "deposit_each": DEPOSIT,
        "margin_usd": MARGIN_USD,
        "leverage": LEVERAGE,
        "max_opens": MAX_OPEN_POSITIONS,
        "symbols_n": len(TEST_SYMBOLS),
        "total_balance": round(tot_bal, 2),
        "total_pnl": round(tot_pnl, 4),
        "total_open": tot_open,
        "books": books,
        "waiting": waiting,
        "top_success": top_success,
        "coin_leaders": coin_leaders,
    }


def status_block(*, with_marks: bool = True) -> dict:
    return cached_status("test", lambda: _build_status(with_marks=with_marks))


def refresh_status_block(*, with_marks: bool = True) -> dict:
    return refresh_status("test", lambda: _build_status(with_marks=with_marks))


def run_reset(*, balance: float = DEPOSIT) -> dict:
    results = []
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        st = reset_book(sp, balance=balance, clear_history_path=hp)
        st["deposit"] = balance
        save_state(sp, st)
        results.append({
            "id": book["uid"],
            "name": book["name"],
            "balance": st.get("balance"),
        })
    out = {
        "ok": True,
        "kind": "test",
        "reset_balance": float(balance),
        "count": len(results),
        "results": results,
    }
    try:
        write_snapshot("test", refresh_status_block(with_marks=False))
    except Exception:
        pass
    print(f"[Kripto Test] reset → ${balance:.0f} × {len(results)} defter")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="AgustosKripto Test sanal runner")
    p.add_argument("cmd", choices=["open", "close", "trail", "scan", "status", "reset"])
    args = p.parse_args()
    if args.cmd == "open":
        r = run_open()
    elif args.cmd == "close":
        r = run_close()
    elif args.cmd == "trail":
        r = run_trail()
    elif args.cmd == "scan":
        r = run_scan()
    elif args.cmd == "reset":
        r = run_reset()
    else:
        r = status_block()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    try:
        write_snapshot("test", refresh_status_block(with_marks=True))
    except Exception:
        pass


if __name__ == "__main__":
    main()

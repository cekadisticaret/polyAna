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
    flatten_all_positions,
    fetch_all_klines,
    in_weekend_pause_tr,
    load_history,
    load_state,
    open_signals,
    position_age_minutes,
    refresh_status,
    reset_book,
    save_state,
    trail_positions,
    write_snapshot,
    now_tr,
)
from exit_policy import policy_for  # noqa: E402

EXIT_POLICY = policy_for("Test")

import importlib.util as _ilu

_CAT_PATH = os.path.join(_DIR, "catalog.py")
_SIG_PATH = os.path.join(_DIR, "signals.py")


def _load_test_module(stem: str, path: str):
    """catalog/signals — dosya mtime değişince yeni modül (dashboard cache bayat kalmasın)."""
    key = f"{stem}_{int(os.path.getmtime(path))}"
    if key in sys.modules:
        return sys.modules[key]
    spec = _ilu.spec_from_file_location(key, path)
    mod = _ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    sys.modules[key] = mod
    return mod


_test_cat = _load_test_module("kripto_test_catalog", _CAT_PATH)
ALL_BOOKS = _test_cat.ALL_BOOKS
TEST_SYMBOLS = _test_cat.TEST_SYMBOLS

_test_sig = _load_test_module("kripto_test_signals", _SIG_PATH)
signal_for_book = _test_sig.signal_for_book

_test_gate = _load_test_module("kripto_test_edge_gate", os.path.join(_DIR, "edge_gate.py"))
edge_decision = _test_gate.decision
edge_summary = _test_gate.summary
gate_open = _test_gate.gate_open

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

# ── PRO rejimi ───────────────────────────────────────────────
# Ölçüm: saatlik zorunlu kapanış 1 yılda A2#05'e 34.692 işlem × $0,58 komisyon
# yükledi (−$26.552). Aynı sinyal sinyal-dönene-kadar tutulunca 5.841 işleme
# indi (−$11.811): komisyonun %83'ü kalkıyor. PRO defterleri bu rejimi kullanır
# ve ek olarak `edge_gate` ölçülen kenarı komisyonu aşmayan çifti hiç açmaz.
PRO_MAX_HOLD_HOURS = 48.0   # kapı bir ufuk vermezse tavan
PRO_MIN_HOLD_HOURS = 1.0    # açıldığı saat içinde süre sınırıyla kapanmasın


def is_pro(book: dict) -> bool:
    return (book.get("mode") or "") == "pro"


def max_opens_for(book: dict) -> int:
    if (book.get("uid") or "") == "jarvis_v1":
        return int(book.get("max_opens") or 10)
    return MAX_OPEN_POSITIONS


def _build_candidates_for_book(
    book: dict,
    kl_1h: dict,
    kl_4h: dict,
    history: list,
) -> list[dict]:
    if (book.get("uid") or "") == "jarvis_v1":
        from jarvis_v1 import build_jarvis_candidates  # noqa: WPS433

        return build_jarvis_candidates(
            book, kl_1h, kl_4h, history,
            symbols=TEST_SYMBOLS,
            signal_for_book=signal_for_book,
        )
    return build_candidates(
        book, kl_1h, kl_4h, history,
        symbols=TEST_SYMBOLS,
        signal_for_book=signal_for_book,
    )


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
    st["max_opens"] = max_opens_for(book)
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
    if is_pro(book):
        # PRO defteri farklı çıkış rejimi — başka defterin geçmişiyle karışmaz
        return hp if os.path.exists(hp) else None
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


# ── Drift-nötr sıralama ───────────────────────────────────────
# WR bazlı sıralama örneklem dönemindeki piyasa yönünü ölçüyordu:
# 30 coin × 60 algoritma = 1.800 kombinasyonda 2-3 işlemli %100'ler
# rastgele oluşuyor ve her saat değişiyor. Ölçülen: ADA SHORT'un
# t=8,68'lik "kenarı" LONG −0,1409% / SHORT +0,1485% ayrıştırmasında
# yok oldu (SKILL ~0). Bu yüzden sıralama artık SKILL + t-istatistiği.
LEADER_MIN_TRADES = 20
LEADER_MIN_T = 2.0
# Eşik %0.04 idi ve yorumu "maker gidiş-dönüş" diyordu — ama bu defterler
# taker ödüyor. 50.554 gerçek işlemden ölçülen fiili maliyet %0.10
# (yön başına %0.05). Eski eşik gerçeğin 2,5 katı altındaydı, yani masrafını
# çıkaramayan (defter, coin) çiftlerini "nitelikli" gösteriyordu.
LEADER_MIN_SKILL = 0.10


def _trade_ret_pct(t: dict) -> float | None:
    """Kaldıraçsız yüzde getiri — yön düzeltmeli."""
    try:
        entry = float(t["entry_price"])
        exit_ = float(t["exit_price"])
    except (KeyError, TypeError, ValueError):
        return None
    if entry <= 0:
        return None
    move = (exit_ - entry) / entry * 100.0
    return move if t.get("side") == "LONG" else -move


def _skill_stats(longs: list[float], shorts: list[float]) -> dict:
    """SKILL / DRIFT / t — tek yön varsa SKILL hesaplanamaz (None)."""
    allv = longs + shorts
    n = len(allv)
    out = {
        "n": n,
        "n_long": len(longs),
        "n_short": len(shorts),
        "skill": None,
        "drift": None,
        "t": 0.0,
    }
    if n < 2:
        return out
    mean = sum(allv) / n
    sd = (sum((v - mean) ** 2 for v in allv) / n) ** 0.5
    out["t"] = round((mean / (sd / n ** 0.5)) if sd > 0 else 0.0, 2)
    out["mean_ret"] = round(mean, 4)
    if longs and shorts:
        ml = sum(longs) / len(longs)
        ms = sum(shorts) / len(shorts)
        out["mean_long"] = round(ml, 4)
        out["mean_short"] = round(ms, 4)
        out["skill"] = round((ml + ms) / 2, 4)
        out["drift"] = round((ms - ml) / 2, 4)
    return out


def _leader_qualifies(row: dict) -> bool:
    """Gerçek para için asgari kenar şartı."""
    skill = row.get("skill")
    return (
        skill is not None
        and row.get("trades", 0) >= LEADER_MIN_TRADES
        and skill >= LEADER_MIN_SKILL
        and abs(row.get("t") or 0) >= LEADER_MIN_T
    )


def _leader_sort_key(r: dict):
    """Nitelikli olanlar önce, sonra SKILL, sonra işlem sayısı."""
    return (
        0 if r.get("qualifies") else 1,
        -(r.get("skill") if r.get("skill") is not None else -99),
        -(r.get("trades") or 0),
    )


def _collect_pairs() -> dict:
    """(coin, algo) → istatistik kovası; tüm Test defterlerini tarar."""
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
            b = buckets.setdefault(
                (sym, algo),
                {
                    "symbol": sym, "algo": algo, "wins": 0, "trades": 0,
                    "pnl": 0.0, "gross": 0.0, "commission": 0.0,
                    "longs": [], "shorts": [],
                },
            )
            b["trades"] += 1
            if t.get("win"):
                b["wins"] += 1
            b["pnl"] += float(t.get("pnl") or 0)
            b["gross"] += float(t.get("pnl_gross") or 0)
            b["commission"] += float(t.get("commission") or 0)
            v = _trade_ret_pct(t)
            if v is not None:
                if t.get("side") == "LONG":
                    b["longs"].append(v)
                elif t.get("side") == "SHORT":
                    b["shorts"].append(v)
    return buckets


def _pair_row(b: dict) -> dict:
    st = _skill_stats(b["longs"], b["shorts"])
    row = {
        "symbol": b["symbol"],
        "algo": b["algo"],
        "wins": b["wins"],
        "trades": b["trades"],
        "wr": round(100.0 * b["wins"] / b["trades"], 1) if b["trades"] else 0.0,
        "pnl": round(b["pnl"], 4),
        "gross": round(b["gross"], 4),
        "commission": round(b["commission"], 4),
        "skill": st["skill"],
        "drift": st["drift"],
        "t": st["t"],
        "n_long": st["n_long"],
        "n_short": st["n_short"],
    }
    row["qualifies"] = _leader_qualifies(row)
    return row


def compute_top_success(*, n: int = 6, min_trades: int | None = None) -> list[dict]:
    """Algo+coin bazında en yüksek SKILL — Kripto overview kutusu.

    Sıralama drift-nötr SKILL üzerinden; nitelikli (n≥20, SKILL≥%0.10 =
    ölçülen taker maliyeti, |t|≥2) satırlar en üstte.
    """
    floor = LEADER_MIN_TRADES if min_trades is None else int(min_trades)
    rows = [
        _pair_row(b)
        for b in _collect_pairs().values()
        if b["trades"] >= floor
    ]
    for r in rows:
        r["algo"] = str(r["algo"]).lower()
        r["label"] = f"{r['algo']} {r['symbol']}"
    rows.sort(key=_leader_sort_key)
    return rows[:n]


def top_success_block(*, n: int = 6) -> list[dict]:
    from virtual_book import read_snapshot

    snap = read_snapshot("test", max_age=900)
    if snap and snap.get("top_success"):
        return list(snap["top_success"])[:n]
    return compute_top_success(n=n)


def compute_coin_leaders(*, min_trades: int | None = None) -> list[dict]:
    """30 coin'in her biri için en yüksek SKILL'li algoritma.

    'En iyi' artık WR değil drift-nötr SKILL: LONG ve SHORT ortalamalarının
    ortalaması. Böylece coin'in örneklem dönemindeki yönü sıralamaya
    karışmıyor. `qualified` alanı gerçek para eşiğini geçen coin sayısını
    ayırt etmek için.
    """
    floor = LEADER_MIN_TRADES if min_trades is None else int(min_trades)
    by_symbol: dict[str, list[dict]] = {}
    for b in _collect_pairs().values():
        if b["trades"] < floor:
            continue
        by_symbol.setdefault(b["symbol"], []).append(_pair_row(b))

    def _slim(r: dict) -> dict:
        return {
            "algo": r["algo"], "wr": r["wr"], "trades": r["trades"],
            "wins": r["wins"], "pnl": r["pnl"], "skill": r["skill"],
            "drift": r["drift"], "t": r["t"], "n_long": r["n_long"],
            "n_short": r["n_short"], "qualifies": r["qualifies"],
        }

    out: list[dict] = []
    for sym in sorted({s.replace("USDT", "") for s in TEST_SYMBOLS}):
        cands = sorted(by_symbol.get(sym) or [], key=_leader_sort_key)
        if not cands:
            out.append({
                "symbol": sym, "best": None, "runner_up": None,
                "candidates": 0, "qualified": 0,
            })
            continue
        out.append({
            "symbol": sym,
            "best": _slim(cands[0]),
            "runner_up": _slim(cands[1]) if len(cands) > 1 else None,
            "candidates": len(cands),
            "qualified": sum(1 for r in cands if r["qualifies"]),
        })
    out.sort(key=lambda r: (
        0 if (r["best"] and r["best"]["qualifies"]) else 1,
        -((r["best"]["skill"] if r["best"] and r["best"]["skill"] is not None else -99)),
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


def _pro_expired_symbols(state: dict) -> set[str]:
    """Süre sınırını aşan PRO pozisyonları — kapının verdiği ufuk, yoksa tavan."""
    out: set[str] = set()
    for pos in (state.get("open_positions") or []):
        sym = str(pos.get("symbol") or "").upper()
        if not sym:
            continue
        limit = float(pos.get("max_hold_h") or PRO_MAX_HOLD_HOURS)
        limit = max(limit, PRO_MIN_HOLD_HOURS)
        if position_age_minutes(pos) >= limit * 60.0:
            out.add(sym)
    return out


def run_close() -> dict:
    """Saatlik settle — PRO defterleri hariç.

    PRO'da saatlik zorunlu kapanış yok: pozisyon sinyal dönene (scan), ATR
    stopuna (trail) veya süre sınırına kadar tutulur. Bu turda yalnız süresi
    dolanlar kapatılır.
    """
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
        if is_pro(book):
            expired = _pro_expired_symbols(load_state(sp))
            r = (close_reversal_positions(
                    sp, hp, label=label(book), reversed_symbols=expired,
                    kl_cache=kl, reason="max_hold")
                 if expired else {"ok": True, "closed": 0, "closed_symbols": []})
            results.append({"id": book["uid"], "name": book["name"], "pro": True, **r})
            continue
        r = close_all_positions(sp, hp, label=label(book), kl_cache=kl,
                                policy=EXIT_POLICY)
        skip_add = set(r.get("closed_atr_syms") or [])
        if skip_add:
            st = load_state(sp)
            skip = {str(s).upper() for s in (st.get("atr_skip_syms") or []) if s}
            skip.update(skip_add)
            st["atr_skip_syms"] = sorted(skip)
            save_state(sp, st)
        results.append({"id": book["uid"], "name": book["name"], **r})
    return {"ok": True, "results": results}


def run_flatten() -> dict:
    """Tüm açık pozisyonları anlık fiyattan kapat (çıkış rejiminden bağımsız)."""
    pos_list: list[dict] = []
    for book in ALL_BOOKS:
        sp, _ = _paths(book)
        pos_list.extend(load_state(sp).get("open_positions") or [])
    kl = klines_for_positions(pos_list, limit=80) if pos_list else {}
    results = []
    total_closed = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        _ensure_state(sp)
        r = flatten_all_positions(sp, hp, label=label(book), kl_cache=kl)
        results.append({"id": book["uid"], "name": book["name"], **r})
        total_closed += int(r.get("closed") or 0)
    try:
        write_snapshot("test", refresh_status_block(with_marks=False))
    except Exception:
        pass
    print(f"[Kripto Test] flatten → {total_closed} pozisyon kapandı")
    return {"ok": True, "results": results, "total_closed": total_closed}


def _apply_edge_gate(book: dict, cands: list[dict]) -> list[dict]:
    """PRO defterinde adayları ölçülen kenara göre süz ve kademe/süre işle.

    Kapıdan geçmeyen (defter, coin) hiç açılmaz — kripto kaybının kaynağı
    kenarı olmayan sinyalleri komisyon ödeyerek işlemekti.
  `gate_open()` açıksa filtre atlanır; PRO çıkış rejimi (saatlik kapanış yok) kalır.
    """
    if not is_pro(book):
        return cands
    if gate_open():
        out = []
        for c in cands:
            c = dict(c)
            c["max_hold_h"] = float(c.get("max_hold_h") or PRO_MAX_HOLD_HOURS)
            c["edge_tier"] = "open"
            out.append(c)
        return out
    out = []
    for c in cands:
        d = edge_decision(book["uid"], c["symbol"])
        if not d.get("allowed"):
            continue
        mult = float(d.get("size_mult") or 0)
        if mult <= 0:
            continue
        c = dict(c)
        c["margin_usd"] = round(MARGIN_USD * mult, 2)
        c["max_hold_h"] = float(d.get("hours") or PRO_MAX_HOLD_HOURS)
        c["edge_tier"] = d.get("tier")
        c["edge_skill_pct"] = d.get("skill_pct")
        c["edge_t"] = d.get("skill_t")
        c["edge_hours"] = d.get("hours")
        out.append(c)
    return out


def run_open() -> dict:
    skipped = _skip_weekend("open")
    if skipped:
        return skipped
    kl_1h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="1h")
    kl_4h = fetch_all_klines(TEST_SYMBOLS, limit=80, interval="4h")
    results = []
    gate_blocked = 0
    for book in ALL_BOOKS:
        sp, hp = _paths(book)
        _ensure_state(sp)
        st = load_state(sp)
        blocked = {str(s).upper() for s in (st.get("atr_skip_syms") or []) if s}
        st["atr_skip_syms"] = []
        save_state(sp, st)
        history = load_history(hp)
        cands = _build_candidates_for_book(book, kl_1h, kl_4h, history)
        for c in cands:
            c["algo"] = book["name"]
        if is_pro(book):
            n0 = len(cands)
            cands = _apply_edge_gate(book, cands)
            gate_blocked += n0 - len(cands)
        r = open_signals(
            sp, hp,
            label=label(book),
            candidates=cands,
            kl_cache={**{f"{s}|1h": kl_1h.get(s, []) for s in TEST_SYMBOLS},
                      **{f"{s}|4h": kl_4h.get(s, []) for s in TEST_SYMBOLS}},
            margin_usd=MARGIN_USD,
            leverage=LEVERAGE,
            max_opens=max_opens_for(book),
            blocked_syms=blocked,
            entry_price_mode="live",
        )
        results.append({
            "id": book["uid"],
            "name": book["name"],
            "opened": r.get("opened", 0),
            **r,
        })
    gs = edge_summary()
    print(
        f"[Kripto Test] open {len(ALL_BOOKS)} defter · ${MARGIN_USD:.0f}×{LEVERAGE}x "
        f"· max {MAX_OPEN_POSITIONS} (JARVIS_V1: 10) · 1h/4h ATR · "
        f"kenar kapısı: {gate_blocked} aday reddedildi, "
        f"{len(gs.get('allowed') or [])} çift izinli"
    )
    return {"ok": True, "results": results, "gate_blocked": gate_blocked}


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
        r = trail_positions(sp, hp, label=label(book), kl_cache=kl,
                            policy=EXIT_POLICY)
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
        if is_pro(book):
            # PRO'da saatlik close yok — süre sınırı bu turda da kontrol edilir
            reversed_syms = set(reversed_syms) | _pro_expired_symbols(st)
        r_close: dict = {"closed": 0, "closed_symbols": []}
        if reversed_syms:
            r_close = close_reversal_positions(
                sp, hp, label=label(book), reversed_symbols=reversed_syms, kl_cache=kl_cache,
            )
            total_closed += int(r_close.get("closed") or 0)

        st = load_state(sp)  # kapanış sonrası taze durum
        blocked = {str(s).upper() for s in (st.get("atr_skip_syms") or []) if s}
        slots_left = max_opens_for(book) - len(st.get("open_positions") or [])

        r_open: dict = {"opened": 0}
        if slots_left > 0:
            history = load_history(hp)
            cands = _build_candidates_for_book(book, kl_1h, kl_4h, history)
            for c in cands:
                c["algo"] = book["name"]
            if is_pro(book):
                cands = _apply_edge_gate(book, cands)
            r_open = open_signals(
                sp, hp,
                label=label(book),
                candidates=cands,
                kl_cache=kl_cache,
                margin_usd=MARGIN_USD,
                leverage=LEVERAGE,
                max_opens=max_opens_for(book),
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
    # PRO defterleri aynı motorun kopyası — konsensüsü ikiye katlamasınlar
    vote_books = [b for b in ALL_BOOKS if not is_pro(b)]
    for book in vote_books:
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
            "tier_label": f"{len(vote_books)} algo",
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
        st["max_opens"] = max_opens_for(book)
        st["open_active"] = True
        st["deposit"] = DEPOSIT
        if is_pro(book):
            st["mode"] = "pro"
            st["pro_of"] = book.get("pro_of")
            st["gate_open"] = gate_open()
            if gate_open():
                st["gate_pairs"] = [{"symbol": "all", "tier": "open"}]
            else:
                st["gate_pairs"] = [
                    r for r in (edge_summary().get("allowed") or [])
                    if r.get("uid") == book.get("pro_of")
                ]
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
        "edge_gate": edge_summary(),
        "pro_count": sum(1 for b in ALL_BOOKS if is_pro(b)),
    }


def status_block(*, with_marks: bool = True) -> dict:
    return cached_status("test", lambda: _build_status(with_marks=with_marks))


def refresh_status_block(*, with_marks: bool = True) -> dict:
    return refresh_status("test", lambda: _build_status(with_marks=with_marks))


def run_reset(*, balance: float = DEPOSIT, close_first: bool = True) -> dict:
    """Bakiyeyi sıfırla; geçmiş dosyalarına dokunma (analiz için korunur)."""
    if close_first:
        run_close()
    stamp = now_tr()
    results = []
    for book in ALL_BOOKS:
        sp, _hp = _paths(book)
        st = reset_book(sp, balance=balance)
        st["deposit"] = balance
        st["balance_reset_at_tr"] = stamp.isoformat()
        st["balance_reset_note"] = (
            f"Kripto Test bakiye reset ${balance:.0f} — geçmiş korundu"
        )
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
        "balance_reset_at_tr": stamp.isoformat(),
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
    p.add_argument("cmd", choices=["open", "close", "trail", "scan", "status", "reset", "flatten"])
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
    elif args.cmd == "flatten":
        r = run_flatten()
    else:
        r = status_block()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    try:
        write_snapshot("test", refresh_status_block(with_marks=True))
    except Exception:
        pass


if __name__ == "__main__":
    main()

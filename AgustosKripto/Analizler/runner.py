#!/usr/bin/env python3
"""Analizler — A1/A2/A3/A8/A4/A10/A6 sanal futures saatlik open/close.

  python3 AgustosKripto/Analizler/runner.py close
  python3 AgustosKripto/Analizler/runner.py open
  python3 AgustosKripto/Analizler/runner.py trail
  python3 AgustosKripto/Analizler/runner.py status
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGUSTOS = os.path.dirname(_DIR)
sys.path.insert(0, _AGUSTOS)
sys.path.insert(0, _DIR)

from virtual_book import (  # noqa: E402
    DEPOSIT,
    LEVERAGE,
    MARGIN_USD,
    MAX_OPENS_PER_HOUR,
    book_status,
    cached_status,
    close_all_positions,
    fetch_all_klines,
    in_weekend_pause_tr,
    load_state,
    open_signals,
    refresh_status,
    reset_book,
    trail_positions,
    write_snapshot,
)
from signals import (  # noqa: E402
    ANALIZ_META,
    clear_venv_cache,
    prefetch_a3_a8,
    resolve,
    supertrend_scored,
)

DATA = os.path.join(_DIR, "data")

# Analiz taraması — majors + likit altlar
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "NEARUSDT",
]

# Supertrend evreni — CR6 "İşlem Bekleyen" (momentum → alt). BTC/ETH yok.
ST_SYMBOLS = [
    "INJUSDT", "TIAUSDT", "ARBUSDT", "OPUSDT", "1000PEPEUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT",
    "BNBUSDT", "XRPUSDT",
    "SOLUSDT",  # yavaş — yalnızca yer kalırsa
]
# Yavaş — seçimde en son (BTC/ETH hiç girmez)
ST_SLOW = frozenset({"SOLUSDT"})

# Defter bazlı sizing — Supertrend (a6): $10 × 15x · max 4
BOOK_CFG: dict[str, dict] = {
    "a6": {"margin_usd": 10.0, "leverage": 15, "max_opens": 4},
}


def _paths(analiz_id: str) -> tuple[str, str]:
    return (
        os.path.join(DATA, f"{analiz_id}_state.json"),
        os.path.join(DATA, f"{analiz_id}_history.json"),
    )


def _cfg(analiz_id: str) -> dict:
    base = {
        "margin_usd": MARGIN_USD,
        "leverage": LEVERAGE,
        "max_opens": MAX_OPENS_PER_HOUR,
    }
    base.update(BOOK_CFG.get(analiz_id) or {})
    return base


def label(meta: dict) -> str:
    return f"{meta['name']} {meta['title']}"


def find_analiz(analiz_id: str) -> dict | None:
    key = str(analiz_id or "").lower().strip()
    for m in ANALIZ_META:
        mid = str(m["id"]).lower()
        name = str(m["name"]).lower()
        if key in (mid, name, f"a{mid.lstrip('a')}"):
            return m
    return None


def book_detail(analiz_id: str, *, recent_limit: int = 80, with_marks: bool = True) -> dict | None:
    """Tek analiz defteri — açık pozisyonlar + son kapanmış işlemler."""
    meta = find_analiz(analiz_id)
    if not meta:
        return None
    sp, hp = _paths(meta["id"])
    kl = {}
    if with_marks:
        opens = load_state(sp).get("open_positions") or []
        syms = sorted({p.get("symbol") for p in opens if p.get("symbol")})
        if syms:
            kl = fetch_all_klines(syms, limit=2)
    cfg = _cfg(meta["id"])
    st = book_status(
        sp, hp,
        label=label(meta),
        kl_cache=kl,
        live_marks=with_marks,
        recent_limit=recent_limit,
    )
    st["id"] = meta["id"]
    st["name"] = meta["name"]
    st["title"] = meta["title"]
    st["category"] = "Analizler"
    st["margin_usd"] = cfg["margin_usd"]
    st["leverage"] = cfg["leverage"]
    st["max_opens"] = cfg["max_opens"]
    st["deposit"] = DEPOSIT
    return st


def _pick(cands: list[dict], max_n: int = MAX_OPENS_PER_HOUR, *, by_score: bool = False) -> list[dict]:
    """by_score=True → en güçlü skor önce; değilse majors öncelik."""
    if by_score:
        cands = sorted(
            cands,
            key=lambda x: (-float(x.get("score") or 0), x["symbol"]),
        )
        return cands[:max_n]
    major = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    cands = sorted(cands, key=lambda x: (0 if x["symbol"] in major else 1, x["symbol"]))
    return cands[:max_n]


def _pick_supertrend(cands: list[dict], max_n: int = 4) -> list[dict]:
    """İşlem Bekleyen önceliği: önce hızlı alt/momentum (skor), BTC/ETH/SOL en son."""
    fast = [c for c in cands if c["symbol"] not in ST_SLOW]
    slow = [c for c in cands if c["symbol"] in ST_SLOW]
    fast.sort(key=lambda x: (-float(x.get("score") or 0), x["symbol"]))
    slow.sort(key=lambda x: (-float(x.get("score") or 0), x["symbol"]))
    picked = (fast + slow)[:max_n]
    return picked


def _skip_weekend(cmd: str) -> dict | None:
    if not in_weekend_pause_tr():
        return None
    print(f"[Analizler] hafta sonu — {cmd} skip (Cum 22:00 – Pzt 11:00 İST)")
    return {"ok": True, "skipped": "weekend_pause", "cmd": cmd, "results": []}


def run_close() -> dict:
    skipped = _skip_weekend("close")
    if skipped:
        return skipped
    scan_syms = list(dict.fromkeys(SYMBOLS + ST_SYMBOLS))
    kl = fetch_all_klines(scan_syms, limit=80)
    results = []
    for m in ANALIZ_META:
        sp, hp = _paths(m["id"])
        r = close_all_positions(sp, hp, label=label(m), kl_cache=kl)
        results.append({"id": m["id"], "name": m["name"], **r})
    return {"ok": True, "results": results}


def run_trail() -> dict:
    skipped = _skip_weekend("trail")
    if skipped:
        return skipped
    open_syms: set[str] = set()
    for m in ANALIZ_META:
        sp, _hp = _paths(m["id"])
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    scan_syms = list(dict.fromkeys(SYMBOLS + ST_SYMBOLS))
    kl = fetch_all_klines(sorted(open_syms) or scan_syms[:1], limit=80) if open_syms else {}
    results = []
    for m in ANALIZ_META:
        sp, hp = _paths(m["id"])
        r = trail_positions(sp, hp, label=label(m), kl_cache=kl)
        results.append({"id": m["id"], "name": m["name"], **r})
    return {"ok": True, "results": results}


def run_open() -> dict:
    skipped = _skip_weekend("open")
    if skipped:
        return skipped
    scan_syms = list(dict.fromkeys(SYMBOLS + ST_SYMBOLS))
    kl = fetch_all_klines(scan_syms, limit=80)
    # A3/A8 sistem python'da talib/jesse yok — freqtrade/jesse .venv üzerinden
    clear_venv_cache()
    prefetch_a3_a8(SYMBOLS)
    results = []
    for m in ANALIZ_META:
        sp, hp = _paths(m["id"])
        universe = ST_SYMBOLS if m["id"] == "a6" else SYMBOLS
        cands = []
        for sym in universe:
            bars = kl.get(sym) or []
            if m["id"] == "a6":
                d, sc = supertrend_scored(bars)
            else:
                d = resolve(m["id"], sym, bars)
                sc = 1.0
            if d not in ("UP", "DOWN"):
                continue
            cands.append({
                "symbol": sym,
                "side": "LONG" if d == "UP" else "SHORT",
                "signal": d,
                "algo": m["name"],
                "score": float(sc),
                "slow": sym in ST_SLOW,
            })
        cfg = _cfg(m["id"])
        if m["id"] == "a6":
            cands = _pick_supertrend(cands, max_n=int(cfg["max_opens"]))
            if cands:
                print(
                    "[Supertrend] top4 (alt önce, SOL son; BTC/ETH yok):",
                    ", ".join(
                        f"{c['symbol']} {c['side']} sc={c['score']:.2f}"
                        + ("*" if c.get("slow") else "")
                        for c in cands
                    ),
                )
        else:
            cands = _pick(cands, max_n=int(cfg["max_opens"]))
        r = open_signals(
            sp, hp, label=label(m), candidates=cands, kl_cache=kl,
            margin_usd=float(cfg["margin_usd"]),
            leverage=int(cfg["leverage"]),
            max_opens=int(cfg["max_opens"]),
        )
        results.append({"id": m["id"], "name": m["name"], **r})
    clear_venv_cache()
    return {"ok": True, "results": results}


def _build_status(*, with_marks: bool = True) -> dict:
    open_syms: set[str] = set()
    for m in ANALIZ_META:
        sp, _hp = _paths(m["id"])
        for p in (load_state(sp).get("open_positions") or []):
            if p.get("symbol"):
                open_syms.add(p["symbol"])
    kl = fetch_all_klines(sorted(open_syms), limit=2) if with_marks and open_syms else {}
    books = []
    tot_bal = 0.0
    tot_pnl = 0.0
    tot_open = 0
    for m in ANALIZ_META:
        sp, hp = _paths(m["id"])
        cfg = _cfg(m["id"])
        st = book_status(
            sp, hp, label=label(m), kl_cache=kl, live_marks=with_marks,
        )
        st["id"] = m["id"]
        st["name"] = m["name"]
        st["title"] = m["title"]
        st["margin_usd"] = cfg["margin_usd"]
        st["leverage"] = cfg["leverage"]
        st["max_opens"] = cfg["max_opens"]
        books.append(st)
        tot_bal += float(st.get("balance") or 0)
        tot_pnl += float(st.get("total_pnl") or 0)
        tot_open += int(st.get("open_count") or 0)
    return {
        "ok": True,
        "kind": "analizler",
        "count": len(books),
        "margin_usd": 15,
        "leverage": 15,
        "deposit_each": 300,
        "max_opens": MAX_OPENS_PER_HOUR,
        "total_balance": round(tot_bal, 2),
        "total_pnl": round(tot_pnl, 4),
        "total_open": tot_open,
        "books": books,
    }


def status_block(*, with_marks: bool = True) -> dict:
    return cached_status("analizler", lambda: _build_status(with_marks=with_marks))


def refresh_status_block(*, with_marks: bool = True) -> dict:
    return refresh_status("analizler", lambda: _build_status(with_marks=with_marks))


def run_reset(*, balance: float = DEPOSIT) -> dict:
    """Tüm analiz defterlerini kapat + bakiyeyi $300'e çek."""
    results = []
    for m in ANALIZ_META:
        sp, _hp = _paths(m["id"])
        st = reset_book(sp, balance=balance)
        results.append({
            "id": m["id"],
            "name": m["name"],
            "balance": st.get("balance"),
            "open_count": 0,
        })
    out = {
        "ok": True,
        "kind": "analizler",
        "reset_balance": float(balance),
        "count": len(results),
        "results": results,
    }
    try:
        write_snapshot("analizler", refresh_status_block(with_marks=False))
    except Exception:
        pass
    print(f"[Analizler] reset → ${balance:.0f} × {len(results)} defter")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="AgustosKripto Analizler sanal runner")
    p.add_argument("cmd", choices=["open", "close", "trail", "status", "reset"])
    args = p.parse_args()
    if args.cmd == "open":
        r = run_open()
    elif args.cmd == "close":
        r = run_close()
    elif args.cmd == "trail":
        r = run_trail()
    elif args.cmd == "reset":
        r = run_reset()
    else:
        r = status_block()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

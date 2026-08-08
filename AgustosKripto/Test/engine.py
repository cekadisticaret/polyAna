#!/usr/bin/env python3
"""Kripto Test — 1h/4h seçimi, aday sıralama, kline cache, ters sinyal kontrolü."""
from __future__ import annotations

import os

from virtual_book import fetch_all_klines, fetch_klines, _pos_interval, position_age_minutes

MIN_TF_TRADES = 2
# Ters sinyal gelse de bu süre dolmadan pozisyon kapatılmaz — flip-flop / gürültü koruması.
MIN_HOLD_MINUTES = float(os.environ.get("KRIPTO_TEST_MIN_HOLD_MIN", "15"))


def _tf_stats(history: list, symbol: str, tf: str) -> tuple[float, float, int]:
    sym = symbol.upper()
    trades = [
        t for t in history
        if (t.get("symbol") or "").upper() == sym
        and (t.get("interval") or "1h") == tf
    ]
    n = len(trades)
    if n == 0:
        return 0.0, 0.0, 0
    wins = sum(1 for t in trades if t.get("win"))
    pnl = sum(float(t.get("pnl") or 0) for t in trades)
    return wins / n, pnl, n


def _tf_score(wr: float, pnl: float, n: int) -> float:
    if n < MIN_TF_TRADES:
        return -1.0
    return wr * 100.0 + min(max(pnl, -20.0), 20.0) * 0.5


def choose_timeframe(
    symbol: str,
    sig_1h: str,
    sig_4h: str,
    history: list,
) -> tuple[str, str]:
    """Geçmiş performansa göre 1h veya 4h; yoksa sinyal olan TF."""
    w1, p1, n1 = _tf_stats(history, symbol, "1h")
    w4, p4, n4 = _tf_stats(history, symbol, "4h")
    sc1, sc4 = _tf_score(w1, p1, n1), _tf_score(w4, p4, n4)
    if sc4 > sc1 and sig_4h in ("UP", "DOWN"):
        return "4h", sig_4h
    if sc4 == sc1 and sc4 > 0 and sig_4h in ("UP", "DOWN"):
        if p4 > p1 or (p4 == p1 and sig_4h in ("UP", "DOWN")):
            return "4h", sig_4h
    if sig_1h in ("UP", "DOWN"):
        return "1h", sig_1h
    if sig_4h in ("UP", "DOWN"):
        return "4h", sig_4h
    return "1h", "NEUTRAL"


def build_candidates(
    book: dict,
    kl_1h: dict[str, list],
    kl_4h: dict[str, list],
    history: list,
    *,
    symbols: list[str],
    signal_for_book,
) -> list[dict]:
    sig1 = signal_for_book(book, kl_1h)
    sig4 = signal_for_book(book, kl_4h)
    rows: list[dict] = []
    for sym in symbols:
        tf, sig = choose_timeframe(
            sym,
            sig1.get(sym, "NEUTRAL"),
            sig4.get(sym, "NEUTRAL"),
            history,
        )
        if sig not in ("UP", "DOWN"):
            continue
        wr, pnl, n = _tf_stats(history, sym, tf)
        score = _tf_score(wr, pnl, n) if n >= MIN_TF_TRADES else 50.0
        rows.append({
            "symbol": sym,
            "side": "LONG" if sig == "UP" else "SHORT",
            "signal": sig,
            "score": round(score, 2),
            "interval": tf,
        })
    rows.sort(key=lambda x: (-x["score"], x["symbol"]))
    return rows


def find_reversal_closes(
    book: dict,
    open_positions: list[dict],
    kl_1h: dict[str, list],
    kl_4h: dict[str, list],
    *,
    signal_for_book,
    min_hold_minutes: float = MIN_HOLD_MINUTES,
) -> set[str]:
    """LONG'ta iken gerçek DOWN, SHORT'ta iken gerçek UP sinyali geldiyse kapatılacak semboller.

    - NEUTRAL asla tetiklemez (gürültüyle karıştırılmaz).
    - min_hold_minutes dolmadan pozisyon dokunulmaz (21:34 açılıp 21:35 kapanmasın).
    - Sinyal, pozisyonun açıldığı zaman dilimiyle (1h/4h) tutarlı okunur.
    """
    if not open_positions:
        return set()
    sig1 = None
    sig4 = None
    out: set[str] = set()
    for pos in open_positions:
        sym = (pos.get("symbol") or "").upper()
        side = pos.get("side")
        if not sym or side not in ("LONG", "SHORT"):
            continue
        if position_age_minutes(pos) < min_hold_minutes:
            continue
        iv = _pos_interval(pos)
        if iv == "4h":
            if sig4 is None:
                sig4 = signal_for_book(book, kl_4h)
            cur = sig4.get(sym, "NEUTRAL")
        else:
            if sig1 is None:
                sig1 = signal_for_book(book, kl_1h)
            cur = sig1.get(sym, "NEUTRAL")
        if cur not in ("UP", "DOWN"):
            continue  # NEUTRAL / veri yok — kapatma
        if side == "LONG" and cur == "DOWN":
            out.add(sym)
        elif side == "SHORT" and cur == "UP":
            out.add(sym)
    return out


def klines_for_positions(positions: list[dict], *, limit: int = 80) -> dict[str, list]:
    """close/trail için {symbol|interval: klines}."""
    by_iv: dict[str, list[str]] = {}
    for pos in positions:
        sym = pos.get("symbol")
        if not sym:
            continue
        iv = _pos_interval(pos)
        by_iv.setdefault(iv, [])
        if sym not in by_iv[iv]:
            by_iv[iv].append(sym)
    cache: dict[str, list] = {}
    for iv, syms in by_iv.items():
        kl_map = fetch_all_klines(syms, limit=limit, interval=iv)
        for sym, kl in kl_map.items():
            cache[f"{sym}|{iv}"] = kl
    return cache


def all_open_positions(books, paths_fn, load_state) -> list[dict]:
    out: list[dict] = []
    for book in books:
        sp, _hp = paths_fn(book)
        out.extend(load_state(sp).get("open_positions") or [])
    return out

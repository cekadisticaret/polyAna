#!/usr/bin/env python3
"""Kripto Test — 59 defter × 30 coin, 1Y saatlik futures simülasyonu.

Test runner ile aynı parametreler: $1000 deposit, $100×6x, max 4 pozisyon.
Her saat: sinyal → en iyi 4 aday aç → 1 saat tut → kapat (komisyon dahil net PnL).

Canlı API gerektirenler (B1#01/02, A6V3) OHLCV proxy; A1#20 OI / A1#21 F&G atlanır.

  python3 AgustosKripto/Test/backtest_1y.py
  python3 AgustosKripto/Test/backtest_1y.py --days 365 --workers 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_DIR))
_POLY = os.path.join(_ROOT, "temmuzPoly")
_AGUSTOS = os.path.join(_ROOT, "AgustosKripto")
for p in (_DIR, _POLY, _AGUSTOS):
    if p not in sys.path:
        sys.path.insert(0, p)

from backtest_analiz2 import fetch_klines_history  # noqa: E402

# Canlı API çağrılarını backtest'te kapat
import signals as _tsig  # noqa: E402

_A6V3_PROXY = _tsig._poly_analiz6


def _poly_b1_backtest(source_key: str, kl_by_symbol: dict) -> dict:
    return {sym: "NEUTRAL" for sym in kl_by_symbol}


def _poly_a6v3_backtest(kl_by_symbol: dict) -> dict:
    limited = {s: kl for s, kl in kl_by_symbol.items() if s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
    return _A6V3_PROXY("analiz6_v2", limited) if limited else {}


_tsig._poly_b1 = _poly_b1_backtest
_tsig._poly_analiz6_v3 = _poly_a6v3_backtest

import importlib.util as _ilu

_cat_spec = _ilu.spec_from_file_location("kripto_test_catalog", os.path.join(_DIR, "catalog.py"))
_cat = _ilu.module_from_spec(_cat_spec)
assert _cat_spec.loader is not None
_cat_spec.loader.exec_module(_cat)
ALL_BOOKS = _cat.ALL_BOOKS
TEST_SYMBOLS = _cat.TEST_SYMBOLS

import engine as _engine_mod  # noqa: E402
from engine import build_candidates  # noqa: E402
from signals import signal_for_book  # noqa: E402
from atr_profit_lock import (  # noqa: E402
    atr_from_klines,
    atr_usd as _atr_usd_fn,
    loss_stop_threshold as _loss_stop_threshold,
    update_lock as _update_lock,
)

DEPOSIT = 1000.0
MARGIN_USD = 100.0
LEVERAGE = 6
MAX_OPEN = 4
FEE_RATE = 0.0005
WARMUP = 80
WINDOW_1H = 260  # indikatör lookback için yeterli; O(n^2) tam-geçmiş slice'ı önler
WINDOW_4H_SRC = WINDOW_1H * 4
CACHE_DIR = os.path.join(_DIR, "data", "backtest_cache")
OUT_DEFAULT = os.path.join(_DIR, "data", "backtest_1y_results.json")


def _resample_4h(bars_1h: list[dict]) -> list[dict]:
    out = []
    bucket = []
    for b in bars_1h:
        bucket.append(b)
        if len(bucket) == 4:
            out.append({
                "o": bucket[0]["open"], "h": max(x["high"] for x in bucket),
                "l": min(x["low"] for x in bucket), "c": bucket[-1]["close"],
                "v": sum(x["volume"] for x in bucket),
                "open": bucket[0]["open"], "high": max(x["high"] for x in bucket),
                "low": min(x["low"] for x in bucket), "close": bucket[-1]["close"],
                "volume": sum(x["volume"] for x in bucket),
            })
            bucket = []
    return out


def _to_vb(bars: list[dict]) -> list[dict]:
    return [
        {
            "o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"],
            "v": b["volume"], "open": b["open"], "high": b["high"],
            "low": b["low"], "close": b["close"], "volume": b["volume"],
        }
        for b in bars
    ]


def _trade_pnl(side: str, entry: float, exit_px: float) -> tuple[float, float, float]:
    notional = MARGIN_USD * LEVERAGE
    qty = notional / entry if entry else 0.0
    if side == "LONG":
        gross = (exit_px - entry) * qty
    else:
        gross = (entry - exit_px) * qty
    comm = notional * FEE_RATE + exit_px * qty * FEE_RATE
    return round(gross - comm, 4), round(gross, 4), round(comm, 4)


def _book_label(book: dict) -> str:
    return book.get("name") or book.get("uid") or "?"


def simulate_book(
    book: dict,
    bars_1h: dict[str, list[dict]],
    master_times: list[int],
    time_index: dict[str, dict[int, int]],
    test_start_ms: int,
) -> dict:
    """Tek defter — saatlik portföy sim + ATR kâr kilidi / zarar stop (gerçek sisteme yakın).

    Her saat: açık pozisyonların o saatlik bar high/low'u ile ATR kilidi güncellenir;
    kilit tetiklenirse (trail stop) veya zarar stop'a değerse o saat kapanır; kilit
    devredeyken (stop_level>=1) ve net kâr pozitifse pozisyon "runner" olarak bir sonraki
    saate taşınır (saatlik zorla kapatma atlanır) — production'daki should_skip_hourly_close
    ile aynı mantık.
    """
    history: list[dict] = []
    opens: list[dict] = []
    total_pnl = 0.0
    wins = 0
    n = len(master_times)

    # engine._tf_stats her çağrıda tüm history'yi O(n) tarıyor; işlem sayısı
    # yıl boyunca binlere çıktığında bu, saatlik döngüde ciddi bir darboğaza
    # dönüşüyor. Süreç-yerel (process-local) artımlı bir önbellekle değiştir —
    # yalnızca bu simulate_book çağrısı süresince geçerli, production'a dokunmaz.
    _tf_bucket: dict[tuple[str, str], list] = {}
    _tf_seen_len = [0]

    def _fast_tf_stats(hist_arg: list, symbol: str, tf: str) -> tuple[float, float, int]:
        if _tf_seen_len[0] < len(hist_arg):
            for t in hist_arg[_tf_seen_len[0]:]:
                tsym = (t.get("symbol") or "").upper()
                tivl = t.get("interval") or "1h"
                b = _tf_bucket.setdefault((tsym, tivl), [0, 0, 0.0])
                b[1] += 1
                if t.get("win"):
                    b[0] += 1
                b[2] += float(t.get("pnl") or 0)
            _tf_seen_len[0] = len(hist_arg)
        b = _tf_bucket.get((symbol.upper(), tf))
        if not b or b[1] == 0:
            return 0.0, 0.0, 0
        bw, bn, bp = b
        return bw / bn, bp, bn

    _orig_tf_stats = _engine_mod._tf_stats
    _engine_mod._tf_stats = _fast_tf_stats

    for idx in range(WARMUP, n - 1):
        t_close = master_times[idx]
        t_next = master_times[idx + 1]
        if t_next < test_start_ms:
            continue

        still_open: list[dict] = []
        for pos in opens:
            sym = pos["symbol"]
            side = pos["side"]
            entry = pos["entry_price"]
            bi = time_index.get(sym, {}).get(t_next)
            if bi is None:
                still_open.append(pos)
                continue
            bar = bars_1h[sym][bi]
            high, low, close_px = bar["high"], bar["low"], bar["close"]
            fav_px, adv_px = (high, low) if side == "LONG" else (low, high)
            net_fav, _, _ = _trade_pnl(side, entry, fav_px)
            net_adv, _, _ = _trade_pnl(side, entry, adv_px)
            net_close, gross_close, comm_close = _trade_pnl(side, entry, close_px)

            pos, _ = _update_lock(pos, net_fav, ts=None, mark=fav_px)
            stop_level = int(pos.get("stop_level") or 0)

            realized_net = None
            exit_reason = None
            exit_px = close_px
            if stop_level >= 1:
                stop_upnl = pos.get("stop_upnl")
                if stop_upnl is not None and net_adv <= float(stop_upnl):
                    realized_net = float(stop_upnl)
                    exit_reason = "atr_stop"
            else:
                lim = _loss_stop_threshold(pos)
                if lim is not None and net_adv <= lim:
                    realized_net = float(lim)
                    exit_reason = "atr_loss"

            if realized_net is None:
                if stop_level >= 1 and net_close > 0:
                    still_open.append(pos)  # runner — saatlik kapanışı atla
                    continue
                realized_net = net_close
                exit_reason = "hourly"

            win = realized_net >= 0
            if win:
                wins += 1
            total_pnl += realized_net
            history.append({
                **pos,
                "exit_price": exit_px,
                "pnl": round(realized_net, 4),
                "win": win,
                "close_reason": exit_reason,
            })
        opens = still_open

        # Yeni sinyaller (bar idx kapanışına kadar)
        kl_1h: dict[str, list] = {}
        kl_4h: dict[str, list] = {}
        for sym in TEST_SYMBOLS:
            bi = time_index.get(sym, {}).get(t_close)
            if bi is None or bi < 30:
                continue
            lo1 = max(0, bi + 1 - WINDOW_1H)
            slice_1h = bars_1h[sym][lo1: bi + 1]
            kl_1h[sym] = _to_vb(slice_1h)
            lo4 = max(0, bi + 1 - WINDOW_4H_SRC)
            slice_4h_src = bars_1h[sym][lo4: bi + 1]
            kl_4h[sym] = _resample_4h(slice_4h_src)

        if not kl_1h:
            continue

        try:
            cands = build_candidates(
                book, kl_1h, kl_4h, history,
                symbols=TEST_SYMBOLS,
                signal_for_book=signal_for_book,
            )
        except Exception as e:
            return {
                "book": _book_label(book),
                "uid": book.get("uid"),
                "error": str(e),
                "total_pnl": round(total_pnl, 2),
                "trades": len(history),
                "wins": wins,
            }

        held_syms = {p["symbol"] for p in opens}
        seen = set()
        for c in cands:
            if len(opens) >= MAX_OPEN:
                break
            sym = c["symbol"]
            if sym in seen or sym in held_syms:
                continue
            bi = time_index.get(sym, {}).get(t_close)
            if bi is None:
                continue
            entry = bars_1h[sym][bi]["close"]
            atr_val = atr_from_klines(kl_1h.get(sym) or [], period=14)
            a_usd = _atr_usd_fn(MARGIN_USD, LEVERAGE, entry, atr_val) if atr_val else 0.0
            opens.append({
                "symbol": sym,
                "side": c["side"],
                "signal": c["signal"],
                "interval": c.get("interval") or "1h",
                "entry_price": entry,
                "margin_usd": MARGIN_USD,
                "leverage": LEVERAGE,
                "atr": atr_val,
                "atr_usd": a_usd,
                "peak_upnl": 0.0,
                "stop_upnl": None,
                "stop_level": 0,
                "lock_armed": False,
            })
            seen.add(sym)

    _engine_mod._tf_stats = _orig_tf_stats
    wr = round(100.0 * wins / len(history), 1) if history else None
    return {
        "book": _book_label(book),
        "uid": book.get("uid"),
        "source": book.get("source"),
        "title": book.get("title"),
        "total_pnl": round(total_pnl, 2),
        "trades": len(history),
        "wins": wins,
        "wr": wr,
        "deposit": DEPOSIT,
        "final_balance": round(DEPOSIT + total_pnl, 2),
        "profitable": total_pnl > 0,
    }


def _load_cache(sym: str) -> list[dict] | None:
    path = os.path.join(CACHE_DIR, f"{sym}_1h.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(sym: str, bars: list[dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, f"{sym}_1h.json"), "w") as f:
        json.dump(bars, f)


async def _fetch_all(symbols: list[str], fetch_ms: int, end_ms: int) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for sym in symbols:
        cached = _load_cache(sym)
        if cached and len(cached) > 500:
            print(f"  cache {sym}: {len(cached)} bar", flush=True)
            out[sym] = cached
            continue
        print(f"  fetch {sym}...", flush=True)
        bars = await fetch_klines_history(sym, "1h", fetch_ms, end_ms)
        print(f"    {len(bars)} bar", flush=True)
        _save_cache(sym, bars)
        out[sym] = bars
    return out


def _build_time_index(bars_1h: dict[str, list[dict]]) -> tuple[list[int], dict[str, dict[int, int]]]:
    master = bars_1h.get("BTCUSDT") or next(iter(bars_1h.values()))
    master_times = [b["open_time"] for b in master]
    time_index: dict[str, dict[int, int]] = {}
    for sym, bars in bars_1h.items():
        time_index[sym] = {b["open_time"]: i for i, b in enumerate(bars)}
    return master_times, time_index


def _run_one(args: tuple) -> dict:
    book, bars_1h, master_times, time_index, test_start_ms = args
    return simulate_book(book, bars_1h, master_times, time_index, test_start_ms)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--out", default=OUT_DEFAULT)
    p.add_argument(
        "--source", default="all",
        choices=["all", "islemler_a2", "islemler_poly", "algo1"],
        help="Yalnızca bu kaynaktan defterleri test et (ör. islemler_a2 = A2 Top-17)",
    )
    args = p.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    fetch_start = start - timedelta(days=12)
    test_start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    fetch_ms = int(fetch_start.timestamp() * 1000)

    src_books = ALL_BOOKS if args.source == "all" else [b for b in ALL_BOOKS if b.get("source") == args.source]
    print(f"Kripto Test 1Y backtest — {args.days}g · {len(src_books)} defter ({args.source}) · {len(TEST_SYMBOLS)} coin")
    print(f"Dönem: {start.date()} → {end.date()}")
    print(f"Param: ${MARGIN_USD:.0f}×{LEVERAGE}x · max {MAX_OPEN} · komisyon {FEE_RATE*100:.2f}%/yön\n")

    t0 = time.time()
    bars_1h = asyncio.run(_fetch_all(TEST_SYMBOLS, fetch_ms, end_ms))
    master_times, time_index = _build_time_index(bars_1h)
    print(f"\nVeri hazır ({time.time()-t0:.0f}s). Simülasyon başlıyor...\n")

    # A1#20 OI / A1#21 F&G — canlı veri; backtest'te nötr
    books = [
        b for b in src_books
        if not (b.get("source") == "algo1" and b.get("kind") in ("oi", "fear_greed"))
    ]
    skipped = [b for b in src_books if b not in books]

    job_args = [
        (book, bars_1h, master_times, time_index, test_start_ms)
        for book in books
    ]
    results: list[dict] = []
    if args.workers <= 1:
        for i, ja in enumerate(job_args, 1):
            r = _run_one(ja)
            results.append(r)
            print(f"  [{i}/{len(job_args)}] {r['book']}: ${r.get('total_pnl',0):+.2f} · {r.get('trades',0)} işlem", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(_run_one, ja): ja[0] for ja in job_args}
            done = 0
            for fut in as_completed(futs):
                done += 1
                r = fut.result()
                results.append(r)
                print(f"  [{done}/{len(job_args)}] {r['book']}: ${r.get('total_pnl',0):+.2f} · {r.get('trades',0)} işlem", flush=True)

    results.sort(key=lambda x: (-(x.get("total_pnl") or 0), -(x.get("trades") or 0)))
    profitable = [r for r in results if r.get("profitable")]
    losers = [r for r in results if not r.get("profitable") and not r.get("error")]

    payload = {
        "ok": True,
        "period_days": args.days,
        "period_start": start.date().isoformat(),
        "period_end": end.date().isoformat(),
        "symbols": TEST_SYMBOLS,
        "params": {
            "deposit": DEPOSIT,
            "margin_usd": MARGIN_USD,
            "leverage": LEVERAGE,
            "max_open": MAX_OPEN,
            "fee_rate": FEE_RATE,
        },
        "books_tested": len(results),
        "books_skipped": [_book_label(b) for b in skipped],
        "profitable_count": len(profitable),
        "profitable": profitable,
        "all_results": results,
        "note": (
            "Saatlik portföy sim: sinyal → max 4 pozisyon → ATR kâr kilidi (arm 1.7×ATR$, "
            "trail 1.0×, zarar stop 2.0×ATR$) + saatlik kapanış (kilit yoksa). "
            "B1#01/02 nötr; A6V3 BTC/ETH/SOL proxy; A1#20/#21 atlandı."
        ),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 64)
    print(f"  KÂRDA (+) KAPATAN ALGORİTMALAR — {len(profitable)} / {len(results)}")
    print("=" * 64)
    for i, r in enumerate(profitable, 1):
        wr = r.get("wr")
        wr_s = f"{wr:.1f}%" if wr is not None else "—"
        print(
            f"  {i:2d}. {r['book']:<10}  net ${r['total_pnl']:>+8.2f}  "
            f"{r.get('trades', 0):>4} işlem  WR {wr_s}"
        )
    print("=" * 64)
    print(f"Zararda: {len(losers)} · Atlanan: {len(skipped)} · Süre: {payload['elapsed_sec']}s")
    print(f"Kayıt: {args.out}")


if __name__ == "__main__":
    main()

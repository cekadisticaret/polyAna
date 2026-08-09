#!/usr/bin/env python3
"""Tutma süresi taraması — sinyalin ham tahmin gücü, portföy mekaniği olmadan.

Soru: komisyon işlem sayısıyla sabit (%0,10 gidiş-dönüş), edge ise tutma
süresiyle büyüyebilir. Saatlik zorunlu kapanış yerine 4/8/24 saat tutulsa
edge maliyeti aşar mı?

Portföy yok, ATR yok, pozisyon limiti yok. Sadece: sinyal ateşlendi →
h saat sonra ortalama imzalı getiri ne? Aynı anda çok sayıda coin benzer
hareket ettiği için standart hata saat bazlı kümelenerek hesaplanır.

  python3 AgustosKripto/Test/horizon_sweep.py --books analiz1,analiz6
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import backtest_1y as bt  # noqa: E402
import backtest_fast as bf  # noqa: E402

HORIZONS = (1, 2, 4, 8, 24)
ROUND_TRIP_FEE = 0.0010  # $100×6x, taker %0,05 × 2 yön
OUT_DEFAULT = os.path.join(_DIR, "data", "horizon_sweep.json")

_G: dict = {}


def _cluster_stats(x: np.ndarray, ts: np.ndarray) -> tuple[float, float, float]:
    """Saat bazlı kümelenmiş ortalama / standart hata / t."""
    if x.size == 0:
        return 0.0, 0.0, 0.0
    u, inv = np.unique(ts, return_inverse=True)
    sums = np.bincount(inv, weights=x)
    cnts = np.bincount(inv)
    g = sums / cnts
    if g.size < 2:
        return float(g.mean()), 0.0, 0.0
    se = float(g.std(ddof=1) / np.sqrt(g.size))
    mu = float(g.mean())
    return mu, se, (mu / se if se > 0 else 0.0)


def sweep_book(book: dict, bars_1h, master_times, time_index, pre, step: int) -> dict:
    from signals import signal_for_book

    maxh = max(HORIZONS)
    closes = {s: np.array([b["close"] for b in bars], dtype=np.float64)
              for s, bars in bars_1h.items()}

    ts_rec: list[int] = []
    ret_rec: list[list[float]] = []
    n = len(master_times)

    for idx in range(bt.WARMUP, n - maxh - 1):
        if (idx - bt.WARMUP) % step:
            continue
        t_close = master_times[idx]
        kl_1h = {}
        bis = {}
        for sym in bt.TEST_SYMBOLS:
            bi = time_index.get(sym, {}).get(t_close)
            if bi is None or bi < 30 or bi + maxh >= len(closes[sym]):
                continue
            kl_1h[sym] = pre["ohlc1"][sym][max(0, bi + 1 - bt.WINDOW_1H):bi + 1]
            bis[sym] = bi
        if not kl_1h:
            continue
        try:
            sigs = signal_for_book(book, kl_1h)
        except Exception as e:
            return {"book": bt._book_label(book), "uid": book.get("uid"), "error": str(e)}

        for sym, s in sigs.items():
            if s not in ("UP", "DOWN"):
                continue
            bi = bis.get(sym)
            if bi is None:
                continue
            c = closes[sym]
            p0 = c[bi]
            if p0 <= 0:
                continue
            sign = 1.0 if s == "UP" else -1.0
            ts_rec.append(t_close)
            ret_rec.append([float((c[bi + h] - p0) / p0 * sign) for h in HORIZONS])

    if not ret_rec:
        return {"book": bt._book_label(book), "uid": book.get("uid"), "signals": 0}

    ts = np.array(ts_rec, dtype=np.int64)
    R = np.array(ret_rec, dtype=np.float64)
    rows = []
    for i, h in enumerate(HORIZONS):
        mu, se, t = _cluster_stats(R[:, i], ts)
        rows.append({
            "hours": h,
            "gross_pct": round(mu * 100, 4),
            "se_pct": round(se * 100, 4),
            "t": round(t, 2),
            "net_pct": round((mu - ROUND_TRIP_FEE) * 100, 4),
            "beats_fee": bool(mu > ROUND_TRIP_FEE),
        })
    return {
        "book": bt._book_label(book), "uid": book.get("uid"),
        "signals": int(R.shape[0]), "hours_sampled": int(np.unique(ts).size),
        "horizons": rows,
    }


def _init(step: int) -> None:
    bars = {}
    for s in bt.TEST_SYMBOLS:
        b = bt._load_cache(s)
        if b:
            bars[s] = b
    mt, ti = bt._build_time_index(bars)
    _G.update(bars=bars, mt=mt, ti=ti, pre=bf.precompute(bars), step=step)


def _run(book: dict) -> dict:
    return sweep_book(book, _G["bars"], _G["mt"], _G["ti"], _G["pre"], _G["step"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--books", default="analiz1,analiz6,analiz6_v2,analiz6_v3")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--step", type=int, default=1, help="kaç saatte bir örnekle")
    p.add_argument("--out", default=OUT_DEFAULT)
    args = p.parse_args()

    want = {x.strip().lower() for x in args.books.split(",") if x.strip()}
    books = [b for b in bt.ALL_BOOKS
             if (b.get("uid") or "").lower() in want or (b.get("name") or "").lower() in want]
    if not books:
        print("Eşleşen defter yok.")
        return

    print(f"Tutma süresi taraması — {len(books)} defter · 30 coin · ufuk {HORIZONS}")
    print(f"Komisyon eşiği: %{ROUND_TRIP_FEE*100:.2f} (gidiş-dönüş)\n")

    t0 = time.time()
    results = []
    if args.workers <= 1:
        _init(args.step)
        for b in books:
            results.append(_run(b))
    else:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_init,
                                 initargs=(args.step,)) as ex:
            futs = {ex.submit(_run, b): b for b in books}
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                print(f"  {r.get('book')}: {r.get('signals', 0)} sinyal · {time.time()-t0:.0f}s",
                      flush=True)

    print()
    for r in sorted(results, key=lambda x: x.get("book") or ""):
        if r.get("error") or not r.get("horizons"):
            print(f"{r.get('book')}: {r.get('error') or 'sinyal yok'}")
            continue
        print(f"── {r['book']} · {r['signals']:,} sinyal ".ljust(60, "─"))
        print(f"{'saat':>6} {'brüt':>10} {'SE':>9} {'t':>7} {'komisyon sonrası':>18}")
        for h in r["horizons"]:
            mark = "  ✓ AŞIYOR" if h["beats_fee"] else ""
            print(f"{h['hours']:6} {h['gross_pct']:9.4f}% {h['se_pct']:8.4f}% "
                  f"{h['t']:7.2f} {h['net_pct']:17.4f}%{mark}")
        print()

    payload = {"ok": True, "horizons": list(HORIZONS), "round_trip_fee": ROUND_TRIP_FEE,
               "results": results, "elapsed_sec": round(time.time() - t0, 1)}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Süre: {payload['elapsed_sec']}s · Kayıt: {args.out}")


if __name__ == "__main__":
    main()

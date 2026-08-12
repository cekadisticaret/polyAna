#!/usr/bin/env python3
"""Tutma süresi taraması — sinyalin ham tahmin gücü, portföy mekaniği olmadan.

Soru: komisyon işlem sayısıyla sabit (%0,10 gidiş-dönüş), edge ise tutma
süresiyle büyüyebilir. Saatlik zorunlu kapanış yerine 4/8/24 saat tutulsa
edge maliyeti aşar mı?

Portföy yok, ATR yok, pozisyon limiti yok. Sadece: sinyal ateşlendi →
h saat sonra ortalama imzalı getiri ne? Standart hata **ufuk boyunda bloklara**
kümelenerek hesaplanır: aynı anda çok sayıda coin benzer hareket ediyor (yatay
bağımlılık) ve 24–48s ufukta ardışık örneklerin sonuç pencereleri örtüşüyor
(dikey bağımlılık). İkisi de düzeltilmezse t 2–3 kat şişer.

Ham brüt getirinin yanında **drift-nötr SKILL** = (ort. LONG + ort. SHORT)/2
raporlanır; örneklem dönemindeki piyasa yönü sıralamaya karışmasın.

  python3 AgustosKripto/Test/horizon_sweep.py --books analiz1,analiz6
  python3 AgustosKripto/Test/horizon_sweep.py --per-symbol --symbols BTCUSDT
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

HORIZONS = (1, 2, 4, 8, 12, 24, 48)
ROUND_TRIP_FEE = 0.0010  # $100×6x, taker %0,05 × 2 yön
MAKER_ROUND_TRIP_FEE = 0.0004  # limit emir %0,02 × 2 yön
OUT_DEFAULT = os.path.join(_DIR, "data", "horizon_sweep.json")

_G: dict = {}


def _block_ids(ts: np.ndarray, hours: int) -> np.ndarray:
    """Ufuk uzunluğunda örtüşmeyen blok kimliği.

    Örnekler 1–3 saat aralıkla alınıyor ama 24–48 saatlik ufukta sonuç
    pencereleri büyük ölçüde örtüşüyor. Saat bazlı kümeleme bu bağımlılığı
    yok sayar ve standart hatayı ~√(ufuk/adım) kat küçük gösterir — 24s ufuk,
    3s adımda t'yi ~2,8 kat şişirir. Kümeyi ufuk boyunda bloğa çevirmek
    pencereleri bloklar arasında ayırır, böylece t dürüst olur.
    """
    span_ms = max(int(hours), 1) * 3_600_000
    return ts // span_ms


def _cluster_stats(x: np.ndarray, ts: np.ndarray) -> tuple[float, float, float]:
    """Küme bazlı ortalama / standart hata / t."""
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


def _skill_stats(x: np.ndarray, ts: np.ndarray, is_long: np.ndarray) -> dict:
    """Drift-nötr SKILL = (ort. LONG + ort. SHORT) / 2, saat kümeli SE.

    `x` işaret düzeltilmiş işlem getirisi (LONG'ta +hareket, SHORT'ta −hareket).
    Ortak piyasa sürüklenmesi LONG'a +d, SHORT'a −d girdiği için ortalamaların
    ortalaması sürüklenmeyi siler; farkın yarısı `drift` olarak raporlanır.

    SE, ortalama farkı için küme-dayanıklı sandviç tahmincisiyle: her saat
    kümesinin etki fonksiyonu toplanır (dengesiz saatleri doğru ağırlıklar).
    """
    out = {"skill": 0.0, "drift": 0.0, "se": 0.0, "t": 0.0,
           "n_long": int(is_long.sum()), "n_short": int((~is_long).sum())}
    nl, ns = out["n_long"], out["n_short"]
    if nl < 2 or ns < 2:
        return out
    ml = float(x[is_long].mean())
    ms = float(x[~is_long].mean())
    out["skill"] = (ml + ms) / 2.0
    out["drift"] = (ms - ml) / 2.0
    _u, inv = np.unique(ts, return_inverse=True)
    g = int(inv.max()) + 1
    a = np.bincount(inv[is_long], weights=(x[is_long] - ml), minlength=g)
    b = np.bincount(inv[~is_long], weights=(x[~is_long] - ms), minlength=g)
    infl = 0.5 * (a / nl + b / ns)
    if g < 2:
        return out
    var = float((infl ** 2).sum()) * g / (g - 1)
    se = var ** 0.5
    out["se"] = se
    out["t"] = (out["skill"] / se) if se > 0 else 0.0
    return out


def sweep_book(book: dict, bars_1h, master_times, time_index, pre, step: int,
               symbols: list[str] | None = None, per_symbol: bool = False) -> dict:
    from signals import signal_for_book

    universe = list(symbols or bt.TEST_SYMBOLS)
    maxh = max(HORIZONS)
    closes = {s: np.array([b["close"] for b in bars], dtype=np.float64)
              for s, bars in bars_1h.items()}

    ts_rec: list[int] = []
    ret_rec: list[list[float]] = []
    long_rec: list[bool] = []
    sym_rec: list[str] = []
    n = len(master_times)

    for idx in range(bt.WARMUP, n - maxh - 1):
        if (idx - bt.WARMUP) % step:
            continue
        t_close = master_times[idx]
        kl_1h = {}
        bis = {}
        for sym in universe:
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
            long_rec.append(s == "UP")
            sym_rec.append(sym)
            ret_rec.append([float((c[bi + h] - p0) / p0 * sign) for h in HORIZONS])

    if not ret_rec:
        return {"book": bt._book_label(book), "uid": book.get("uid"), "signals": 0}

    ts = np.array(ts_rec, dtype=np.int64)
    R = np.array(ret_rec, dtype=np.float64)
    is_long = np.array(long_rec, dtype=bool)
    rows = []
    for i, h in enumerate(HORIZONS):
        blk = _block_ids(ts, h)
        mu, se, t = _cluster_stats(R[:, i], blk)
        sk = _skill_stats(R[:, i], blk, is_long)
        rows.append({
            "hours": h,
            "gross_pct": round(mu * 100, 4),
            "se_pct": round(se * 100, 4),
            "t": round(t, 2),
            "net_pct": round((mu - ROUND_TRIP_FEE) * 100, 4),
            "beats_fee": bool(mu > ROUND_TRIP_FEE),
            "skill_pct": round(sk["skill"] * 100, 4),
            "skill_se_pct": round(sk["se"] * 100, 4),
            "skill_t": round(sk["t"], 2),
            "drift_pct": round(sk["drift"] * 100, 4),
            "n_long": sk["n_long"],
            "n_short": sk["n_short"],
            "skill_beats_taker": bool(sk["skill"] > ROUND_TRIP_FEE and sk["t"] >= 2.0),
            "skill_beats_maker": bool(sk["skill"] > MAKER_ROUND_TRIP_FEE and sk["t"] >= 2.0),
        })
    out = {
        "book": bt._book_label(book), "uid": book.get("uid"),
        "signals": int(R.shape[0]), "hours_sampled": int(np.unique(ts).size),
        "universe": len(universe),
        "horizons": rows,
    }
    if per_symbol:
        syms = np.array(sym_rec)
        by_sym: dict[str, list] = {}
        for sym in sorted(set(sym_rec)):
            m = syms == sym
            if m.sum() < 40:
                continue
            srows = []
            for i, h in enumerate(HORIZONS):
                sk = _skill_stats(R[m, i], _block_ids(ts[m], h), is_long[m])
                srows.append({
                    "hours": h,
                    "skill_pct": round(sk["skill"] * 100, 4),
                    "skill_se_pct": round(sk["se"] * 100, 4),
                    "skill_t": round(sk["t"], 2),
                    "drift_pct": round(sk["drift"] * 100, 4),
                    "n_long": sk["n_long"], "n_short": sk["n_short"],
                })
            by_sym[sym] = srows
        out["by_symbol"] = by_sym
    return out


def _init(step: int, symbols: list[str] | None = None, per_symbol: bool = False) -> None:
    bars = {}
    for s in bt.TEST_SYMBOLS:
        b = bt._load_cache(s)
        if b:
            bars[s] = b
    mt, ti = bt._build_time_index(bars)
    _G.update(bars=bars, mt=mt, ti=ti, pre=bf.precompute(bars), step=step,
              symbols=symbols, per_symbol=per_symbol)


def _run(book: dict) -> dict:
    return sweep_book(book, _G["bars"], _G["mt"], _G["ti"], _G["pre"], _G["step"],
                      _G.get("symbols"), _G.get("per_symbol", False))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--books", default="analiz1,analiz6,analiz6_v2,analiz6_v3")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--step", type=int, default=1, help="kaç saatte bir örnekle")
    p.add_argument("--symbols", default=None,
                   help="evreni kısıtla (ör. BTCUSDT,ETHUSDT,SOLUSDT); boş = 30 coin")
    p.add_argument("--per-symbol", action="store_true",
                   help="coin bazlı SKILL kırılımı da yaz (edge_gate tablosu için)")
    p.add_argument("--out", default=OUT_DEFAULT)
    args = p.parse_args()

    syms = ([x.strip().upper() for x in args.symbols.split(",") if x.strip()]
            if args.symbols else None)

    want = {x.strip().lower() for x in args.books.split(",") if x.strip()}
    books = [b for b in bt.ALL_BOOKS
             if (b.get("uid") or "").lower() in want or (b.get("name") or "").lower() in want]
    if not books:
        print("Eşleşen defter yok.")
        return

    print(f"Tutma süresi taraması — {len(books)} defter · "
          f"{len(syms) if syms else len(bt.TEST_SYMBOLS)} coin · ufuk {HORIZONS}")
    print(f"Komisyon eşiği: %{ROUND_TRIP_FEE*100:.2f} (gidiş-dönüş)\n")

    t0 = time.time()
    results = []
    if args.workers <= 1:
        _init(args.step, syms, args.per_symbol)
        for b in books:
            results.append(_run(b))
    else:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_init,
                                 initargs=(args.step, syms, args.per_symbol)) as ex:
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
        print(f"── {r['book']} · {r['signals']:,} sinyal ".ljust(86, "─"))
        print(f"{'saat':>5} {'brüt':>9} {'t':>6} │ {'SKILL':>9} {'SE':>8} {'t':>6} "
              f"{'sürükl.':>9} │ {'taker':>7} {'maker':>7}")
        for h in r["horizons"]:
            print(f"{h['hours']:5} {h['gross_pct']:8.4f}% {h['t']:6.2f} │ "
                  f"{h['skill_pct']:8.4f}% {h['skill_se_pct']:7.4f}% {h['skill_t']:6.2f} "
                  f"{h['drift_pct']:8.4f}% │ "
                  f"{'✓' if h['skill_beats_taker'] else '—':>7} "
                  f"{'✓' if h['skill_beats_maker'] else '—':>7}")
        print(f"      eşik: SKILL > %{ROUND_TRIP_FEE*100:.2f} (taker) / "
              f"%{MAKER_ROUND_TRIP_FEE*100:.2f} (maker) ve t ≥ 2\n")

    payload = {"ok": True, "horizons": list(HORIZONS), "round_trip_fee": ROUND_TRIP_FEE,
               "maker_round_trip_fee": MAKER_ROUND_TRIP_FEE,
               "results": results, "elapsed_sec": round(time.time() - t0, 1)}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Süre: {payload['elapsed_sec']}s · Kayıt: {args.out}")


if __name__ == "__main__":
    main()

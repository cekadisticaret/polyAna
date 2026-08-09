#!/usr/bin/env python3
"""Kripto Test 1Y backtest — hızlandırılmış sürüm.

`backtest_1y.py` ile **birebir aynı** simülasyon mantığı; fark yalnızca veri
hazırlığında. Profil, sürenin ~%92'sinin algoritma matematiğinde değil saatlik
döngüde tekrar tekrar yapılan format dönüşümünde geçtiğini gösterdi:

  _resample_4h  %59  — her saat, her coin için 1040 bar yeniden gruplanıyordu
  _bars_ohlc    %33  — her saat, her coin için 260 dict yeniden üretiliyordu

Üçü de zamandan bağımsız, yani coin başına **bir kez** hesaplanabilir:

  1. `ohlc1[sym]`    — tam 1h serisi, algo formatında (dilim al, kopyalama yok)
  2. `ohlc4[sym][p]` — 4 faz hizalı 4h serisi; orijinal kod pencereyi
     `bi+1-1040`'tan başlattığı için kova sınırları `(bi+1) % 4` ile kayar,
     dört fazın tamamı önceden üretilince sonuç bit bit aynı kalır
  3. `_bars_ohlc` devre dışı — girdi zaten normalize (backtest'e özel)

Ayrıca işçi süreçlere `bars_1h`/`time_index` her iş için pickle'lanmıyor;
initializer ile süreç başına bir kez kuruluyor.

  python3 AgustosKripto/Test/backtest_fast.py --days 365 --workers 2
  python3 AgustosKripto/Test/backtest_fast.py --source islemler_a2
  python3 AgustosKripto/Test/backtest_fast.py --verify   # orijinalle karşılaştır
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_DIR))
for p in (_DIR, os.path.join(_ROOT, "temmuzPoly"), os.path.join(_ROOT, "AgustosKripto")):
    if p not in sys.path:
        sys.path.insert(0, p)

import backtest_1y as bt  # noqa: E402
import engine as _engine_mod  # noqa: E402
from engine import build_candidates  # noqa: E402
from atr_profit_lock import (  # noqa: E402
    atr_from_klines,
    atr_usd as _atr_usd_fn,
    loss_stop_threshold as _loss_stop_threshold,
    update_lock as _update_lock,
)

import signals as _tsig  # noqa: E402

# `_bars_ohlc` her saat her coin için 260 dict'i yeniden üretiyor. Bu backtest'te
# barlar zaten `_bar10` ile normalize edildiği (o/h/l/c/v float) için dönüşüm
# gereksiz — modül attribute'unu geçersiz kıl. Yalnızca bu süreçte geçerli.
_tsig._algo_cat._bars_ohlc = lambda kl: kl or []
# Aynı gerekçe: A6/A6V2 yolundaki o/h/l/c/v dönüşümü de gereksiz.
_tsig.to_algo21_klines = lambda kl: kl or []

# ATR(14) Wilder, verilen 260 barlık pencereye bağlı → (coin, bar) ile tam belirli.
# Aynı süreçte onlarca defter aynı (coin, bar) çiftini istediği için süreç-yerel
# memo, tekrar hesabı ortadan kaldırır.
_ATR_MEMO: dict[tuple[str, int], float | None] = {}


def _atr_cached(sym: str, bi: int, kl: list) -> float | None:
    key = (sym, bi)
    if key not in _ATR_MEMO:
        _ATR_MEMO[key] = atr_from_klines(kl, period=14)
    return _ATR_MEMO[key]


ALL_BOOKS = bt.ALL_BOOKS
TEST_SYMBOLS = bt.TEST_SYMBOLS
DEPOSIT, MARGIN_USD, LEVERAGE = bt.DEPOSIT, bt.MARGIN_USD, bt.LEVERAGE
MAX_OPEN, WARMUP = bt.MAX_OPEN, bt.WARMUP
WINDOW_1H, WINDOW_4H_SRC = bt.WINDOW_1H, bt.WINDOW_4H_SRC
OUT_DEFAULT = os.path.join(_DIR, "data", "backtest_fast_results.json")

_G: dict = {}


def _bar10(o: float, h: float, l: float, c: float, v: float) -> dict:
    """Hem kısa (o/h/l/c/v) hem uzun anahtarlı bar — tüm tüketiciler okuyabilsin."""
    return {"o": o, "h": h, "l": l, "c": c, "v": v,
            "open": o, "high": h, "low": l, "close": c, "volume": v}


def precompute(bars_1h: dict[str, list[dict]]) -> dict:
    """Coin başına tam 1h serisi + 4 faz hizalı 4h serisi (bir kez)."""
    ohlc1: dict[str, list[dict]] = {}
    ohlc4: dict[str, list[list[dict]]] = {}
    for sym, bars in bars_1h.items():
        full = [
            _bar10(float(b["open"]), float(b["high"]), float(b["low"]),
                   float(b["close"]), float(b["volume"]))
            for b in bars
        ]
        ohlc1[sym] = full
        phases: list[list[dict]] = []
        for p in range(4):
            ser = []
            i = p
            n = len(full)
            while i + 3 < n:
                g = full[i:i + 4]
                ser.append(_bar10(
                    g[0]["o"], max(x["h"] for x in g), min(x["l"] for x in g),
                    g[3]["c"], sum(x["v"] for x in g),
                ))
                i += 4
            phases.append(ser)
        ohlc4[sym] = phases
    return {"ohlc1": ohlc1, "ohlc4": ohlc4}


def _slice_4h(sym: str, bi: int, pre: dict) -> list[dict]:
    """Orijinal `_resample_4h(bars[bi+1-1040 : bi+1])` ile aynı dilim."""
    lo4 = max(0, bi + 1 - WINDOW_4H_SRC)
    p = lo4 % 4
    j0 = (lo4 - p) // 4
    j1 = (bi - p - 3) // 4
    if j1 < j0:
        return []
    return pre["ohlc4"][sym][p][j0:j1 + 1]


def simulate_book(book: dict, bars_1h, master_times, time_index, test_start_ms, pre) -> dict:
    """backtest_1y.simulate_book ile aynı mantık; dilimler önceden hesaplanmış."""
    history: list[dict] = []
    opens: list[dict] = []
    total_pnl = 0.0
    wins = 0
    n = len(master_times)

    _tf_bucket: dict[tuple[str, str], list] = {}
    _tf_seen_len = [0]

    def _fast_tf_stats(hist_arg: list, symbol: str, tf: str):
        if _tf_seen_len[0] < len(hist_arg):
            for t in hist_arg[_tf_seen_len[0]:]:
                b = _tf_bucket.setdefault(
                    ((t.get("symbol") or "").upper(), t.get("interval") or "1h"), [0, 0, 0.0])
                b[1] += 1
                if t.get("win"):
                    b[0] += 1
                b[2] += float(t.get("pnl") or 0)
            _tf_seen_len[0] = len(hist_arg)
        b = _tf_bucket.get((symbol.upper(), tf))
        if not b or b[1] == 0:
            return 0.0, 0.0, 0
        return b[0] / b[1], b[2], b[1]

    _orig = _engine_mod._tf_stats
    _engine_mod._tf_stats = _fast_tf_stats
    from signals import signal_for_book

    try:
        for idx in range(WARMUP, n - 1):
            t_close = master_times[idx]
            t_next = master_times[idx + 1]
            if t_next < test_start_ms:
                continue

            still_open: list[dict] = []
            for pos in opens:
                sym, side, entry = pos["symbol"], pos["side"], pos["entry_price"]
                bi = time_index.get(sym, {}).get(t_next)
                if bi is None:
                    still_open.append(pos)
                    continue
                bar = bars_1h[sym][bi]
                high, low, close_px = bar["high"], bar["low"], bar["close"]
                fav_px, adv_px = (high, low) if side == "LONG" else (low, high)
                net_fav, _, _ = bt._trade_pnl(side, entry, fav_px)
                net_adv, _, _ = bt._trade_pnl(side, entry, adv_px)
                net_close, _, _ = bt._trade_pnl(side, entry, close_px)

                pos, _ = _update_lock(pos, net_fav, ts=None, mark=fav_px)
                stop_level = int(pos.get("stop_level") or 0)

                realized_net = None
                exit_reason = None
                if stop_level >= 1:
                    su = pos.get("stop_upnl")
                    if su is not None and net_adv <= float(su):
                        realized_net, exit_reason = float(su), "atr_stop"
                else:
                    lim = _loss_stop_threshold(pos)
                    if lim is not None and net_adv <= lim:
                        realized_net, exit_reason = float(lim), "atr_loss"

                if realized_net is None:
                    if stop_level >= 1 and net_close > 0:
                        still_open.append(pos)
                        continue
                    realized_net, exit_reason = net_close, "hourly"

                win = realized_net >= 0
                if win:
                    wins += 1
                total_pnl += realized_net
                history.append({**pos, "exit_price": close_px,
                                "pnl": round(realized_net, 4), "win": win,
                                "close_reason": exit_reason})
            opens = still_open

            kl_1h: dict[str, list] = {}
            kl_4h: dict[str, list] = {}
            for sym in TEST_SYMBOLS:
                bi = time_index.get(sym, {}).get(t_close)
                if bi is None or bi < 30:
                    continue
                kl_1h[sym] = pre["ohlc1"][sym][max(0, bi + 1 - WINDOW_1H):bi + 1]
                kl_4h[sym] = _slice_4h(sym, bi, pre)

            if not kl_1h:
                continue

            try:
                cands = build_candidates(book, kl_1h, kl_4h, history,
                                         symbols=TEST_SYMBOLS,
                                         signal_for_book=signal_for_book)
            except Exception as e:
                return {"book": bt._book_label(book), "uid": book.get("uid"),
                        "error": str(e), "total_pnl": round(total_pnl, 2),
                        "trades": len(history), "wins": wins}

            held = {p["symbol"] for p in opens}
            seen = set()
            for c in cands:
                if len(opens) >= MAX_OPEN:
                    break
                sym = c["symbol"]
                if sym in seen or sym in held:
                    continue
                bi = time_index.get(sym, {}).get(t_close)
                if bi is None:
                    continue
                entry = bars_1h[sym][bi]["close"]
                atr_val = _atr_cached(sym, bi, kl_1h.get(sym) or [])
                opens.append({
                    "symbol": sym, "side": c["side"], "signal": c["signal"],
                    "interval": c.get("interval") or "1h", "entry_price": entry,
                    "margin_usd": MARGIN_USD, "leverage": LEVERAGE,
                    "atr": atr_val,
                    "atr_usd": _atr_usd_fn(MARGIN_USD, LEVERAGE, entry, atr_val) if atr_val else 0.0,
                    "peak_upnl": 0.0, "stop_upnl": None, "stop_level": 0,
                    "lock_armed": False,
                })
                seen.add(sym)
    finally:
        _engine_mod._tf_stats = _orig

    wr = round(100.0 * wins / len(history), 1) if history else None
    return {"book": bt._book_label(book), "uid": book.get("uid"),
            "source": book.get("source"), "title": book.get("title"),
            "total_pnl": round(total_pnl, 2), "trades": len(history), "wins": wins,
            "wr": wr, "deposit": DEPOSIT,
            "final_balance": round(DEPOSIT + total_pnl, 2), "profitable": total_pnl > 0}


def _init_worker(test_start_ms: int) -> None:
    """Süreç başına bir kez: cache'i diskten oku + ön hesap (pickle yok)."""
    bars = {}
    for s in TEST_SYMBOLS:
        b = bt._load_cache(s)
        if b:
            bars[s] = b
    mt, ti = bt._build_time_index(bars)
    _G.update(bars=bars, mt=mt, ti=ti, pre=precompute(bars), start=test_start_ms)


def _run_one(book: dict) -> dict:
    return simulate_book(book, _G["bars"], _G["mt"], _G["ti"], _G["start"], _G["pre"])


def _verify(hours: int = 400) -> None:
    """Orijinalle aynı sonucu verdiğini kanıtla (kısa pencere, birkaç defter)."""
    bars = {s: b for s in TEST_SYMBOLS if (b := bt._load_cache(s))}
    mt, ti = bt._build_time_index(bars)
    mt_s = mt[-(WARMUP + hours):]
    start = mt_s[WARMUP]
    pre = precompute(bars)
    print(f"Doğrulama — {hours} saat, orijinal vs hızlı\n")
    ok = True
    for uid in ("a2_01", "a1_05", "analiz6"):
        cand = [b for b in ALL_BOOKS if b["uid"] == uid]
        if not cand:
            continue
        book = cand[0]
        t0 = time.time()
        r_old = bt.simulate_book(book, bars, mt_s, ti, start)
        t_old = time.time() - t0
        t0 = time.time()
        r_new = simulate_book(book, bars, mt_s, ti, start, pre)
        t_new = time.time() - t0
        same = (r_old.get("total_pnl") == r_new.get("total_pnl")
                and r_old.get("trades") == r_new.get("trades"))
        ok = ok and same
        print(f"  {r_old['book']:<8} pnl {r_old.get('total_pnl'):>10} vs {r_new.get('total_pnl'):>10} · "
              f"işlem {r_old.get('trades'):>4} vs {r_new.get('trades'):>4} · "
              f"{t_old:6.1f}s → {t_new:5.1f}s ({t_old/max(t_new,1e-9):5.1f}x) "
              f"{'AYNI' if same else 'FARKLI'}")
    print("\n" + ("Tüm defterler birebir aynı." if ok else "UYUŞMAZLIK VAR."))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--out", default=OUT_DEFAULT)
    p.add_argument("--source", default="all",
                   choices=["all", "islemler_a2", "islemler_poly", "algo1"])
    p.add_argument("--books", default=None,
                   help="virgülle defter seçimi — uid veya ad (ör. analiz1,analiz6,A6V2)")
    p.add_argument("--verify", action="store_true", help="orijinalle sonuç/hız karşılaştır")
    p.add_argument("--verify-hours", type=int, default=400)
    args = p.parse_args()

    if args.verify:
        _verify(args.verify_hours)
        return

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    test_start_ms = int(start.timestamp() * 1000)

    src = ALL_BOOKS if args.source == "all" else [b for b in ALL_BOOKS if b.get("source") == args.source]
    if args.books:
        want = {x.strip().lower() for x in args.books.split(",") if x.strip()}
        src = [b for b in src
               if (b.get("uid") or "").lower() in want or (b.get("name") or "").lower() in want]
        missing = want - {(b.get("uid") or "").lower() for b in src} - {(b.get("name") or "").lower() for b in src}
        if missing:
            print(f"UYARI — bulunamayan defter: {', '.join(sorted(missing))}")
        if not src:
            print("Eşleşen defter yok."); return
    books = [b for b in src if not (b.get("source") == "algo1" and b.get("kind") in ("oi", "fear_greed"))]
    skipped = [b for b in src if b not in books]

    print(f"Kripto Test hızlı backtest — {args.days}g · {len(books)} defter ({args.source}) · {len(TEST_SYMBOLS)} coin")
    print(f"Dönem: {start.date()} → {end.date()} · {args.workers} işçi\n")

    t0 = time.time()
    results: list[dict] = []
    if args.workers <= 1:
        _init_worker(test_start_ms)
        for i, b in enumerate(books, 1):
            r = _run_one(b)
            results.append(r)
            print(f"  [{i}/{len(books)}] {r['book']}: ${r.get('total_pnl',0):+.2f} · "
                  f"{r.get('trades',0)} işlem · {time.time()-t0:.0f}s", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers,
                                 initializer=_init_worker,
                                 initargs=(test_start_ms,)) as ex:
            futs = {ex.submit(_run_one, b): b for b in books}
            for i, fut in enumerate(as_completed(futs), 1):
                r = fut.result()
                results.append(r)
                print(f"  [{i}/{len(books)}] {r['book']}: ${r.get('total_pnl',0):+.2f} · "
                      f"{r.get('trades',0)} işlem · {time.time()-t0:.0f}s", flush=True)

    results.sort(key=lambda x: (-(x.get("total_pnl") or 0), -(x.get("trades") or 0)))
    profitable = [r for r in results if r.get("profitable")]

    payload = {
        "ok": True, "period_days": args.days,
        "period_start": start.date().isoformat(), "period_end": end.date().isoformat(),
        "symbols": TEST_SYMBOLS,
        "params": {"deposit": DEPOSIT, "margin_usd": MARGIN_USD, "leverage": LEVERAGE,
                   "max_open": MAX_OPEN, "fee_rate": bt.FEE_RATE},
        "books_tested": len(results),
        "books_skipped": [bt._book_label(b) for b in skipped],
        "profitable_count": len(profitable), "profitable": profitable,
        "all_results": results,
        "engine": "backtest_fast (ön hesaplı dilim; backtest_1y ile birebir)",
        "elapsed_sec": round(time.time() - t0, 1),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 64)
    print(f"  KÂRDA (+) KAPATAN — {len(profitable)} / {len(results)}")
    print("=" * 64)
    for i, r in enumerate(profitable, 1):
        wr = r.get("wr")
        print(f"  {i:2d}. {r['book']:<10}  net ${r['total_pnl']:>+8.2f}  "
              f"{r.get('trades',0):>4} işlem  WR {f'{wr:.1f}%' if wr is not None else '—'}")
    print("=" * 64)
    print(f"Süre: {payload['elapsed_sec']}s · Kayıt: {args.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Poly→Kripto çıkış rejimi taraması — A2#05 · A6V3 · B1#03 MUM · MELEZ.

Neden: bu 4 defter Poly'de kâr ediyor, Binance Futures sanalında kaybediyor.
Ölçülen sebep komisyon değil "saatlik zorunlu kapanış":

  brüt kenar/işlem   A2#05 −$0,24 · A6V3 +$0,11 · B1#03 +$0,60
  komisyon/işlem     $0,55 – $0,60   (taker %0,05 × 2 yön × $600 notional)

Poly'de saatlik kapanış piyasanın kuralı ve ödeme ~2:1 binary olduğu için %54
isabet kâr demek. Futures'ta ödeme simetrik: 1 saatlik ufukta %54 isabetin
beklenen kenarı notional'ın %0,02–0,05'i, gidiş-dönüş taker ise %0,09–0,10.
Ücret kenarın 2–5 katı → her saat kapatmak matematiksel olarak kayıp.

Bu betik aynı sinyalleri sabit tutup **yalnız çıkış kuralını** değiştirir ve
hangi rejimin kenarı komisyonun üstüne çıkardığını ölçer.

  python3 AgustosKripto/Test/backtest_pro4.py --days 120          # tarama
  python3 AgustosKripto/Test/backtest_pro4.py --days 365 --regimes r0,r2
  python3 AgustosKripto/Test/backtest_pro4.py --list
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

import backtest_1y as bt  # noqa: E402  (canlı API yamalarını da kurar)
import backtest_fast as bf  # noqa: E402
import engine as _engine_mod  # noqa: E402
from atr_profit_lock import (  # noqa: E402
    atr_from_klines,
    atr_usd as _atr_usd_fn,
    loss_stop_threshold as _loss_stop_threshold,
    update_lock as _update_lock,
)

ALL_BOOKS = bt.ALL_BOOKS
TEST_SYMBOLS = bt.TEST_SYMBOLS
DEPOSIT, MARGIN_USD, LEVERAGE = bt.DEPOSIT, bt.MARGIN_USD, bt.LEVERAGE
WARMUP, WINDOW_1H = bt.WARMUP, bt.WINDOW_1H

# Taranan 4 defter — dashboard "Algoritma Durumu" en iyi 4'ü
POLY4 = ["a2_05", "analiz6_v3", "b1_mum", "melez"]
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

TAKER = 0.0005   # mevcut sistemin varsaydığı oran (Binance gerçek taker %0,045)
MAKER = 0.0002   # limit emirle giriş/çıkış (Binance maker %0,018)

OUT_DEFAULT = os.path.join(_DIR, "data", "backtest_pro4.json")


# ── Rejimler ──────────────────────────────────────────────────
# exit: "hourly" = mevcut sistem (her saat kapat) · "signal" = sinyal dönene
#       kadar tut. max_hold = üst sınır (1h bar). cooldown = ATR stop sonrası
#       aynı sembole tekrar girmeden beklenecek bar.
def _reg(name, desc, **kw) -> dict:
    base = {
        "name": name, "desc": desc, "exit": "signal", "fee": TAKER,
        "max_hold": 24, "symbols": None, "tf": "auto",
        "atr_loss": True, "atr_lock": True, "cooldown": 0, "max_open": 4,
    }
    base.update(kw)
    return base


REGIMES: dict[str, dict] = {
    "r0": _reg("r0 MEVCUT", "saatlik zorunlu kapanış (bugünkü sistem)",
               exit="hourly", max_hold=None),
    "r1": _reg("r1 SİNYAL-24", "sinyal dönene kadar tut, max 24 saat"),
    "r2": _reg("r2 SİNYAL-72", "sinyal dönene kadar tut, max 72 saat", max_hold=72),
    "r3": _reg("r3 SİNYAL-∞", "yalnız sinyal/ATR çıkışı, süre sınırı yok", max_hold=None),
    "r4": _reg("r4 SİNYAL-72 MAKER", "r2 + limit emir komisyonu", max_hold=72, fee=MAKER),
    "r5": _reg("r5 SİNYAL-72 4h", "r2 + yalnız 4h zaman dilimi", max_hold=72, tf="4h"),
    "r6": _reg("r6 SİNYAL-72 MAJÖR", "r2 + yalnız BTC/ETH/SOL", max_hold=72, symbols=MAJORS),
    "r7": _reg("r7 SİNYAL-72 STOPSUZ", "r2 + ATR zarar stopu kapalı", max_hold=72, atr_loss=False),
    "r8": _reg("r8 SİNYAL-72 SOĞUMA", "r2 + stop sonrası 6 bar bekleme", max_hold=72, cooldown=6),
    "r9": _reg("r9 SAATLİK MAKER", "mevcut sistem + limit emir komisyonu",
               exit="hourly", max_hold=None, fee=MAKER),
}


# ── PnL ───────────────────────────────────────────────────────
def _pnl(side: str, entry: float, exit_px: float, fee: float) -> tuple[float, float, float]:
    """(net, brüt, komisyon) — notional sabit $600, komisyon iki yönlü."""
    notional = MARGIN_USD * LEVERAGE
    qty = notional / entry if entry else 0.0
    gross = (exit_px - entry) * qty if side == "LONG" else (entry - exit_px) * qty
    comm = notional * fee + exit_px * qty * fee
    return round(gross - comm, 4), round(gross, 4), round(comm, 4)


def _ret_pct(side: str, entry: float, exit_px: float) -> float:
    """Kaldıraçsız yön düzeltmeli yüzde — SKILL hesabı için."""
    if not entry:
        return 0.0
    move = (exit_px - entry) / entry * 100.0
    return move if side == "LONG" else -move


def _skill(longs: list[float], shorts: list[float]) -> dict:
    """Drift-nötr SKILL + t (runner.py::_skill_stats ile aynı tanım)."""
    allv = longs + shorts
    n = len(allv)
    out = {"skill": None, "drift": None, "t": 0.0, "n_long": len(longs), "n_short": len(shorts)}
    if n < 2:
        return out
    mean = sum(allv) / n
    sd = (sum((v - mean) ** 2 for v in allv) / n) ** 0.5
    out["t"] = round((mean / (sd / n ** 0.5)) if sd > 0 else 0.0, 2)
    out["mean_ret"] = round(mean, 4)
    if longs and shorts:
        ml, ms = sum(longs) / len(longs), sum(shorts) / len(shorts)
        out["skill"] = round((ml + ms) / 2, 4)
        out["drift"] = round((ms - ml) / 2, 4)
        out["mean_long"] = round(ml, 4)
        out["mean_short"] = round(ms, 4)
    return out


# ── Simülasyon ────────────────────────────────────────────────
def simulate(book: dict, regime: dict, bars_1h, master_times, time_index,
             test_start_ms: int, pre: dict) -> dict:
    """backtest_fast.simulate_book'un rejim parametreli sürümü.

    Sinyal hesabı birebir aynı; değişen tek şey pozisyonun ne zaman kapandığı.
    """
    from signals import signal_for_book

    fee = float(regime["fee"])
    exit_mode = regime["exit"]
    max_hold = regime["max_hold"]
    tf_mode = regime["tf"]
    max_open = int(regime["max_open"])
    cooldown = int(regime["cooldown"] or 0)
    symbols = list(regime["symbols"] or TEST_SYMBOLS)

    history: list[dict] = []
    opens: list[dict] = []
    longs: list[float] = []
    shorts: list[float] = []
    total_net = 0.0
    total_gross = 0.0
    total_comm = 0.0
    wins = 0
    hold_bars_sum = 0
    cool_until: dict[str, int] = {}
    reasons: dict[str, list] = {}

    # engine._tf_stats — geçmişten TF seçimi; O(n^2) taramayı kovaya çevir
    _tf_bucket: dict[tuple[str, str], list] = {}
    _seen = [0]

    def _fast_tf_stats(hist_arg: list, symbol: str, tf: str):
        if _seen[0] < len(hist_arg):
            for t in hist_arg[_seen[0]:]:
                b = _tf_bucket.setdefault(
                    ((t.get("symbol") or "").upper(), t.get("interval") or "1h"), [0, 0, 0.0])
                b[1] += 1
                if t.get("win"):
                    b[0] += 1
                b[2] += float(t.get("pnl") or 0)
            _seen[0] = len(hist_arg)
        b = _tf_bucket.get((symbol.upper(), tf))
        if not b or b[1] == 0:
            return 0.0, 0.0, 0
        return b[0] / b[1], b[2], b[1]

    _orig = _engine_mod._tf_stats
    _engine_mod._tf_stats = _fast_tf_stats

    def _record(pos: dict, exit_px: float, reason: str, idx: int) -> None:
        nonlocal total_net, total_gross, total_comm, wins, hold_bars_sum
        net, gross, comm = _pnl(pos["side"], pos["entry_price"], exit_px, fee)
        total_net += net
        total_gross += gross
        total_comm += comm
        if net >= 0:
            wins += 1
        hold_bars_sum += idx - int(pos.get("_bi") or idx)
        r = _ret_pct(pos["side"], pos["entry_price"], exit_px)
        (longs if pos["side"] == "LONG" else shorts).append(r)
        b = reasons.setdefault(reason, [0, 0.0])
        b[0] += 1
        b[1] += net
        history.append({**pos, "exit_price": exit_px, "pnl": round(net, 4),
                        "pnl_gross": gross, "commission": comm,
                        "win": net >= 0, "close_reason": reason})

    try:
        n = len(master_times)
        for idx in range(WARMUP, n):
            t_close = master_times[idx]
            if t_close < test_start_ms:
                continue

            # 1) kapanmış barlardan sinyal (idx dahil) — ileri bakış yok
            kl_1h: dict[str, list] = {}
            kl_4h: dict[str, list] = {}
            for sym in symbols:
                bi = time_index.get(sym, {}).get(t_close)
                if bi is None or bi < 30:
                    continue
                kl_1h[sym] = pre["ohlc1"][sym][max(0, bi + 1 - WINDOW_1H):bi + 1]
                kl_4h[sym] = bf._slice_4h(sym, bi, pre)
            if not kl_1h:
                continue

            need_4h = tf_mode != "1h"
            try:
                sig1 = signal_for_book(book, kl_1h) if tf_mode != "4h" else {}
                sig4 = signal_for_book(book, kl_4h) if need_4h else {}
            except Exception as e:
                _engine_mod._tf_stats = _orig
                return {"book": bt._book_label(book), "uid": book.get("uid"),
                        "regime": regime["name"], "error": str(e)}

            # 2) açık pozisyonları bu bar (idx) üzerinde yönet.
            #    Pozisyon idx-1'in kapanışında açıldı → bu bar onun ilk barı.
            #    ATR stopları bar içi high/low ile, sinyal çıkışı bar kapanışıyla.
            still_open: list[dict] = []
            for pos in opens:
                sym, side, entry = pos["symbol"], pos["side"], pos["entry_price"]
                bi = time_index.get(sym, {}).get(t_close)
                if bi is None:
                    still_open.append(pos)
                    continue
                bar = bars_1h[sym][bi]
                fav_px, adv_px = ((bar["high"], bar["low"]) if side == "LONG"
                                  else (bar["low"], bar["high"]))
                close_px = bar["close"]
                net_fav = _pnl(side, entry, fav_px, fee)[0]
                net_adv = _pnl(side, entry, adv_px, fee)[0]
                net_close = _pnl(side, entry, close_px, fee)[0]

                if regime["atr_lock"]:
                    pos, _ = _update_lock(pos, net_fav, ts=None, mark=fav_px)
                stop_level = int(pos.get("stop_level") or 0)

                # ATR kâr kilidi / zarar stopu — bar içi
                if stop_level >= 1:
                    su = pos.get("stop_upnl")
                    if su is not None and net_adv <= float(su):
                        _record(pos, _solve_px(side, entry, float(su), fee), "atr_stop", idx)
                        if cooldown:
                            cool_until[sym] = idx + cooldown
                        continue
                elif regime["atr_loss"]:
                    lim = _loss_stop_threshold(pos)
                    if lim is not None and net_adv <= lim:
                        _record(pos, _solve_px(side, entry, float(lim), fee), "atr_loss", idx)
                        if cooldown:
                            cool_until[sym] = idx + cooldown
                        continue

                if exit_mode == "hourly":
                    # kâr kilidi kuruluysa koş, değilse saat sonunda kapat
                    if stop_level >= 1 and net_close > 0:
                        still_open.append(pos)
                        continue
                    _record(pos, close_px, "hourly", idx)
                    continue

                # sinyal rejimi — gerçek ters sinyal veya süre sınırı
                cur = (sig4 if (pos.get("interval") == "4h" and need_4h) else sig1).get(sym, "NEUTRAL")
                flipped = (side == "LONG" and cur == "DOWN") or (side == "SHORT" and cur == "UP")
                age = idx - int(pos.get("_bi") or idx)
                if flipped:
                    _record(pos, close_px, "signal_reversal", idx)
                elif max_hold is not None and age >= max_hold:
                    _record(pos, close_px, "max_hold", idx)
                else:
                    still_open.append(pos)
            opens = still_open

            # 3) yeni pozisyon
            if len(opens) >= max_open:
                continue
            held = {p["symbol"] for p in opens}
            rows = []
            for sym in symbols:
                if sym not in kl_1h or sym in held:
                    continue
                if cooldown and idx < cool_until.get(sym, -1):
                    continue
                s1 = sig1.get(sym, "NEUTRAL")
                s4 = sig4.get(sym, "NEUTRAL")
                if tf_mode == "1h":
                    tf, sig = "1h", s1
                elif tf_mode == "4h":
                    tf, sig = "4h", s4
                else:
                    tf, sig = _engine_mod.choose_timeframe(sym, s1, s4, history)
                if sig not in ("UP", "DOWN"):
                    continue
                wr, pnl_h, nh = _fast_tf_stats(history, sym, tf)
                score = _engine_mod._tf_score(wr, pnl_h, nh) if nh >= 2 else 50.0
                rows.append({"symbol": sym, "side": "LONG" if sig == "UP" else "SHORT",
                             "signal": sig, "interval": tf, "score": round(score, 2)})
            rows.sort(key=lambda x: (-x["score"], x["symbol"]))

            for c in rows:
                if len(opens) >= max_open:
                    break
                sym = c["symbol"]
                bi = time_index.get(sym, {}).get(t_close)
                if bi is None:
                    continue
                entry = bars_1h[sym][bi]["close"]
                atr_val = bf._atr_cached(sym, bi, kl_1h.get(sym) or [])
                opens.append({
                    "symbol": sym, "side": c["side"], "signal": c["signal"],
                    "interval": c["interval"], "entry_price": entry,
                    "margin_usd": MARGIN_USD, "leverage": LEVERAGE, "atr": atr_val,
                    "atr_usd": _atr_usd_fn(MARGIN_USD, LEVERAGE, entry, atr_val) if atr_val else 0.0,
                    "peak_upnl": 0.0, "stop_upnl": None, "stop_level": 0,
                    "lock_armed": False, "_bi": idx,
                })
    finally:
        _engine_mod._tf_stats = _orig

    nt = len(history)
    st = _skill(longs, shorts)
    return {
        "book": bt._book_label(book), "uid": book.get("uid"),
        "regime": regime["name"], "regime_key": regime.get("key"),
        "total_pnl": round(total_net, 2),
        "gross": round(total_gross, 2),
        "commission": round(total_comm, 2),
        "trades": nt,
        "wins": wins,
        "wr": round(100.0 * wins / nt, 1) if nt else None,
        "avg_hold_h": round(hold_bars_sum / nt, 1) if nt else None,
        "edge_per_trade": round(total_gross / nt, 4) if nt else None,
        "fee_per_trade": round(total_comm / nt, 4) if nt else None,
        "final_balance": round(DEPOSIT + total_net, 2),
        "profitable": total_net > 0,
        "skill": st["skill"], "drift": st["drift"], "t": st["t"],
        "n_long": st["n_long"], "n_short": st["n_short"],
        "reasons": {k: [v[0], round(v[1], 2)] for k, v in sorted(reasons.items())},
    }


def _solve_px(side: str, entry: float, target_net: float, fee: float) -> float:
    """Hedef net PnL'i veren çıkış fiyatı — ATR stopunun tetiklendiği seviye.

    LONG :  net = px·qty·(1−fee) − entry·qty − notional·fee
    SHORT:  net = entry·qty − px·qty·(1+fee) − notional·fee
    """
    notional = MARGIN_USD * LEVERAGE
    qty = notional / entry if entry else 0.0
    if not qty:
        return entry
    if side == "LONG":
        px = (target_net + entry * qty + notional * fee) / (qty * (1 - fee))
    else:
        px = (entry * qty - notional * fee - target_net) / (qty * (1 + fee))
    return round(max(px, 1e-12), 10)


# ── Çalıştırıcı ───────────────────────────────────────────────
_G: dict = {}


def _init_worker(test_start_ms: int) -> None:
    bars = {}
    for s in TEST_SYMBOLS:
        b = bt._load_cache(s)
        if b:
            bars[s] = b
    mt, ti = bt._build_time_index(bars)
    _G.update(bars=bars, mt=mt, ti=ti, pre=bf.precompute(bars), start=test_start_ms)


def _run_job(job: tuple) -> dict:
    uid, reg_key = job
    book = next(b for b in ALL_BOOKS if b["uid"] == uid)
    reg = dict(REGIMES[reg_key])
    reg["key"] = reg_key
    return simulate(book, reg, _G["bars"], _G["mt"], _G["ti"], _G["start"], _G["pre"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--books", default=",".join(POLY4))
    p.add_argument("--regimes", default="all")
    p.add_argument("--out", default=OUT_DEFAULT)
    p.add_argument("--list", action="store_true")
    args = p.parse_args()

    if args.list:
        for k, r in REGIMES.items():
            print(f"  {k:4s} {r['name']:22s} {r['desc']}")
        return

    reg_keys = list(REGIMES) if args.regimes == "all" else [
        x.strip() for x in args.regimes.split(",") if x.strip() in REGIMES]
    uids = [x.strip() for x in args.books.split(",") if x.strip()]
    missing = [u for u in uids if not any(b["uid"] == u for b in ALL_BOOKS)]
    if missing:
        print(f"Katalogda yok: {', '.join(missing)}")
        return

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    test_start_ms = int(start.timestamp() * 1000)
    jobs = [(u, r) for r in reg_keys for u in uids]

    print(f"Poly→Kripto çıkış rejimi taraması — {args.days} gün · "
          f"{len(uids)} defter × {len(reg_keys)} rejim = {len(jobs)} sim")
    print(f"Dönem: {start.date()} → {end.date()} · ${MARGIN_USD:.0f}×{LEVERAGE}x\n")

    t0 = time.time()
    results: list[dict] = []
    if args.workers <= 1:
        _init_worker(test_start_ms)
        for i, j in enumerate(jobs, 1):
            r = _run_job(j)
            results.append(r)
            print(f"  [{i}/{len(jobs)}] {r.get('regime','?'):22s} {r['book']:<7} "
                  f"${r.get('total_pnl',0):+9.2f} · {r.get('trades',0):>5} işlem · "
                  f"{time.time()-t0:.0f}s", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker,
                                 initargs=(test_start_ms,)) as ex:
            futs = {ex.submit(_run_job, j): j for j in jobs}
            for i, fut in enumerate(as_completed(futs), 1):
                r = fut.result()
                results.append(r)
                print(f"  [{i}/{len(jobs)}] {r.get('regime','?'):22s} {r['book']:<7} "
                      f"${r.get('total_pnl',0):+9.2f} · {r.get('trades',0):>5} işlem · "
                      f"{time.time()-t0:.0f}s", flush=True)

    # rejim bazlı toplam
    by_reg: dict[str, dict] = {}
    for r in results:
        k = r.get("regime_key") or "?"
        b = by_reg.setdefault(k, {"key": k, "name": r.get("regime"), "pnl": 0.0,
                                  "trades": 0, "gross": 0.0, "comm": 0.0,
                                  "books": 0, "profitable_books": 0, "rows": []})
        b["pnl"] += r.get("total_pnl") or 0
        b["trades"] += r.get("trades") or 0
        b["gross"] += r.get("gross") or 0
        b["comm"] += r.get("commission") or 0
        b["books"] += 1
        b["profitable_books"] += 1 if r.get("profitable") else 0
        b["rows"].append(r)
    ranked = sorted(by_reg.values(), key=lambda x: -x["pnl"])

    print("\n" + "=" * 92)
    print(f"  REJİM SIRALAMASI — {len(uids)} defter toplamı ({args.days} gün)")
    print("=" * 92)
    print(f"  {'rejim':24s} {'toplam net':>11s} {'brüt':>10s} {'komisyon':>10s} "
          f"{'işlem':>7s} {'kârlı':>6s}")
    for r in ranked:
        print(f"  {r['name']:24s} {r['pnl']:>+11.2f} {r['gross']:>+10.2f} "
              f"{r['comm']:>10.2f} {r['trades']:>7d} {r['profitable_books']}/{r['books']:>4d}")
    print("=" * 92)

    best = ranked[0] if ranked else None
    if best:
        print(f"\n  EN İYİ: {best['name']}")
        print(f"  {'defter':8s} {'net':>10s} {'brüt':>9s} {'kom':>8s} {'işlem':>6s} "
              f"{'WR':>6s} {'SKILL':>8s} {'t':>6s} {'ort saat':>9s}")
        for r in sorted(best["rows"], key=lambda x: -(x.get("total_pnl") or 0)):
            sk = r.get("skill")
            print(f"  {r['book']:8s} {r.get('total_pnl',0):>+10.2f} {r.get('gross',0):>+9.2f} "
                  f"{r.get('commission',0):>8.2f} {r.get('trades',0):>6d} "
                  f"{(r.get('wr') or 0):>5.1f}% {(f'{sk:+.4f}' if sk is not None else '—'):>8s} "
                  f"{(r.get('t') or 0):>+6.2f} {(r.get('avg_hold_h') or 0):>9.1f}")

    payload = {
        "ok": True, "days": args.days,
        "period_start": start.date().isoformat(), "period_end": end.date().isoformat(),
        "books": uids, "regimes": reg_keys,
        "params": {"deposit": DEPOSIT, "margin_usd": MARGIN_USD, "leverage": LEVERAGE,
                   "taker": TAKER, "maker": MAKER},
        "regime_ranking": [{k: v for k, v in r.items() if k != "rows"} for r in ranked],
        "results": results,
        "regime_defs": {k: {kk: vv for kk, vv in v.items() if kk != "key"}
                        for k, v in REGIMES.items()},
        "elapsed_sec": round(time.time() - t0, 1),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nSüre: {payload['elapsed_sec']}s · Kayıt: {args.out}")


if __name__ == "__main__":
    main()

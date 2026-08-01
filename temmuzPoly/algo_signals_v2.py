#!/usr/bin/env python3
"""Algoritma Analiz 2 — 1Y backtest'te kârlı 17 algo (saatlik sinyal)."""
from __future__ import annotations

import datetime
import json
import os

import algo_signals as sig
from algo_catalog_extended import (
    EXTENDED_CATALOG,
    cci,
    fib_retracement,
    hurst_proxy,
    liquidity_sweep_proxy,
    range_bounce,
    schaff_trend_cycle,
    squeeze_momentum,
    williams_r,
    zscore_pairs_proxy,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = "/tmp/algo_signals_v2.json"
PREV_FILE = "/tmp/algo_signals_v2_prev.json"
ACCURACY_FILE = os.path.join(_DIR, "algo_accuracy_v2.json")

# display_id, name, category, handler_type
ALGO_V2_META = [
    (1,  "Liquidity Sweep Proxy",      "SMC",        "fn", liquidity_sweep_proxy),
    (2,  "RSI Diverjansı (14) Katı",   "Momentum",   "fn", sig.rsi_divergence_strict),
    (3,  "Stochastic RSI",             "Momentum",   "fn", sig.stoch_rsi),
    (4,  "Schaff Trend Cycle",         "Momentum",   "fn", schaff_trend_cycle),
    (5,  "Mean Reversion (Z-Score)",   "İstatistik", "fn", sig.mean_reversion),
    (6,  "Z-Score Mean Reversion",     "İstatistik", "fn", zscore_pairs_proxy),
    (7,  "Hurst Proxy (trend/MR)",     "İstatistik", "fn", hurst_proxy),
    (8,  "Williams %R",                "Momentum",   "fn", williams_r),
    (9,  "Squeeze Momentum (BB+KC)",   "Volatilite", "fn", squeeze_momentum),
    (10, "Fibonacci Retracement",      "Price Action","fn", fib_retracement),
    (11, "Range Trading S/R Bounce",   "Range",      "fn", range_bounce),
    (12, "Stochastic RSI (14) K/D",    "Momentum",   "fn", sig.stoch_rsi_kd),
    (13, "Bollinger Bands + Squeeze",  "Volatilite", "fn", sig.bb_squeeze),
    (14, "CCI",                        "Momentum",   "fn", cci),
    (15, "Pairs Trading",              "Pairs",      "pairs", None),
    (16, "Supertrend",                 "Trend",      "fn", sig.supertrend),
    (17, "SuperTrend v2 (7,2.0)",      "Trend",      "fn", sig.supertrend_v2),
]


def _build_signals(
    interval: str = "1h",
    htf_interval: str = "4h",
    limit: int = 200,
    htf_limit: int = 100,
) -> tuple[dict, dict]:
    kl_primary, kl_htf = {}, {}
    for sym, pair in sig.SYMBOLS.items():
        try:
            kl_primary[sym] = sig.fetch_klines(pair, interval, limit)
            kl_htf[sym] = sig.fetch_klines(pair, htf_interval, htf_limit)
        except Exception as e:
            print(f"[A2] Fetch error {sym}: {e}")
            kl_primary[sym] = []
            kl_htf[sym] = []

    pairs_sig = sig.pairs_trading(kl_primary)
    signals = {}

    for num, name, _cat, kind, fn in ALGO_V2_META:
        entry = {sym: "NEUTRAL" for sym in sig.SYMBOLS}
        entry["name"] = name
        if kind == "pairs":
            entry.update(pairs_sig)
        elif kind == "fn" and fn:
            for sym in sig.SYMBOLS:
                kl = kl_primary.get(sym, [])
                if kl:
                    try:
                        entry[sym] = fn(kl)
                    except Exception as e:
                        print(f"[A2] Algo {num} {sym}: {e}")
        signals[str(num)] = entry

    active = list(signals.values())
    consensus = {}
    for sym in sig.SYMBOLS:
        up = sum(1 for v in active if v[sym] == "UP")
        down = sum(1 for v in active if v[sym] == "DOWN")
        consensus[sym] = {
            "UP": up, "DOWN": down, "NEUTRAL": len(active) - up - down, "total": len(active),
        }
    return signals, consensus


def run():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    signals, consensus = _build_signals()

    try:
        prev_data = json.load(open(PREV_FILE)) if os.path.exists(PREV_FILE) else None
        if prev_data and prev_data.get("signals"):
            acc = {}
            if os.path.exists(ACCURACY_FILE):
                with open(ACCURACY_FILE) as f:
                    acc = json.load(f)

            updated_any = False
            for sym, pair in sig.SYMBOLS.items():
                kl = sig.fetch_klines(pair, "1h", 200)
                if len(kl) < 3:
                    continue
                prev_close = kl[-3]["c"]
                curr_close = kl[-2]["c"]
                if curr_close == prev_close:
                    continue
                actual = "UP" if curr_close > prev_close else "DOWN"

                for algo_num, sigs in prev_data["signals"].items():
                    algo_sig = sigs.get(sym)
                    if algo_sig not in ("UP", "DOWN"):
                        continue
                    correct = 1 if algo_sig == actual else 0
                    if algo_num not in acc:
                        acc[algo_num] = {"name": sigs.get("name", ""), "total": 0, "correct": 0, "by_sym": {}}
                    if not acc[algo_num].get("name") and sigs.get("name"):
                        acc[algo_num]["name"] = sigs["name"]
                    acc[algo_num]["total"] += 1
                    acc[algo_num]["correct"] += correct
                    by_sym = acc[algo_num].setdefault("by_sym", {})
                    if sym not in by_sym:
                        by_sym[sym] = {"total": 0, "correct": 0}
                    by_sym[sym]["total"] += 1
                    by_sym[sym]["correct"] += correct
                    updated_any = True

            if updated_any:
                with open(ACCURACY_FILE, "w") as f:
                    json.dump(acc, f, indent=2, ensure_ascii=False)
                print(f"[A2 {now.strftime('%H:%M')}] algo_accuracy_v2.json güncellendi")
        if prev_data and prev_data.get("consensus"):
            from chart_signal_accuracy import update_consensus_accuracy
            kl_map = {sym: sig.fetch_klines(pair, "1h", 200) for sym, pair in sig.SYMBOLS.items()}
            update_consensus_accuracy(
                prev_data["consensus"],
                kl_map,
                ACCURACY_FILE,
                name="Analiz 2 Konsensüs",
            )
    except Exception as e:
        print(f"[A2 {now.strftime('%H:%M')}] accuracy hatası: {e}")

    try:
        with open(PREV_FILE, "w") as f:
            json.dump({"signals": signals, "consensus": consensus}, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    period_start = now.replace(minute=5, second=0, microsecond=0)
    period_end = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    out = {
        "updated": now.strftime("%H:%M"),
        "period_start": period_start.strftime("%H:%M"),
        "period_end": period_end.strftime("%H:%M"),
        "signals": signals,
        "consensus": consensus,
        "panel": "analiz2",
        "algo_count": len(ALGO_V2_META),
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"[A2 {now.strftime('%H:%M')}] {len(ALGO_V2_META)} algo → {OUT_FILE}")
    for sym in sig.SYMBOLS:
        c = consensus[sym]
        print(f"  {sym}: ▲{c['UP']} ▼{c['DOWN']} ={c['NEUTRAL']}")


if __name__ == "__main__":
    run()

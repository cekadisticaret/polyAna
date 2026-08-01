#!/usr/bin/env python3
"""
95 algo kataloğu — 1Y saatlik yön backtest (BTC+ETH+SOL).

Mevcut algo_signals (1-39) + genişletilmiş katalog (40-83).
On-chain / sosyal / opsiyon verisi gerektirenler atlanır veya OHLCV proxy kullanılır.

  python3 temmuzPoly/backtest_algo_catalog.py
  python3 temmuzPoly/backtest_algo_catalog.py --top 30 --min-trades 80
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import algo_signals as sig
from algo_catalog_extended import EXTENDED_CATALOG, _to_kl
from backtest_analiz2 import fetch_klines_history

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SKIP_IDS = {13, 14}  # yön yok
OUT_FILE = os.path.join(_DIR, "backtest_algo_catalog_1y.json")
WARMUP = 60
MIN_TRADES_DEFAULT = 50


def _build_base_catalog() -> list[dict]:
    simple = {
        1: sig.ema_crossover, 2: sig.macd_div, 3: sig.supertrend, 4: sig.ichimoku,
        5: sig.rsi_div, 6: sig.stoch_rsi, 7: sig.bb_squeeze, 8: sig.vwap, 9: sig.obv,
        10: sig.volume_profile, 11: sig.mean_reversion, 16: sig.atr_breakout,
        17: sig.heikin_ashi, 18: sig.tema_crossover, 19: sig.adx_regime,
        25: sig.parabolic_sar_adx, 26: sig.macd_histogram_div, 27: sig.stoch_rsi_kd,
        28: sig.triple_ema, 29: sig.hull_ma, 30: sig.keltner_channel,
        31: sig.donchian_channel, 32: sig.vwap_volume_profile, 33: sig.money_flow_index,
        34: sig.random_forest_clf, 35: sig.markov_chain, 36: sig.supertrend_v2,
        37: sig.ichimoku_v2, 38: sig.rsi_divergence_strict, 39: sig.h1_combination,
    }
    cats = {
        1: "Trend", 2: "Momentum", 3: "Trend", 4: "Trend", 5: "Momentum",
        6: "Momentum", 7: "Volatilite", 8: "Hacim", 9: "Hacim", 10: "Hacim",
        11: "İstatistik", 12: "Pairs", 15: "Multi-TF", 16: "Breakout", 17: "Trend",
        18: "Trend", 19: "Regime", 20: "Order Flow", 21: "Sentiment",
        25: "Trend", 26: "Momentum", 27: "Momentum", 28: "Trend", 29: "Trend",
        30: "Volatilite", 31: "Breakout", 32: "Hacim", 33: "Hacim", 34: "ML",
        35: "İstatistik", 36: "Trend", 37: "Trend", 38: "Momentum", 39: "Kombinasyon",
    }
    out = []
    for num, name in sig.ALGO_META:
        if num in SKIP_IDS:
            continue
        if num in simple:
            out.append({"id": num, "category": cats.get(num, "?"), "name": name, "fn": simple[num], "type": "single"})
        elif num == 12:
            out.append({"id": num, "category": "Pairs", "name": name, "fn": None, "type": "pairs"})
        elif num == 15:
            out.append({"id": num, "category": "Multi-TF", "name": name, "fn": None, "type": "multi_tf"})
        elif num in (20, 21):
            out.append({"id": num, "category": cats.get(num, "?"), "name": name, "fn": None, "type": "skip_live"})
    for num, cat, name, fn in EXTENDED_CATALOG:
        out.append({"id": num, "category": cat, "name": name, "fn": fn, "type": "single"})
    return out


def _resample_4h(bars_1h: list[dict]) -> list[dict]:
    out = []
    bucket = []
    for b in bars_1h:
        bucket.append(b)
        if len(bucket) == 4:
            out.append({
                "open_time": bucket[0]["open_time"],
                "open": bucket[0]["open"],
                "high": max(x["high"] for x in bucket),
                "low": min(x["low"] for x in bucket),
                "close": bucket[-1]["close"],
                "volume": sum(x["volume"] for x in bucket),
                "taker_buy": sum(x.get("taker_buy", x["volume"] * 0.5) for x in bucket),
            })
            bucket = []
    return out


def _eval_signal(entry: dict, sym: str, bars_by_sym: dict[str, list[dict]], i: int) -> str:
    t = entry["type"]
    if t == "skip_live":
        return "NEUTRAL"
    bars = bars_by_sym[sym]
    win = bars[max(0, i - 199): i + 1]
    if t == "pairs":
        eth = _to_kl(bars_by_sym["ETHUSDT"][max(0, i - 199): i + 1])
        btc = _to_kl(bars_by_sym["BTCUSDT"][max(0, i - 199): i + 1])
        d = sig.pairs_trading({"ETH": eth, "BTC": btc})
        if sym == "ETHUSDT":
            return d.get("ETH", "NEUTRAL")
        if sym == "BTCUSDT":
            return d.get("BTC", "NEUTRAL")
        return "NEUTRAL"
    if t == "multi_tf":
        kl1 = _to_kl(win)
        bars4 = _resample_4h(bars[max(0, i - 799): i + 1])
        kl4 = _to_kl(bars4)
        if len(kl4) < 10:
            return "NEUTRAL"
        return sig.multi_tf(kl1, kl4)
    fn = entry["fn"]
    kl = _to_kl(win)
    try:
        return fn(kl)
    except Exception:
        return "NEUTRAL"


def backtest_catalog(bars_by_sym: dict[str, list[dict]], catalog: list[dict], test_start_ms: int) -> list[dict]:
    sym_keys = list(bars_by_sym.keys())
    results = {e["id"]: {"id": e["id"], "name": e["name"], "category": e["category"], "correct": 0, "total": 0} for e in catalog}

    total_jobs = len(catalog) * len(sym_keys)
    done = 0
    for entry in catalog:
        for sym in sym_keys:
            bars = bars_by_sym[sym]
            done += 1
            if done % 10 == 0 or done == total_jobs:
                print(f"  [{done}/{total_jobs}] #{entry['id']} {sym}...", flush=True)
            for i in range(WARMUP, len(bars) - 1):
                if bars[i + 1]["open_time"] < test_start_ms:
                    continue
                pred = _eval_signal(entry, sym, bars_by_sym, i)
                if pred not in ("UP", "DOWN"):
                    continue
                actual = "UP" if bars[i + 1]["close"] > bars[i]["close"] else "DOWN"
                r = results[entry["id"]]
                r["total"] += 1
                if pred == actual:
                    r["correct"] += 1

    out = []
    for r in results.values():
        if r["total"] == 0:
            continue
        r["wr"] = round(r["correct"] / r["total"] * 100, 2)
        out.append(r)
    out.sort(key=lambda x: (x["wr"], x["total"]), reverse=True)
    return out


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--min-trades", type=int, default=MIN_TRADES_DEFAULT)
    p.add_argument("--out", default=OUT_FILE)
    args = p.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    fetch_start = start - timedelta(days=10)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    fetch_ms = int(fetch_start.timestamp() * 1000)

    bars_by_sym = {}
    for sym in SYMBOLS:
        print(f"Veri çekiliyor: {sym} 1h ({args.days}g)...")
        bars = await fetch_klines_history(sym, "1h", fetch_ms, end_ms)
        print(f"  {len(bars)} bar")
        bars_by_sym[sym] = bars

    catalog = _build_base_catalog()
    print(f"\nBacktest: {len(catalog)} algo × 3 sembol...")
    ranked = backtest_catalog(bars_by_sym, catalog, start_ms)

    eligible = [r for r in ranked if r["total"] >= args.min_trades]
    top = eligible[: args.top]
    skipped = [r for r in ranked if r["total"] < args.min_trades]

    payload = {
        "period_days": args.days,
        "period_start": start.date().isoformat(),
        "period_end": end.date().isoformat(),
        "symbols": SYMBOLS,
        "algos_tested": len(catalog),
        "min_trades": args.min_trades,
        "top": top,
        "all_ranked": ranked,
        "insufficient_data": skipped,
        "note": "On-chain/sosyal/haber (#20 OI canlı, #21 F&G canlı) OHLCV proxy veya atlandı.",
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"  TOP {args.top} — 1Y saatlik yön doğruluğu (min {args.min_trades} sinyal)")
    print("=" * 60)
    for i, r in enumerate(top, 1):
        print(f"  {i:2d}. #{r['id']:2d}  {r['wr']:5.1f}%  ({r['correct']}/{r['total']})  [{r['category']}] {r['name']}")
    print("=" * 60)
    print(f"Kaydedildi: {args.out}")
    if skipped:
        print(f"Yetersiz veri (<{args.min_trades} sinyal): {len(skipped)} algo")


if __name__ == "__main__":
    asyncio.run(main())

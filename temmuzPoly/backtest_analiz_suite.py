#!/usr/bin/env python3
"""
4 / 10 / 21. Analiz — 1Y walk-forward backtest

Canlı trader ve algo dosyalarına DOKUNULMAZ; sadece import edilir.
Varsayılan: $1000 · 2025-07-17 · bugün

  python3 temmuzPoly/backtest_analiz_suite.py --all --telegram
  python3 temmuzPoly/backtest_analiz_suite.py --analiz 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import poly_predictor_analysis as pa
from poly_predictor_analysis import predict
from backtest_analiz2 import _neutral_preloaded
from backtest_common import (
    Trade,
    NEUTRAL_OB,
    run_walk_forward,
    print_summary,
    to_a4_klines,
    to_algo21_klines,
)

_TZ_TR = ZoneInfo("Europe/Istanbul")
INITIAL_BALANCE = 1000.0
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID = "830754964"

# ── Analiz 4 sinyal (poly_trader_analiz4 algo fonksiyonları) ──
def signal_analiz4(sym, kslice, open_ms, history, amount_fn):
    from poly_trader_analiz4 import (
        algo_trend, algo_mr, algo_orderflow, algo_funding,
        AMOUNT_STRONG, AMOUNT_MODERATE,
    )
    klines = to_a4_klines(kslice)
    v1, _ = algo_trend(klines)
    v2, _ = algo_mr(klines)
    v3, _ = algo_orderflow(klines, NEUTRAL_OB)
    v4, _ = algo_funding(0.0)
    score = v1 + v2 + v3 + v4
    amount = AMOUNT_STRONG if abs(score) >= 3 else AMOUNT_MODERATE if abs(score) == 2 else 0.0
    if amount <= 0 or score == 0:
        return None
    return {
        "predicted_dir": "UP" if score > 0 else "DOWN",
        "amount": amount,
        "entry_price": kslice[-1]["close"],
        "extra": {"score": score},
    }


# ── Analiz 10 sinyal (poly_analiz_dual_core + predict) ──
async def signal_analiz10(sym, kslice, open_ms, history, amount_fn):
    from poly_analiz_dual_core import (
        CONFIG_A10, algo_trend, algo_mr, algo_orderflow, algo_funding, _trade_amount,
    )
    cfg = CONFIG_A10
    pa._slot_utc_ms = open_ms
    pred = await predict(sym, preloaded=_neutral_preloaded(kslice))
    if pred is None:
        return None
    klines = to_a4_klines(kslice)
    v_trend, _ = algo_trend(klines)
    v_mr, _ = algo_mr(klines)
    v_of, _ = algo_orderflow(klines, NEUTRAL_OB)
    v_fund, _ = algo_funding(0.0)
    score_b = v_trend + v_mr + v_of + v_fund
    dir_b = "UP" if score_b > 0 else "DOWN" if score_b < 0 else None
    dir_a = pred.predicted_dir
    conf_a = max(pred.prob_up, pred.prob_down)
    strong_a = conf_a >= 0.65
    strong_b = abs(score_b) >= 3
    if dir_b is None or abs(score_b) < cfg.min_score_b or dir_a != dir_b:
        return None
    return {
        "predicted_dir": dir_a,
        "amount": _trade_amount(cfg, strong_a, strong_b),
        "entry_price": kslice[-1]["close"],
        "extra": {"score_b": score_b, "conf_a": round(conf_a, 2)},
    }


# ── Analiz 21 sinyal (btc_analiz21_algo) ──
def _dyn_a21(history: list[Trade], sym: str) -> float:
    low, mid, high = 12.0, 16.0, 20.0
    sh = [t for t in history if t.symbol == sym]
    if not sh:
        return mid
    rate = sum(1 for t in sh if t.win) / len(sh)
    if rate > 0.5:
        return high
    if rate < 0.5:
        return low
    return mid


def signal_analiz21(sym, kslice, open_ms, history, amount_fn):
    from btc_analiz21_algo import SYMBOL_ALGOS
    cfg = SYMBOL_ALGOS.get(sym)
    if not cfg:
        return None
    fn, algo_name = cfg
    kl = to_algo21_klines(kslice)
    if len(kl) < 50:
        return None
    sig = fn(kl)
    if sig not in ("UP", "DOWN"):
        return None
    return {
        "predicted_dir": sig,
        "amount": _dyn_a21(history, sym),
        "entry_price": kslice[-1]["close"],
        "extra": {"algo": algo_name},
    }


ANALIZ_CONFIG = {
    4: {
        "label": "4. ANALİZ",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "signal": signal_analiz4,
        "min_bars": 60,
        "out": "backtest_analiz4_1y.json",
    },
    10: {
        "label": "10. ANALİZ",
        "symbols": ["BTCUSDT", "SOLUSDT"],
        "signal": signal_analiz10,
        "min_bars": 60,
        "out": "backtest_analiz10_1y.json",
    },
    21: {
        "label": "21. ANALİZ",
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "signal": signal_analiz21,
        "min_bars": 50,
        "out": "backtest_analiz21_1y.json",
    },
}


async def run_one(analiz_id: int, start: datetime, balance: float) -> dict:
    cfg = ANALIZ_CONFIG[analiz_id]
    return await run_walk_forward(
        label=cfg["label"],
        symbols=cfg["symbols"],
        signal_fn=cfg["signal"],
        start_date=start,
        initial_balance=balance,
        min_bars=cfg["min_bars"],
    )


def tg_send(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
        }).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=15) as r:
            r.read()
        print("[TG] Gönderildi")
    except Exception as e:
        print(f"[TG] Hata: {e}")


def build_tg_report(results: list[dict]) -> str:
    sep = "━" * 28
    parts = [
        sep,
        "📊 <b>1Y BACKTEST — Analiz 4 / 10 / 21</b>",
        f"${results[0]['initial_balance']:.0f} · 17 Tem 2025 → bugün",
        "<i>Algo dosyaları değiştirilmedi · OB/funding nötr sim.</i>",
        "",
    ]
    for r in results:
        ret = (r["final_balance"] / r["initial_balance"] - 1) * 100
        parts.append(f"<b>{r['label']}</b>")
        parts.append(
            f"  {r['trades']} işlem  WR {r['win_rate_pct']}%  "
            f"P&L {'+' if r['total_pnl']>=0 else ''}${r['total_pnl']:.0f}  "
            f"→ ${r['final_balance']:.0f} ({ret:+.0f}%)"
        )
        for sym, st in r["by_symbol"].items():
            name = sym.replace("USDT", "")
            parts.append(
                f"    {name}: {st['trades']}t WR{st['win_rate_pct']}% "
                f"{'+' if st['pnl']>=0 else ''}${st['pnl']:.0f}"
            )
        parts.append("")
    parts.append(sep)
    return "\n".join(parts)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--analiz", type=int, choices=[4, 10, 21], help="Tek analiz")
    p.add_argument("--all", action="store_true", help="4+10+21 hepsi")
    p.add_argument("--balance", type=float, default=INITIAL_BALANCE)
    p.add_argument("--start", default="2025-07-17")
    p.add_argument("--telegram", action="store_true")
    args = p.parse_args()

    if not args.analiz and not args.all:
        args.all = True

    y, m, d = map(int, args.start.split("-"))
    start = datetime(y, m, d, 0, 0, 0, tzinfo=_TZ_TR)

    ids = [4, 10, 21] if args.all else [args.analiz]
    t0 = time.time()
    results = []
    for aid in ids:
        r = await run_one(aid, start, args.balance)
        print_summary(r)
        out = os.path.join(_DIR, ANALIZ_CONFIG[aid]["out"])
        with open(out, "w") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
        print(f"→ {out}")
        results.append(r)

    print(f"\nToplam süre: {time.time()-t0:.0f}s")
    if args.telegram:
        tg_send(build_tg_report(results))


if __name__ == "__main__":
    asyncio.run(main())

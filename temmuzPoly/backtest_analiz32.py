#!/usr/bin/env python3
"""
32. Analiz — 1Y walk-forward backtest (SOL only, FeatureEngine composite)

Analiz32 core/features DOKUNULMAZ — predictor.predict_from_klines kullanılır.
Sanal PM 0.50 · stake $12/$16/$20 (WR).
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
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_A32 = os.path.join(os.path.dirname(_DIR), "Analiz32")
sys.path.insert(0, _DIR)
sys.path.insert(0, _A32)

from backtest_common import Trade, print_summary, run_walk_forward
from predictor import predict_from_klines

_TZ_TR = ZoneInfo("Europe/Istanbul")
INITIAL_BALANCE = 1000.0
SYMBOLS = ["SOLUSDT"]
OUT_DEFAULT = os.path.join(_DIR, "backtest_analiz32_1y.json")

BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID = "830754964"


def _dyn_amount(history: list[Trade], sym: str) -> float:
    sh = [t for t in history if t.symbol == sym]
    if not sh:
        return 16.0
    rate = sum(1 for t in sh if t.win) / len(sh)
    if rate > 0.5:
        return 20.0
    if rate < 0.5:
        return 12.0
    return 16.0


def _signal(sym: str, kslice: list[dict], open_ms: int, history: list, amount_fn) -> dict | None:
    # walk-forward kslice kapalı mumlar; predictor son barı 'forming' sanıp düşürür → pad
    if len(kslice) < 80:
        return None
    padded = list(kslice) + [kslice[-1]]
    pred = predict_from_klines(sym, padded)
    if pred is None or not pred.predicted_dir:
        return None
    amount = amount_fn(history, sym) if amount_fn else 16.0
    return {
        "predicted_dir": pred.predicted_dir,
        "entry_price": float(kslice[-1]["close"]),
        "amount": amount,
        "extra": {
            "up_score": pred.up_score,
            "down_score": pred.down_score,
            "htf_bias": pred.htf_bias,
            "confidence": pred.confidence,
            "factors": pred.factors[:4],
        },
    }


def build_tg(r: dict) -> str:
    ret = (r["final_balance"] / r["initial_balance"] - 1) * 100
    sym_lines = [
        f"  {sym.replace('USDT','')}: {st['trades']}t WR{st['win_rate_pct']}% "
        f"{'+' if st['pnl']>=0 else ''}${st['pnl']:.0f}"
        for sym, st in r["by_symbol"].items()
    ]
    monthly = "\n".join(
        f"  {m}: {'+' if p>=0 else ''}${p:.0f}" for m, p in sorted(r["monthly_pnl"].items())
    )
    sep = "━" * 28
    return "\n".join([
        sep, "📊 <b>32. ANALİZ — 1Y BACKTEST</b>",
        f"SOL · ${r['initial_balance']:.0f} · {r['period']}", "",
        f"İşlem: {r['trades']} ({r['wins']}W/{r['losses']}L)  WR: {r['win_rate_pct']}%",
        f"P&L: {'+' if r['total_pnl']>=0 else ''}${r['total_pnl']:.0f}",
        f"Bakiye: ${r['initial_balance']:.0f} → ${r['final_balance']:.0f} ({ret:+.0f}%)",
        f"Max DD: {r['max_drawdown_pct']}%  |  skip: {r['skipped_signals']}", "",
        "<b>Sembol</b>", *sym_lines, "", "<b>Aylık P&L</b>", monthly, "",
        "<i>FeatureEngine composite · gate±15 · PM 0.50 · $12/16/20</i>", sep,
    ])


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


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--balance", type=float, default=INITIAL_BALANCE)
    p.add_argument("--start", default="2025-07-17")
    p.add_argument("--telegram", action="store_true")
    p.add_argument("--out", default=OUT_DEFAULT)
    args = p.parse_args()

    y, m, d = map(int, args.start.split("-"))
    start = datetime(y, m, d, 0, 0, 0, tzinfo=_TZ_TR)

    t0 = time.time()
    result = await run_walk_forward(
        label="32. ANALİZ",
        symbols=SYMBOLS,
        signal_fn=_signal,
        start_date=start,
        initial_balance=args.balance,
        min_bars=80,
        amount_fn=_dyn_amount,
    )
    print_summary(result)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n→ {args.out} ({time.time()-t0:.0f}s)")
    if args.telegram:
        tg_send(build_tg(result))


if __name__ == "__main__":
    asyncio.run(main())

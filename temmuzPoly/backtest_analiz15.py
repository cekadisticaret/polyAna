#!/usr/bin/env python3
"""
15. Analiz — 1Y walk-forward backtest

BTC → A6 MACD Hist. Div · ETH → A8 Jesse EMA8/21 (sıkı) · SOL → A2 Poly Predictor
Saatlik · $300 · :05 open / :00 close · WR tier $12/$16/$20

  python3 temmuzPoly/backtest_analiz15.py
  python3 temmuzPoly/backtest_analiz15.py --telegram --start 2025-07-27
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
sys.path.insert(0, _DIR)

from analiz15_signal import SYMBOLS, engine_label, resolve_direction
from backtest_common import run_walk_forward, print_summary, Trade
from a3a8_signal_mode import signal_mode_status
from pm_trader_helpers import SANAL_INITIAL_BALANCE, symbol_wr_amount

_TZ_TR = ZoneInfo("Europe/Istanbul")
LABEL = "15. ANALİZ"
OUT_FILE = os.path.join(_DIR, "backtest_analiz15_1y.json")
BOT_TOKEN = os.getenv("TELEGRAM_ANALIZ4_BOT_TOKEN", "8630483764:AAFmAmG4nHAGb238wpavlWgMjJZDvIy4DzE")
CHAT_ID = os.getenv("TELEGRAM_ANALIZ4_CHAT_ID", os.getenv("TELEGRAM_CHAT", "830754964"))


def _history_as_dicts(history: list[Trade]) -> list[dict]:
    return [{"symbol": t.symbol, "win": t.win} for t in history]


def _amount_fn(history: list[Trade], sym: str) -> float:
    return symbol_wr_amount(_history_as_dicts(history), sym)


def _make_signal(a8_strict: bool | None):
    async def _fn(sym, kslice, open_ms, history, amount_fn):
        direction = await resolve_direction(sym, kslice, open_ms, a8_strict=a8_strict)
        if direction not in ("UP", "DOWN"):
            return None
        amount = amount_fn(history, sym) if amount_fn else SANAL_INITIAL_BALANCE / 20
        eng = engine_label(sym)
        return {
            "predicted_dir": direction,
            "amount": amount,
            "entry_price": float(kslice[-1]["close"]),
            "extra": {"engine": eng, "source": SYMBOLS and sym},
        }
    return _fn


async def run_backtest(start: datetime, balance: float, a8_strict: bool | None) -> dict:
    return await run_walk_forward(
        label=LABEL,
        symbols=SYMBOLS,
        signal_fn=_make_signal(a8_strict),
        start_date=start,
        initial_balance=balance,
        min_bars=60,
        amount_fn=_amount_fn,
    )


def tg_send(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
        }).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=20) as r:
            r.read()
        print("[TG] Gönderildi")
    except Exception as e:
        print(f"[TG] Hata: {e}")


def build_tg_report(r: dict, start_label: str, mode_label: str) -> str:
    sep = "━" * 28
    ret = (r["final_balance"] / r["initial_balance"] - 1) * 100 if r["initial_balance"] else 0
    parts = [
        sep,
        "📊 <b>1Y BACKTEST — 15. Analiz</b>",
        "BTC→A6 MACD · ETH→A8 Jesse · SOL→A2",
        f"BTC+ETH+SOL · ${r['initial_balance']:.0f} başlangıç",
        f"Dönem: {start_label} → bugün",
        f"<i>A8 mod: {mode_label}</i>",
        "",
        f"<b>{r['label']}</b>",
        f"  {r['trades']} işlem  WR {r['win_rate_pct']}%  "
        f"P&L {'+' if r['total_pnl'] >= 0 else ''}${r['total_pnl']:.0f}  "
        f"MaxDD {r['max_drawdown_pct']}%  skip {r.get('skipped_signals', 0)}",
        f"  Bakiye ${r['initial_balance']:.0f} → ${r['final_balance']:.0f} ({ret:+.0f}%)",
    ]
    for sym, st in r["by_symbol"].items():
        name = sym.replace("USDT", "")
        parts.append(
            f"    {name}: {st['trades']}t WR{st['win_rate_pct']}% "
            f"{'+' if st['pnl'] >= 0 else ''}${st['pnl']:.0f}"
        )
    monthly = r.get("monthly_pnl") or {}
    if monthly:
        last3 = sorted(monthly.items())[-3:]
        parts.append("    Son aylar: " + ", ".join(
            f"{m} {'+' if p >= 0 else ''}${p:.0f}" for m, p in last3
        ))
    parts.append(sep)
    return "\n".join(parts)


async def main() -> None:
    p = argparse.ArgumentParser(description="15. Analiz 1Y backtest")
    p.add_argument("--balance", type=float, default=SANAL_INITIAL_BALANCE)
    p.add_argument("--start", default="2025-07-27", help="Başlangıç (YYYY-MM-DD İST)")
    p.add_argument("--loose", action="store_true", help="A8 gevşek mod")
    p.add_argument("--strict", action="store_true", help="A8 sıkı mod")
    p.add_argument("--telegram", action="store_true")
    args = p.parse_args()

    a8_strict: bool | None = None
    if args.strict:
        a8_strict = True
    elif args.loose:
        a8_strict = False
    mode = signal_mode_status() if a8_strict is None else {
        "a3a8_signal_mode_label": "sıkı (entry/kesişim)" if a8_strict else "gevşek (her saat)",
    }

    y, m, d = map(int, args.start.split("-"))
    start = datetime(y, m, d, 0, 0, 0, tzinfo=_TZ_TR)
    t0 = time.time()
    r = await run_backtest(start, args.balance, a8_strict)
    print_summary(r)
    with open(OUT_FILE, "w") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    print(f"→ {OUT_FILE} ({time.time() - t0:.0f}s)")
    if args.telegram:
        tg_send(build_tg_report(r, start.strftime("%d.%m.%Y"), mode["a3a8_signal_mode_label"]))


if __name__ == "__main__":
    asyncio.run(main())

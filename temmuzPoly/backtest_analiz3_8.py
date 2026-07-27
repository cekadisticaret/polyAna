#!/usr/bin/env python3
"""
3. Analiz (Freqtrade) + 8. Analiz (Jesse) — 1Y walk-forward backtest

Canlı trader / algo dosyalarına DOKUNULMAZ.
Saatlik BTC+SOL+ETH · $300 başlangıç · :05 open / :00 close
Skip: pm_system_control.json → a3a8_signal_strict (true=entry/kesişim, false=her saat)

  python3 temmuzPoly/backtest_analiz3_8.py --all --telegram
  python3 temmuzPoly/backtest_analiz3_8.py --analiz 3 --start 2025-07-27
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

from backtest_common import run_walk_forward, print_summary, Trade
from a3a8_signal_mode import a3_direction, a8_direction, is_a3a8_strict, signal_mode_status
from pm_trader_helpers import SANAL_INITIAL_BALANCE, symbol_wr_amount

_TZ_TR = ZoneInfo("Europe/Istanbul")
SYMBOLS = ["BTCUSDT", "SOLUSDT", "ETHUSDT"]
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID = "830754964"


def _history_as_dicts(history: list[Trade]) -> list[dict]:
    return [{"symbol": t.symbol, "win": t.win} for t in history]


def _amount_fn(history: list[Trade], sym: str) -> float:
    return symbol_wr_amount(_history_as_dicts(history), sym)


ANALIZ_CONFIG = {
    3: {
        "label": "3. ANALİZ FREQTRADE",
        "min_bars": 35,
        "out": "backtest_analiz3_1y.json",
    },
    8: {
        "label": "8. ANALİZ JESSE",
        "min_bars": 30,
        "out": "backtest_analiz8_1y.json",
    },
}


def _make_signal(analiz_id: int, strict: bool | None):
    def _fn(sym, kslice, open_ms, history, amount_fn):
        direction = (a3_direction if analiz_id == 3 else a8_direction)(kslice, strict=strict)
        if direction not in ("UP", "DOWN"):
            return None
        amount = amount_fn(history, sym) if amount_fn else SANAL_INITIAL_BALANCE / 20
        engine = "A3 Freqtrade" if analiz_id == 3 else "A8 Jesse EMA8/21"
        return {
            "predicted_dir": direction,
            "amount": amount,
            "entry_price": float(kslice[-1]["close"]),
            "extra": {"engine": engine},
        }
    return _fn


async def run_one(analiz_id: int, start: datetime, balance: float, strict: bool | None) -> dict:
    cfg = ANALIZ_CONFIG[analiz_id]
    return await run_walk_forward(
        label=cfg["label"],
        symbols=SYMBOLS,
        signal_fn=_make_signal(analiz_id, strict),
        start_date=start,
        initial_balance=balance,
        min_bars=cfg["min_bars"],
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


def build_tg_report(results: list[dict], start_label: str, mode_label: str) -> str:
    sep = "━" * 28
    parts = [
        sep,
        "📊 <b>1Y BACKTEST — Analiz 3 / 8</b>",
        f"BTC+SOL+ETH · ${results[0]['initial_balance']:.0f} başlangıç",
        f"Dönem: {start_label} → bugün",
        f"<i>Mod: {mode_label}</i>",
        "<i>PM token 0.50 sim · WR tier $12/$16/$20</i>",
        "",
    ]
    for r in results:
        ret = (r["final_balance"] / r["initial_balance"] - 1) * 100 if r["initial_balance"] else 0
        parts.append(f"<b>{r['label']}</b>")
        parts.append(
            f"  {r['trades']} işlem  WR {r['win_rate_pct']}%  "
            f"P&L {'+' if r['total_pnl'] >= 0 else ''}${r['total_pnl']:.0f}  "
            f"MaxDD {r['max_drawdown_pct']}%  skip {r.get('skipped_signals', 0)}"
        )
        parts.append(
            f"  Bakiye ${r['initial_balance']:.0f} → ${r['final_balance']:.0f} ({ret:+.0f}%)"
        )
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
        parts.append("")
    parts.append(sep)
    return "\n".join(parts)


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--analiz", type=int, choices=[3, 8], help="Tek analiz")
    p.add_argument("--all", action="store_true", help="3+8 hepsi")
    p.add_argument("--balance", type=float, default=SANAL_INITIAL_BALANCE)
    p.add_argument("--start", default="2025-07-27", help="Başlangıç (YYYY-MM-DD İST)")
    p.add_argument("--loose", action="store_true", help="Gevşek mod (pm_system_control yok say)")
    p.add_argument("--strict", action="store_true", help="Sıkı mod (pm_system_control yok say)")
    p.add_argument("--telegram", action="store_true")
    args = p.parse_args()

    if not args.analiz and not args.all:
        args.all = True

    strict_override: bool | None = None
    if args.strict:
        strict_override = True
    elif args.loose:
        strict_override = False
    mode = signal_mode_status() if strict_override is None else {
        "a3a8_signal_mode_label": "sıkı (entry/kesişim)" if strict_override else "gevşek (her saat)",
    }

    y, m, d = map(int, args.start.split("-"))
    start = datetime(y, m, d, 0, 0, 0, tzinfo=_TZ_TR)
    start_label = start.strftime("%d.%m.%Y")

    ids = [3, 8] if args.all else [args.analiz]
    t0 = time.time()
    results: list[dict] = []
    for aid in ids:
        r = await run_one(aid, start, args.balance, strict_override)
        print_summary(r)
        out = os.path.join(_DIR, ANALIZ_CONFIG[aid]["out"])
        with open(out, "w") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
        print(f"→ {out}")
        results.append(r)

    print(f"\nToplam süre: {time.time() - t0:.0f}s")
    if args.telegram and results:
        tg_send(build_tg_report(results, start_label, mode["a3a8_signal_mode_label"]))


if __name__ == "__main__":
    asyncio.run(main())

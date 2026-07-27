#!/usr/bin/env python3
"""
1. Analiz — walk-forward backtest (BTC+SOL, saatlik)

poly_trader_analiz1.py ve poly_predictor_analysis.py DOKUNULMAZ.
Canlı mantık kopyası:
  - :05 open → predict() (boşsa atla, fallback yok)
  - :00 close → entry vs 1h kapanış
  - Semboller: BTCUSDT, SOLUSDT (aynı saatte ikisi de açılabilir)
  - Tutar: $12 / $16 / $20 (sembol WR tier)
  - Bakiye: açılışta düşülmez, kapanışta sanal_pnl eklenir (Analiz 1 modeli)

Not: CVD/orderbook/funding geçmişi yok → predict'e nötr flow enjekte edilir.
PM token sabit 0.50 (gamma simülasyonu).
Hafta sonu: Cum 22:00 – Pzt 08:00 İST open+close kapalı (canlı A1 ile aynı).
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
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import poly_predictor_analysis as pa
from poly_predictor_analysis import predict
from backtest_analiz2 import fetch_klines_history, _neutral_preloaded
from pm_trader_helpers import in_weekend_pause_tr

_TZ_TR = ZoneInfo("Europe/Istanbul")

INITIAL_BALANCE = 1000.0
TRADE_AMOUNT = 16.0
TRADE_AMOUNT_HIGH = 20.0
TRADE_AMOUNT_LOW = 12.0
SYMBOLS = ["BTCUSDT", "SOLUSDT"]
TOKEN_SIM = 0.50

BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID = "830754964"


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    symbol: str
    predicted_dir: str
    actual_dir: str
    win: bool
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    balance_after: float


def _apply_synthetic_pm(pos: dict, amount: float) -> None:
    pos["pm_spent"] = amount
    pos["pm_size"] = round(amount / TOKEN_SIM, 2)
    pos["pm_entry_price"] = TOKEN_SIM
    pos["to_win"] = pos["pm_size"]


def _resolve_pnl(pos: dict, win: bool) -> float:
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    size = float(pos.get("pm_size") or 0)
    if size > 0 and spent > 0:
        return round(size - spent, 2) if win else round(-spent, 2)
    return round(-spent, 2) if not win else 0.0


def _dyn_amount(history: list[Trade], symbol: str) -> float:
    sym_hist = [t for t in history if t.symbol == symbol]
    if not sym_hist:
        return TRADE_AMOUNT
    wins = sum(1 for t in sym_hist if t.win)
    rate = wins / len(sym_hist)
    if rate > 0.5:
        return TRADE_AMOUNT_HIGH
    if rate < 0.5:
        return TRADE_AMOUNT_LOW
    return TRADE_AMOUNT


async def run_backtest(
    start_date: datetime,
    end_date: datetime | None = None,
    initial_balance: float = INITIAL_BALANCE,
) -> dict:
    end = end_date or datetime.now(timezone.utc)
    warmup_days = 5
    fetch_start = start_date - timedelta(days=warmup_days + 3)
    test_start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    warmup = 60

    bars_by_sym: dict[str, list[dict]] = {}
    for sym in SYMBOLS:
        print(f"Veri çekiliyor: {sym} 1h...")
        bars = await fetch_klines_history(
            sym, "1h",
            int(fetch_start.timestamp() * 1000),
            end_ms,
        )
        if len(bars) < 100:
            raise RuntimeError(f"Yetersiz veri {sym}: {len(bars)} bar")
        bars_by_sym[sym] = bars

    # ortak zaman ekseni — en kısa seri
    min_len = min(len(b) for b in bars_by_sym.values())

    balance = initial_balance
    total_pnl = 0.0
    history: list[Trade] = []
    open_pos: dict[str, dict] = {}
    skipped = 0
    skipped_weekend = 0

    for i in range(warmup, min_len - 1):
        ref_bar = bars_by_sym[SYMBOLS[0]][i]
        if ref_bar["open_time"] < test_start_ms and not open_pos:
            nxt = bars_by_sym[SYMBOLS[0]][i + 1]["open_time"] if i + 1 < min_len else 0
            if nxt < test_start_ms:
                continue

        # ── CLOSE ──
        for sym in SYMBOLS:
            pos = open_pos.get(sym)
            if pos is None or pos["settle_idx"] != i:
                continue
            bar = bars_by_sym[sym][i]
            entry = pos["entry_price"]
            exit_p = bar["close"]
            pred = pos["predicted_dir"]
            actual = "UP" if exit_p >= entry else "DOWN"
            win = pred == actual
            pnl = _resolve_pnl(pos, win)
            balance = round(balance + pnl, 2)
            total_pnl = round(total_pnl + pnl, 2)

            ts_open = datetime.fromtimestamp(pos["open_ms"] / 1000, tz=timezone.utc)
            ts_close = datetime.fromtimestamp(bar["open_time"] / 1000 + 3600, tz=timezone.utc)
            if in_weekend_pause_tr(ts_close.astimezone(_TZ_TR)):
                pos["settle_idx"] = i + 1
                skipped_weekend += 1
                continue
            if ts_open.timestamp() >= start_date.timestamp():
                history.append(Trade(
                    entry_time=ts_open.astimezone(_TZ_TR).isoformat(),
                    exit_time=ts_close.astimezone(_TZ_TR).isoformat(),
                    symbol=sym,
                    predicted_dir=pred,
                    actual_dir=actual,
                    win=win,
                    entry_price=entry,
                    exit_price=exit_p,
                    amount=pos["amount"],
                    pnl=pnl,
                    balance_after=balance,
                ))
            del open_pos[sym]

        # ── OPEN ──
        if i + 1 >= min_len:
            continue
        nxt_ms = bars_by_sym[SYMBOLS[0]][i + 1]["open_time"]
        if nxt_ms < test_start_ms:
            continue

        open_ms = nxt_ms + 5 * 60 * 1000
        open_tr = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc).astimezone(_TZ_TR)
        if in_weekend_pause_tr(open_tr):
            skipped_weekend += 1
            continue

        for sym in SYMBOLS:
            if sym in open_pos:
                continue
            bars = bars_by_sym[sym]
            kslice = bars[max(0, i - 59): i + 1]
            if len(kslice) < 30:
                continue

            pa._slot_utc_ms = open_ms
            pred = await predict(sym, preloaded=_neutral_preloaded(kslice), kill_zone=False)
            if pred is None:
                skipped += 1
                continue

            amount = _dyn_amount(history, sym)
            pos = {
                "symbol": sym,
                "predicted_dir": pred.predicted_dir,
                "entry_price": bars[i]["close"],
                "amount": amount,
                "settle_idx": i + 1,
                "open_ms": open_ms,
            }
            _apply_synthetic_pm(pos, amount)
            open_pos[sym] = pos

    pa._slot_utc_ms = None

    wins = sum(1 for t in history if t.win)
    total = len(history)
    wr = wins / total * 100 if total else 0.0
    monthly: dict[str, float] = {}
    sym_stats: dict[str, dict] = {}
    for t in history:
        mk = t.entry_time[:7]
        monthly[mk] = round(monthly.get(mk, 0) + t.pnl, 2)
        s = sym_stats.setdefault(t.symbol, {"w": 0, "n": 0, "pnl": 0.0})
        s["n"] += 1
        s["pnl"] = round(s["pnl"] + t.pnl, 2)
        if t.win:
            s["w"] += 1

    peak = initial_balance
    max_dd = 0.0
    for t in history:
        peak = max(peak, t.balance_after)
        dd = (peak - t.balance_after) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    first = history[0].entry_time[:10] if history else "—"
    last = history[-1].entry_time[:10] if history else "—"

    return {
        "symbols": SYMBOLS,
        "start_date": start_date.astimezone(_TZ_TR).strftime("%Y-%m-%d"),
        "end_date": end.astimezone(_TZ_TR).strftime("%Y-%m-%d"),
        "period": f"{first} → {last}",
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate_pct": round(wr, 1),
        "max_drawdown_pct": round(max_dd, 1),
        "skipped_signals": skipped,
        "skipped_weekend": skipped_weekend,
        "weekend_pause": "Cum 22:00 – Pzt 08:00 İST",
        "monthly_pnl": monthly,
        "by_symbol": {
            k: {
                "trades": v["n"],
                "wins": v["w"],
                "win_rate_pct": round(v["w"] / v["n"] * 100, 1) if v["n"] else 0,
                "pnl": v["pnl"],
            }
            for k, v in sym_stats.items()
        },
        "trade_list": [asdict(t) for t in history],
    }


def _print_summary(r: dict) -> None:
    print("\n" + "=" * 52)
    print("  1. ANALİZ BACKTEST — BTC+SOL")
    print("=" * 52)
    print(f"  Dönem      : {r['period']}")
    print(f"  İşlem      : {r['trades']} ({r['wins']}W / {r['losses']}L)")
    print(f"  Win rate   : {r['win_rate_pct']}%")
    print(f"  P&L        : {'+' if r['total_pnl']>=0 else ''}${r['total_pnl']:.2f}")
    print(f"  Bakiye     : ${r['initial_balance']:.0f} → ${r['final_balance']:.2f}")
    print(f"  Max DD     : {r['max_drawdown_pct']}%")
    print(f"  Atlanan    : {r['skipped_signals']} saat (predict boş)")
    print(f"  Hafta sonu : {r.get('skipped_weekend', 0)} slot (Cum 22 – Pzt 08)")
    for sym, st in r["by_symbol"].items():
        name = sym.replace("USDT", "")
        print(f"  {name:4s}       : {st['trades']} işlem  WR {st['win_rate_pct']}%  P&L {'+' if st['pnl']>=0 else ''}${st['pnl']:.0f}")
    print("\n  Aylık P&L:")
    for m, p in sorted(r["monthly_pnl"].items()):
        print(f"    {m}: {'+' if p>=0 else ''}${p:.2f}")
    print("=" * 52)


def tg_send(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
        print("[TG] Gönderildi")
    except Exception as e:
        print(f"[TG] Hata: {e}")


def _month_label(ym: str) -> str:
    names = ("", "Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")
    try:
        y, m = ym.split("-")
        return f"{names[int(m)]} {y}"
    except Exception:
        return ym


def build_tg_report(r: dict) -> str:
    sep = "━" * 28
    sym_lines = []
    for sym, st in r["by_symbol"].items():
        name = sym.replace("USDT", "")
        sym_lines.append(
            f"  {name}: {st['trades']} işlem  WR {st['win_rate_pct']}%  "
            f"P&L {'+' if st['pnl'] >= 0 else ''}${st['pnl']:.0f}"
        )
    monthly = "\n".join(
        f"  {_month_label(m)}: {'+' if p >= 0 else ''}${p:.0f}"
        for m, p in sorted(r["monthly_pnl"].items())
    )
    ret = (r["final_balance"] / r["initial_balance"] - 1) * 100
    return "\n".join([
        sep,
        "📊 <b>A1 — 1Y BACKTEST</b>",
        f"1. Analiz motoru · BTC+SOL · ${r['initial_balance']:.0f} başlangıç",
        f"Dönem: {r['period']}",
        "",
        f"İşlem: {r['trades']} ({r['wins']}W/{r['losses']}L)  WR: {r['win_rate_pct']}%",
        f"P&L: {'+' if r['total_pnl'] >= 0 else ''}${r['total_pnl']:.0f}",
        f"Bakiye: ${r['initial_balance']:.0f} → ${r['final_balance']:.0f} ({ret:+.0f}%)",
        f"Max DD: {r['max_drawdown_pct']}%",
        f"Hafta sonu atlanan: {r.get('skipped_weekend', 0)} slot (Cum 22 – Pzt 08)",
        "",
        "<b>Sembol bazlı</b>",
        *sym_lines,
        "",
        "<b>Aylık P&amp;L</b>",
        monthly,
        "",
        "<i>predict() · fallback yok · PM 0.50 sim · $12/$16/$20 · Cum 22–Pzt 08 kapalı</i>",
        sep,
    ])


async def main():
    p = argparse.ArgumentParser(description="1. Analiz backtest")
    p.add_argument("--balance", type=float, default=1000.0)
    p.add_argument("--start", default="2025-07-17", help="Başlangıç tarihi (YYYY-MM-DD İST)")
    p.add_argument("--telegram", action="store_true")
    p.add_argument("--out", default=os.path.join(_DIR, "backtest_analiz1_1y.json"))
    args = p.parse_args()

    y, m, d = map(int, args.start.split("-"))
    start = datetime(y, m, d, 0, 0, 0, tzinfo=_TZ_TR)

    t0 = time.time()
    result = await run_backtest(start_date=start, initial_balance=args.balance)
    _print_summary(result)

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nTam liste → {args.out} ({time.time()-t0:.0f}s)")

    if args.telegram:
        tg_send(build_tg_report(result))


if __name__ == "__main__":
    asyncio.run(main())

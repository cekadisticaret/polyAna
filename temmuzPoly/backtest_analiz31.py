#!/usr/bin/env python3
"""
31. Analiz — 1Y walk-forward backtest (BTC+SOL, Multi-TF MR v1.1)

Analiz31/ DOKUNULMAZ — predict() import edilir.
CVD: 15m bar proxy (5m/30m tam geçmişi çekilmez — hız için).
"""
from __future__ import annotations

import argparse
import asyncio
import bisect
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_A31 = os.path.join(os.path.dirname(_DIR), "Analiz31")
sys.path.insert(0, _DIR)
sys.path.insert(0, _A31)

from backtest_analiz2 import fetch_klines_history
from backtest_common import Trade, apply_synthetic_pm, resolve_pnl, print_summary
from config import TIMEFRAMES
from features import extract_all_features
from predictor import predict as a31_predict
import scorer as a31_scorer

_TZ_TR = ZoneInfo("Europe/Istanbul")
INITIAL_BALANCE = 1000.0
SYMBOLS = ["BTCUSDT", "SOLUSDT"]
INTERVAL_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}
FETCH_TFS = ["15m", "1h", "4h", "1d"]
CACHE_FILE = os.path.join(_DIR, "backtest_analiz31_cache.json")

BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID = "830754964"


class BarIndex:
    """Kapalı barlar için O(log n) dilimleme."""

    def __init__(self, bars: list[dict], interval: str):
        self.bars = bars
        self.close_times = [b["open_time"] + INTERVAL_MS[interval] for b in bars]

    def slice(self, end_ms: int, limit: int) -> list[dict]:
        idx = bisect.bisect_right(self.close_times, end_ms)
        start = max(0, idx - limit)
        return self.bars[start:idx]


def _cvd_from_bars(bars: list[dict]) -> float:
    if not bars:
        return 0.0
    total_vol = sum(b["volume"] for b in bars)
    taker_buy = sum(b.get("taker_buy", b["volume"] * 0.5) for b in bars)
    return (2 * taker_buy - total_vol) / total_vol if total_vol else 0.0


def _build_raw(idx: dict[str, BarIndex], end_ms: int) -> dict:
    tf = {name: idx[name].slice(end_ms, cfg["limit"]) for name, cfg in TIMEFRAMES.items()}
    b15 = idx["15m"].slice(end_ms, 8)
    cvd_5m = _cvd_from_bars(b15[-6:] if len(b15) >= 6 else b15)
    cvd_30m = _cvd_from_bars(b15[-2:] if len(b15) >= 2 else b15)
    return {
        "timeframes": tf,
        "cvd_5m": cvd_5m,
        "cvd_30m": cvd_30m,
        "orderbook": 0.5,
    }


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


async def _load_cache(fetch_ms: int, end_ms: int, use_disk: bool) -> dict[str, dict[str, BarIndex]]:
    if use_disk and os.path.exists(CACHE_FILE):
        mtime = os.path.getmtime(CACHE_FILE)
        if time.time() - mtime < 86400:
            print(f"[cache] disk'ten yükleniyor: {CACHE_FILE}")
            with open(CACHE_FILE) as f:
                raw = json.load(f)
            return {
                sym: {tf: BarIndex(raw[sym][tf], tf) for tf in FETCH_TFS}
                for sym in SYMBOLS
            }

    out: dict[str, dict[str, list]] = {}
    for sym in SYMBOLS:
        out[sym] = {}
        print(f"[31. ANALİZ] {sym} veri...")
        for tf in FETCH_TFS:
            out[sym][tf] = await fetch_klines_history(sym, tf, fetch_ms, end_ms)
            print(f"  {tf}: {len(out[sym][tf])} bar")

    if use_disk:
        with open(CACHE_FILE, "w") as f:
            json.dump(out, f)
        print(f"[cache] kaydedildi → {CACHE_FILE}")

    return {
        sym: {tf: BarIndex(out[sym][tf], tf) for tf in FETCH_TFS}
        for sym in SYMBOLS
    }


async def run_backtest(
    start_date: datetime,
    initial_balance: float = INITIAL_BALANCE,
    use_disk_cache: bool = True,
) -> dict:
    end = datetime.now(timezone.utc)
    fetch_start = start_date - timedelta(days=45)
    test_start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    fetch_ms = int(fetch_start.timestamp() * 1000)

    cache = await _load_cache(fetch_ms, end_ms, use_disk_cache)
    bars_1h = {sym: cache[sym]["1h"].bars for sym in SYMBOLS}
    min_len = min(len(bars_1h[s]) for s in SYMBOLS)
    warmup = 60
    total_steps = min_len - warmup - 1

    balance = initial_balance
    total_pnl = 0.0
    history: list[Trade] = []
    open_pos: dict[str, dict] = {}
    skipped = 0
    t_loop = time.time()

    for step, i in enumerate(range(warmup, min_len - 1), 1):
        if step % 1000 == 0:
            elapsed = time.time() - t_loop
            print(f"  simülasyon {step}/{total_steps} ({elapsed:.0f}s)...")

        if bars_1h[SYMBOLS[0]][i]["open_time"] < test_start_ms and not open_pos:
            if bars_1h[SYMBOLS[0]][i + 1]["open_time"] < test_start_ms:
                continue

        for sym in SYMBOLS:
            pos = open_pos.get(sym)
            if pos is None or pos["settle_idx"] != i:
                continue
            bar = bars_1h[sym][i]
            entry, exit_p = pos["entry_price"], bar["close"]
            pred = pos["predicted_dir"]
            actual = "UP" if exit_p >= entry else "DOWN"
            win = pred == actual
            pnl = resolve_pnl(pos, win)
            balance = round(balance + pnl, 2)
            total_pnl = round(total_pnl + pnl, 2)

            ts_open = datetime.fromtimestamp(pos["open_ms"] / 1000, tz=timezone.utc)
            if ts_open.timestamp() >= start_date.timestamp():
                ts_close = datetime.fromtimestamp(bar["open_time"] / 1000 + 3600, tz=timezone.utc)
                history.append(Trade(
                    entry_time=ts_open.astimezone(_TZ_TR).isoformat(),
                    exit_time=ts_close.astimezone(_TZ_TR).isoformat(),
                    symbol=sym, predicted_dir=pred, actual_dir=actual, win=win,
                    entry_price=entry, exit_price=exit_p, amount=pos["amount"],
                    pnl=pnl, balance_after=balance, extra=pos.get("extra"),
                ))
            del open_pos[sym]

        if i + 1 >= min_len or bars_1h[SYMBOLS[0]][i + 1]["open_time"] < test_start_ms:
            continue

        open_ms = bars_1h[SYMBOLS[0]][i + 1]["open_time"] + 5 * 60 * 1000
        feature_end_ms = bars_1h[SYMBOLS[0]][i]["open_time"] + INTERVAL_MS["1h"]

        for sym in SYMBOLS:
            if sym in open_pos:
                continue
            raw = _build_raw(cache[sym], feature_end_ms)
            if len(raw["timeframes"].get("1h", [])) < 30:
                skipped += 1
                continue

            features = extract_all_features(raw)

            def _fake_now(tz=None, _ms=open_ms):
                t = datetime.fromtimestamp(_ms / 1000, tz=timezone.utc)
                return t.astimezone(tz) if tz else t

            with patch.object(a31_scorer, "datetime") as mock_dt:
                mock_dt.now = _fake_now
                hour_ist = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc).astimezone(_TZ_TR).hour
                pred = a31_predict(sym, {"features": features, "hour_ist": hour_ist})

            if pred is None or not pred.predicted_dir:
                skipped += 1
                continue

            amount = _dyn_amount(history, sym)
            pos = {
                "symbol": sym,
                "predicted_dir": pred.predicted_dir,
                "entry_price": bars_1h[sym][i]["close"],
                "amount": amount,
                "settle_idx": i + 1,
                "open_ms": open_ms,
                "extra": {
                    "up_score": pred.up_score, "down_score": pred.down_score,
                    "up_gate": pred.up_gate, "down_gate": pred.down_gate,
                    "htf_bias": pred.htf_bias,
                },
            }
            apply_synthetic_pm(pos, amount)
            open_pos[sym] = pos

    wins = sum(1 for t in history if t.win)
    total = len(history)
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

    peak, max_dd = initial_balance, 0.0
    for t in history:
        peak = max(peak, t.balance_after)
        max_dd = max(max_dd, (peak - t.balance_after) / peak * 100 if peak else 0)

    first = history[0].entry_time[:10] if history else "—"
    last = history[-1].entry_time[:10] if history else "—"

    return {
        "label": "31. ANALİZ",
        "symbols": SYMBOLS,
        "period": f"{first} → {last}",
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate_pct": round(wins / total * 100, 1) if total else 0.0,
        "max_drawdown_pct": round(max_dd, 1),
        "skipped_signals": skipped,
        "monthly_pnl": monthly,
        "by_symbol": {
            k: {
                "trades": v["n"], "wins": v["w"],
                "win_rate_pct": round(v["w"] / v["n"] * 100, 1) if v["n"] else 0,
                "pnl": v["pnl"],
            }
            for k, v in sym_stats.items()
        },
        "trade_list": [asdict(t) for t in history],
    }


def tg_send(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=15) as r:
            r.read()
        print("[TG] Gönderildi")
    except Exception as e:
        print(f"[TG] Hata: {e}")


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
        sep, "📊 <b>31. ANALİZ — 1Y BACKTEST (v1.1)</b>",
        f"BTC+SOL · ${r['initial_balance']:.0f} · {r['period']}", "",
        f"İşlem: {r['trades']} ({r['wins']}W/{r['losses']}L)  WR: {r['win_rate_pct']}%",
        f"P&L: {'+' if r['total_pnl']>=0 else ''}${r['total_pnl']:.0f}",
        f"Bakiye: ${r['initial_balance']:.0f} → ${r['final_balance']:.0f} ({ret:+.0f}%)",
        f"Max DD: {r['max_drawdown_pct']}%  |  skip: {r['skipped_signals']}", "",
        "<b>Sembol</b>", *sym_lines, "", "<b>Aylık P&L</b>", monthly, "",
        "<i>Multi-TF v1.1 · CVD=15m proxy · PM 0.50</i>", sep,
    ])


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--balance", type=float, default=INITIAL_BALANCE)
    p.add_argument("--start", default="2025-07-17")
    p.add_argument("--telegram", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--out", default=os.path.join(_DIR, "backtest_analiz31_1y.json"))
    args = p.parse_args()

    y, m, d = map(int, args.start.split("-"))
    start = datetime(y, m, d, 0, 0, 0, tzinfo=_TZ_TR)

    t0 = time.time()
    result = await run_backtest(start, args.balance, use_disk_cache=not args.no_cache)
    print_summary(result)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n→ {args.out} ({time.time()-t0:.0f}s)")
    if args.telegram:
        tg_send(build_tg(result))


if __name__ == "__main__":
    asyncio.run(main())

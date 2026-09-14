#!/usr/bin/env python3
"""İzleme kartları — 1Y walk-forward (F16 · A2#03 · A2#05 · F16V2 · JARVIS2026).

Cron: 00:00 İST (`0 21 * * *` UTC). Emir yok. Telegram yok.
F16 = canlı ile aynı: BTC+SOL · predict(). F16V2 = o F16 + ETH A2#03.
JARVIS: güncel fikir (path_trend / reversion); follow yoksa path_trend.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import algo_signals as sig
from algo_signals_v2 import ALGO_V2_META
from backtest_algo_islemler_1y import (
    THREE,
    WARMUP,
    _fn_dir,
    fetch_klines,
)
from backtest_selected_algos_1y import _dir_a1
from backtest_pm import fill_position_quote
from pm_trader_helpers import sanal_pnl, wr_tier_amount

_TZ = ZoneInfo("Europe/Istanbul")
OUT = os.path.join(_DIR, "backtest_watch_1y.json")
POLICY = os.path.join(_DIR, "jarvis2026_policy.json")
INITIAL = 1000.0
F16_SYMS = ["BTCUSDT", "SOLUSDT"]
_A2_FN = {f"a2_{n:02d}": fn for n, _name, _cat, kind, fn in ALGO_V2_META if kind == "fn"}


def _stake(hist: list, sym: str, lo: float, mid: float, hi: float) -> float:
    return wr_tier_amount(hist, sym, lo, mid, hi)


def _load_jarvis_idea(sym: str) -> dict:
    try:
        pol = json.loads(open(POLICY, encoding="utf-8").read())
    except Exception:
        pol = {}
    for raw in pol.get("ideas") or []:
        if str(raw.get("symbol") or "") == sym:
            return raw
    return {
        "dir_mode": "path_trend",
        "ask_max": 0.45,
        "path_abs_bps": 10.0,
    }


def _path_dir(bar: dict, mode: str, abs_bps: float) -> str | None:
    ref = float(bar["open"])
    if ref <= 0:
        return None
    up = (float(bar["high"]) - ref) / ref * 10000.0
    dn = (ref - float(bar["low"])) / ref * 10000.0
    hit_up = up >= abs_bps
    hit_dn = dn >= abs_bps
    if hit_up and hit_dn:
        return None
    if not hit_up and not hit_dn:
        return None
    above = hit_up
    if mode == "path_reversion":
        return "DOWN" if above else "UP"
    return "UP" if above else "DOWN"


def _simulate_signal(
    key: str,
    label: str,
    dirs: dict[str, list],
    bars: dict[str, list],
    start_ms: int,
    *,
    lo: float,
    mid: float,
    hi: float,
    ask_max: float | None = None,
    symbols: list[str] | None = None,
) -> dict:
    n = min(len(v) for v in bars.values())
    hist: list[dict] = []
    bal = INITIAL
    pnl = 0.0
    skipped = 0
    by_sym = {s: {"n": 0, "w": 0, "pnl": 0.0} for s in THREE}
    months: dict[str, float] = defaultdict(float)
    coins = symbols or THREE
    for i in range(WARMUP, n - 1):
        nxt_t = bars[THREE[0]][i + 1]["open_time"]
        if nxt_t < start_ms:
            continue
        for sym in coins:
            d = dirs.get(sym, [None] * n)[i]
            if d not in ("UP", "DOWN"):
                skipped += 1
                continue
            kslice = bars[sym][max(0, i - 199): i + 1]
            nxt = bars[sym][i + 1]
            amt = _stake(hist, sym, lo, mid, hi)
            q = fill_position_quote(sym, d, amt, kslice, nxt)
            if not q:
                skipped += 1
                continue
            ask = float(q.get("pm_entry_price") or 0)
            if ask_max is not None and ask > ask_max:
                skipped += 1
                continue
            actual = "UP" if nxt["close"] > nxt["open"] else "DOWN"
            win = d == actual
            trade_pnl = sanal_pnl(q, win)
            bal = round(bal + trade_pnl, 2)
            pnl = round(pnl + trade_pnl, 4)
            hist.append({"symbol": sym, "win": win, "pnl": trade_pnl, "t": nxt_t})
            by_sym[sym]["n"] += 1
            by_sym[sym]["w"] += int(win)
            by_sym[sym]["pnl"] += trade_pnl
            mo = datetime.fromtimestamp(nxt_t / 1000, tz=_TZ).strftime("%Y-%m")
            months[mo] += trade_pnl
    return _pack(key, label, hist, bal, pnl, skipped, by_sym, months)


def _simulate_jarvis(bars: dict[str, list], start_ms: int) -> dict:
    """Önceki saatin tamamlanmış yolu → bu saatte giriş (dakika verisi yok, sızdırmaz)."""
    n = min(len(v) for v in bars.values())
    hist: list[dict] = []
    bal = INITIAL
    pnl = 0.0
    skipped = 0
    by_sym = {s: {"n": 0, "w": 0, "pnl": 0.0} for s in THREE}
    months: dict[str, float] = defaultdict(float)
    ideas = {s: _load_jarvis_idea(s) for s in THREE}
    for i in range(WARMUP + 1, n):
        t = bars[THREE[0]][i]["open_time"]
        if t < start_ms:
            continue
        for sym in THREE:
            idea = ideas[sym]
            mode = str(idea.get("dir_mode") or "path_trend")
            if mode not in ("path_trend", "path_reversion"):
                mode = "path_trend"
            abs_bps = float(idea.get("path_abs_bps") or 10)
            prev = bars[sym][i - 1]
            bar = bars[sym][i]
            d = _path_dir(prev, mode, abs_bps)
            if d not in ("UP", "DOWN"):
                skipped += 1
                continue
            # CLOB yok. Ask = önceki kapanış vs bu saat açılışı (bu saatin close yok).
            kslice = bars[sym][max(0, i - 199): i]
            q = fill_position_quote(
                sym, d, _stake(hist, sym, 16, 24, 32), kslice, bar,
            )
            if not q:
                skipped += 1
                continue
            actual = "UP" if bar["close"] > bar["open"] else "DOWN"
            win = d == actual
            trade_pnl = sanal_pnl(q, win)
            bal = round(bal + trade_pnl, 2)
            pnl = round(pnl + trade_pnl, 4)
            hist.append({"symbol": sym, "win": win, "pnl": trade_pnl, "t": t})
            by_sym[sym]["n"] += 1
            by_sym[sym]["w"] += int(win)
            by_sym[sym]["pnl"] += trade_pnl
            mo = datetime.fromtimestamp(t / 1000, tz=_TZ).strftime("%Y-%m")
            months[mo] += trade_pnl
    return _pack("jarvis2026", "JARVIS2026", hist, bal, pnl, skipped, by_sym, months)


def _pack(key, label, hist, bal, pnl, skipped, by_sym, months) -> dict:
    trades = len(hist)
    wins = sum(1 for t in hist if t["win"])
    by = {}
    for s, r in by_sym.items():
        by[s] = {
            "trades": r["n"],
            "wins": r["w"],
            "wr": round(100.0 * r["w"] / r["n"], 1) if r["n"] else None,
            "pnl": round(r["pnl"], 2),
        }
    return {
        "id": key,
        "label": label,
        "final_balance": round(bal, 2),
        "total_pnl": round(pnl, 2),
        "trades": trades,
        "wins": wins,
        "win_rate_pct": round(100.0 * wins / trades, 1) if trades else None,
        "skipped": skipped,
        "by_symbol": by,
        "monthly_pnl": {k: round(v, 2) for k, v in sorted(months.items())},
        **(
            {"note": "BTC+SOL · predict()"} if key == "analiz1"
            else {"note": "BTC/SOL F16 predict · ETH A2#03"} if key == "f16v2"
            else {"note": "önceki saat yolu · CLOB ask yok"} if key == "jarvis2026"
            else {}
        ),
    }


def _dirs_a2(key: str, bars: dict[str, list], symbols: list[str] | None = None) -> dict[str, list]:
    n = min(len(v) for v in bars.values())
    out = {s: [None] * n for s in THREE}
    fn = _A2_FN.get(key) or (sig.stoch_rsi if key == "a2_03" else sig.mean_reversion)
    coins = symbols or THREE
    for i in range(WARMUP, n - 1):
        for s in coins:
            win = bars[s][max(0, i - 199): i + 1]
            d = _fn_dir(fn, win)
            out[s][i] = d if d in ("UP", "DOWN") else None
    return out


async def _dirs_f16(bars: dict[str, list]) -> dict[str, list]:
    """Canlı F16: yalnız BTC+SOL, poly_predictor predict()."""
    n = min(len(v) for v in bars.values())
    out = {s: [None] * n for s in THREE}
    for i in range(WARMUP, n - 1):
        if i % 500 == 0:
            print(f"  [f16] {i}/{n}", flush=True)
        open_ms = bars[THREE[0]][i + 1]["open_time"] + 5 * 60 * 1000
        for s in F16_SYMS:
            win = bars[s][max(0, i - 199): i + 1]
            d = await _dir_a1(s, win, open_ms)
            out[s][i] = d if d in ("UP", "DOWN") else None
    return out


async def run() -> dict:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365)
    fetch_start = start - timedelta(days=12)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    bars = {}
    for sym in THREE:
        print(f"[watch-1y] veri {sym}", flush=True)
        bars[sym] = await fetch_klines(sym, int(fetch_start.timestamp() * 1000), end_ms)
        print(f"  {len(bars[sym])} bar", flush=True)
    n = min(len(v) for v in bars.values())
    keep = set(bars[THREE[0]][i]["open_time"] for i in range(n))
    for s in THREE[1:]:
        keep &= {b["open_time"] for b in bars[s]}
    keep = sorted(keep)
    aligned = {}
    for s in THREE:
        by = {b["open_time"]: b for b in bars[s]}
        aligned[s] = [by[t] for t in keep]
    only = (os.environ.get("WATCH_1Y_ONLY") or "").strip()
    prev_algos = []
    if only and os.path.isfile(OUT):
        try:
            prev_algos = json.loads(open(OUT, encoding="utf-8").read()).get("algos") or []
        except Exception:
            prev_algos = []
    by_id = {str(a.get("id")): a for a in prev_algos}
    f16_dirs = None
    if only in ("", "f16", "analiz1", "f16v2"):
        print("[watch-1y] analiz1  BTC+SOL predict()", flush=True)
        f16_dirs = await _dirs_f16(aligned)
        by_id["analiz1"] = _simulate_signal(
            "analiz1", "F16", f16_dirs, aligned, start_ms,
            lo=24, mid=36, hi=48, symbols=F16_SYMS,
        )
    if only in ("", "f16", "f16v2"):
        print("[watch-1y] f16v2  BTC/SOL F16 · ETH A2#03", flush=True)
        if f16_dirs is None:
            f16_dirs = await _dirs_f16(aligned)
        v2 = {s: list(f16_dirs[s]) for s in THREE}
        eth = _dirs_a2("a2_03", aligned, ["ETHUSDT"])
        v2["ETHUSDT"] = eth["ETHUSDT"]
        by_id["f16v2"] = _simulate_signal(
            "f16v2", "F16V2", v2, aligned, start_ms,
            lo=24, mid=36, hi=48,
        )
    if only == "":
        for key, label in (("a2_03", "A2#03"), ("a2_05", "A2#05")):
            print(f"[watch-1y] {key}", flush=True)
            by_id[key] = _simulate_signal(
                key, label, _dirs_a2(key, aligned), aligned, start_ms,
                lo=24, mid=36, hi=48,
            )
        print("[watch-1y] jarvis2026", flush=True)
        by_id["jarvis2026"] = _simulate_jarvis(aligned, start_ms)
    order = ["analiz1", "a2_03", "a2_05", "f16v2", "jarvis2026"]
    books = [by_id[k] for k in order if k in by_id]
    out = {
        "generated_at_tr": datetime.now(_TZ).isoformat(),
        "period": f"{start.date()} → {end.date()}",
        "days": 365,
        "initial_balance": INITIAL,
        "algos": books,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    for b in books:
        print(
            f"  {b['id']:12s} n={b['trades']} WR={b['win_rate_pct']} "
            f"pnl={b['total_pnl']:+.0f}",
            flush=True,
        )
    return out


def main() -> int:
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

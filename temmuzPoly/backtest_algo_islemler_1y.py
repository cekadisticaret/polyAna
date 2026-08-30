#!/usr/bin/env python3
"""/algoritma-islemler defterleri — 1Y Poly walk-forward (BTC/ETH/SOL).

Aynı kasa $1000 · WR kademe $24/36/48 (COMBO $16/24/32 · COMBO2 $64).
Dolum: model ask + taker ücret (geçmiş CLOB yok).
fapi yok — spot/data-api.

  python3 temmuzPoly/backtest_algo_islemler_1y.py
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
sys.path.insert(0, _DIR)

import algo_signals as sig
from algo_signals_v2 import ALGO_V2_META
from analiz6_v3_signal import _SYMBOL_ENGINE as A6V3_ENGINE
from analiz6_v4_signal import _SYMBOL_ENGINE as MELEZ_ENGINE
from analiz15_signal import direction_a6, direction_a8
from backtest_pm import fill_position_quote, estimate_asks
from c101_signal import EDGE_MIN as C101_EDGE, evaluate, parkinson_sigma, _phi, _MIN_T_REMAIN
from poly_a2_algo_trader_core import entry_zscore
from pm_trader_helpers import wr_tier_amount, sanal_pnl
from poly_predictor_analysis import _rsi, _macd, _ema

_TZ = ZoneInfo("Europe/Istanbul")
THREE = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INITIAL = 1000.0
WARMUP = 80
A2_05_V2_Z = (1.0, 1.5)
C101_V2_EDGE = 0.03
OUT = os.path.join(_DIR, "backtest_algo_islemler_1y.json")
_KLINE_HOSTS = (
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
)

A1_SIMPLE = {
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
A1_SKIP_LIVE = {13, 14, 20, 21}  # grid/lstm + canlı OI/F&G


def _to_kl(bars: list[dict]) -> list[dict]:
    return [{"o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"],
             "v": b.get("volume", 0)} for b in bars]


def _resample_4h(bars: list[dict]) -> list[dict]:
    out, bucket = [], []
    for b in bars:
        bucket.append(b)
        if len(bucket) == 4:
            out.append({
                "open": bucket[0]["open"],
                "high": max(x["high"] for x in bucket),
                "low": min(x["low"] for x in bucket),
                "close": bucket[-1]["close"],
                "volume": sum(x["volume"] for x in bucket),
            })
            bucket = []
    return out


def rsi_macd_ema(bars: list[dict]) -> str | None:
    """A1/A2 predictor vekili — nötr flow, RSI+MACD+EMA oy."""
    if len(bars) < 26:
        return None
    closes = [b["close"] for b in bars]
    rsi = _rsi(closes)
    macd_val, macd_sig = _macd(closes)
    e9, e21 = _ema(closes, 9)[-1], _ema(closes, 21)[-1]
    votes = [
        1 if rsi < 50 else -1,
        1 if macd_val > macd_sig else -1,
        1 if e9 > e21 else -1,
    ]
    return "UP" if sum(votes) > 0 else "DOWN"


def _fn_dir(fn, bars: list[dict]) -> str | None:
    if fn is None or len(bars) < 30:
        return None
    try:
        d = fn(_to_kl(bars))
    except Exception:
        return None
    return d if d in ("UP", "DOWN") else None


def _c101_p_up(bars: list[dict], ptb: float, spot: float) -> float | None:
    kl = _to_kl(bars)
    if len(kl) < 14 or ptb <= 0 or spot <= 0:
        return None
    sig_s = parkinson_sigma(kl, 12)
    sig_l = parkinson_sigma(kl, 72)
    if sig_s is None and sig_l is None:
        return None
    if sig_s is None:
        sigma = sig_l
    elif sig_l is None:
        sigma = sig_s
    else:
        sigma = 0.6 * sig_s + 0.4 * sig_l
    if not sigma or sigma <= 0:
        return None
    denom = sigma * math.sqrt(max(_MIN_T_REMAIN, 0.92))
    if denom <= 0:
        return None
    return max(0.01, min(0.99, _phi(math.log(spot / ptb) / denom)))


async def fetch_klines(symbol: str, start_ms: int, end_ms: int) -> list[dict]:
    import aiohttp
    out, cur = [], start_ms
    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while cur < end_ms:
            params = {
                "symbol": symbol, "interval": "1h",
                "startTime": cur, "endTime": end_ms, "limit": 1000,
            }
            data = None
            for url in _KLINE_HOSTS:
                try:
                    async with session.get(url, params=params) as r:
                        raw = await r.json()
                    if isinstance(raw, list) and raw:
                        data = raw
                        break
                except Exception:
                    continue
            if not data:
                break
            for k in data:
                out.append({
                    "open_time": int(k[0]),
                    "open": float(k[1]), "high": float(k[2]),
                    "low": float(k[3]), "close": float(k[4]),
                    "volume": float(k[5]),
                    "taker_buy": float(k[9]) if len(k) > 9 else 0.0,
                })
            nxt = int(data[-1][0]) + 1
            if nxt <= cur:
                break
            cur = nxt
            if len(data) < 1000:
                break
            await asyncio.sleep(0.08)
    seen, deduped = set(), []
    for b in out:
        if b["open_time"] in seen:
            continue
        seen.add(b["open_time"])
        deduped.append(b)
    return deduped


def _align(bars_by_sym: dict[str, list[dict]]) -> dict[str, list[dict]]:
    common = None
    for bars in bars_by_sym.values():
        ts = {b["open_time"] for b in bars}
        common = ts if common is None else common & ts
    keep = sorted(common or [])
    out = {}
    for sym, bars in bars_by_sym.items():
        by = {b["open_time"]: b for b in bars}
        out[sym] = [by[t] for t in keep]
    return out


def _tiers(key: str) -> tuple[float, float, float]:
    if key == "combo":
        return 16.0, 24.0, 32.0
    if key == "combo2":
        return 64.0, 64.0, 64.0
    return 24.0, 36.0, 48.0


def _stake(key: str, hist: list[dict], sym: str) -> float:
    lo, mid, hi = _tiers(key)
    return wr_tier_amount(hist, sym, lo, mid, hi)


def simulate_book(
    key: str,
    label: str,
    dirs: dict[str, list[str | None]],
    bars_by_sym: dict[str, list[dict]],
    start_ms: int,
    extra_ok=None,
) -> dict:
    n = min(len(v) for v in bars_by_sym.values())
    hist: list[dict] = []
    bal = INITIAL
    pnl = 0.0
    skipped = 0
    fee_sum = 0.0
    by_sym = {s: {"n": 0, "w": 0, "pnl": 0.0} for s in THREE}
    months: dict[str, float] = defaultdict(float)
    for i in range(WARMUP, n - 1):
        nxt_t = bars_by_sym[THREE[0]][i + 1]["open_time"]
        if nxt_t < start_ms:
            continue
        for sym in THREE:
            d = dirs.get(sym, [None] * n)[i]
            if d not in ("UP", "DOWN"):
                continue
            kslice = bars_by_sym[sym][max(0, i - 199): i + 1]
            nxt = bars_by_sym[sym][i + 1]
            if extra_ok and not extra_ok(key, sym, kslice, nxt, d):
                skipped += 1
                continue
            amt = _stake(key, hist, sym)
            q = fill_position_quote(sym, d, amt, kslice, nxt)
            if not q:
                skipped += 1
                continue
            actual = "UP" if nxt["close"] > nxt["open"] else "DOWN"
            win = d == actual
            trade_pnl = sanal_pnl(q, win)
            bal = round(bal + trade_pnl, 2)
            pnl = round(pnl + trade_pnl, 4)
            fee_sum += float(q.get("pm_fee") or 0)
            rec = {
                "symbol": sym, "win": win, "pnl": trade_pnl,
                "t": nxt_t,
            }
            hist.append(rec)
            by_sym[sym]["n"] += 1
            by_sym[sym]["w"] += int(win)
            by_sym[sym]["pnl"] += trade_pnl
            mo = datetime.fromtimestamp(nxt_t / 1000, tz=timezone.utc).strftime("%Y-%m")
            months[mo] += trade_pnl
    trades = len(hist)
    wins = sum(1 for t in hist if t["win"])
    wr = round(100.0 * wins / trades, 1) if trades else None
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
        "win_rate_pct": wr,
        "skipped": skipped,
        "fees": round(fee_sum, 2),
        "by_symbol": by,
        "monthly_pnl": {k: round(v, 2) for k, v in sorted(months.items())},
    }


def _z_ok(key, sym, kslice, nxt, d) -> bool:
    if key != "a2_05_v2":
        return True
    z = entry_zscore(kslice)
    if z is None:
        return False
    lo, hi = A2_05_V2_Z
    return lo <= abs(float(z)) < hi


async def main() -> int:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365)
    fetch_start = start - timedelta(days=12)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    bars_by_sym = {}
    for sym in THREE:
        print(f"veri {sym} …", flush=True)
        bars_by_sym[sym] = await fetch_klines(sym, int(fetch_start.timestamp() * 1000), end_ms)
        print(f"  {len(bars_by_sym[sym])} bar", flush=True)
    bars_by_sym = _align(bars_by_sym)
    n = min(len(v) for v in bars_by_sym.values())
    print(f"hizalı {n} saat", flush=True)

    books: list[tuple[str, str]] = []
    dir_map: dict[str, dict[str, list[str | None]]] = {}

    def alloc() -> dict[str, list[str | None]]:
        return {s: [None] * n for s in THREE}

    # A1
    a1_skip = set(getattr(sig, "SKIP", set())) | A1_SKIP_LIVE
    for num, name in sig.ALGO_META:
        if num in a1_skip:
            continue
        key = f"a1_{num:02d}"
        books.append((key, f"A1#{num:02d} {name}"))
        dmap = alloc()
        for i in range(WARMUP, n - 1):
            for s in THREE:
                win = bars_by_sym[s][max(0, i - 199): i + 1]
                if num == 12:
                    eth = _to_kl(bars_by_sym["ETHUSDT"][max(0, i - 199): i + 1])
                    btc = _to_kl(bars_by_sym["BTCUSDT"][max(0, i - 199): i + 1])
                    try:
                        pair = sig.pairs_trading({"ETH": eth, "BTC": btc})
                    except Exception:
                        pair = {}
                    raw = pair.get("ETH" if s == "ETHUSDT" else "BTC") if s != "SOLUSDT" else None
                    dmap[s][i] = raw if raw in ("UP", "DOWN") else None
                elif num == 15:
                    kl1 = _to_kl(win)
                    kl4 = _to_kl(_resample_4h(bars_by_sym[s][max(0, i - 799): i + 1]))
                    try:
                        raw = sig.multi_tf(kl1, kl4) if len(kl4) >= 10 else None
                    except Exception:
                        raw = None
                    dmap[s][i] = raw if raw in ("UP", "DOWN") else None
                else:
                    dmap[s][i] = _fn_dir(A1_SIMPLE.get(num), win)
        dir_map[key] = dmap
        print(f"  sinyal {key}", flush=True)

    # A2
    for num, name, _cat, kind, fn in ALGO_V2_META:
        key = f"a2_{num:02d}"
        books.append((key, f"A2#{num:02d} {name}"))
        dmap = alloc()
        for i in range(WARMUP, n - 1):
            for s in THREE:
                win = bars_by_sym[s][max(0, i - 199): i + 1]
                if kind == "pairs":
                    eth = _to_kl(bars_by_sym["ETHUSDT"][max(0, i - 199): i + 1])
                    btc = _to_kl(bars_by_sym["BTCUSDT"][max(0, i - 199): i + 1])
                    try:
                        pair = sig.pairs_trading({"ETH": eth, "BTC": btc})
                    except Exception:
                        pair = {}
                    raw = pair.get("ETH" if s == "ETHUSDT" else "BTC") if s != "SOLUSDT" else None
                    dmap[s][i] = raw if raw in ("UP", "DOWN") else None
                else:
                    dmap[s][i] = _fn_dir(fn, win)
        dir_map[key] = dmap
        print(f"  sinyal {key}", flush=True)

    # Named OHLCV
    named = {
        "analiz1": ("A1 · RSI+MACD+EMA", THREE),
        "analiz2": ("A2 · A1 SOL only", ["SOLUSDT"]),
        "analiz6": ("6. Analiz", THREE),
        "analiz6_v2": ("6. Analiz V2", ["BTCUSDT", "ETHUSDT"]),
        "analiz6_v3": ("6. Analiz V3", THREE),
        "melez": ("MELEZ", THREE),
        "analiz15": ("15. Analiz", THREE),
        "a2_05_v2": ("A2#05 V2 · Z kapısı", THREE),
        "b1_02": ("B1#02", THREE),
        "b1_mum": ("B1#03 MUM", THREE),
    }
    mum_fn = None
    try:
        from b1_mum_signal import resolve_direction
        mum_fn = resolve_direction
    except Exception as e:
        print(f"b1_mum yok: {e}", flush=True)

    for key, (label, syms) in named.items():
        books.append((key, label))
        dmap = alloc()
        for i in range(WARMUP, n - 1):
            for s in THREE:
                if s not in syms:
                    continue
                win = bars_by_sym[s][max(0, i - 199): i + 1]
                d = None
                if key in ("analiz1", "analiz2"):
                    d = rsi_macd_ema(win)
                elif key == "analiz6":
                    fn = sig.macd_histogram_div if s != "ETHUSDT" else sig.rsi_divergence_strict
                    d = _fn_dir(fn, win)
                elif key == "analiz6_v2":
                    fn = sig.macd_histogram_div if s == "BTCUSDT" else sig.rsi_divergence_strict
                    d = _fn_dir(fn, win)
                elif key == "analiz6_v3":
                    kind, _ = A6V3_ENGINE.get(s, ("", ""))
                    if kind == "a6_macd":
                        d = _fn_dir(sig.macd_histogram_div, win)
                    elif kind == "a6_rsi":
                        d = _fn_dir(sig.rsi_divergence_strict, win)
                    elif kind == "a2":
                        d = rsi_macd_ema(win)
                elif key == "melez":
                    fn, _ = MELEZ_ENGINE.get(s, (None, ""))
                    d = _fn_dir(fn, win)
                elif key == "analiz15":
                    if s == "BTCUSDT":
                        d = direction_a6(win)
                    elif s == "ETHUSDT":
                        d = direction_a8(win, strict=True)
                    else:
                        d = rsi_macd_ema(win)
                elif key == "a2_05_v2":
                    d = _fn_dir(sig.mean_reversion, win)
                elif key == "b1_02":
                    if s == "BTCUSDT":
                        d = direction_a6(win)
                    elif s == "ETHUSDT":
                        d = _fn_dir(sig.rsi_divergence_strict, win)
                    else:
                        d = dir_map.get("a2_01", {}).get(s, [None] * n)[i]
                elif key == "b1_mum" and mum_fn:
                    try:
                        raw = mum_fn(s, win, poly_symbols_only=True)
                        d = raw if raw in ("UP", "DOWN") else None
                    except Exception:
                        d = None
                dmap[s][i] = d if d in ("UP", "DOWN") else None
        dir_map[key] = dmap
        print(f"  sinyal {key}", flush=True)

    # C101 / V2 — model vs mid / ask
    for key, label, edge, use_ask in (
        ("c101", "C1#01 mid 5p", C101_EDGE, False),
        ("c101_v2", "C1#01 V2 ask 3p", C101_V2_EDGE, True),
    ):
        books.append((key, label))
        dmap = alloc()
        for i in range(WARMUP, n - 1):
            for s in THREE:
                win = bars_by_sym[s][max(0, i - 199): i + 1]
                nxt = bars_by_sym[s][i + 1]
                p_up = _c101_p_up(win, nxt["open"], win[-1]["close"])
                if p_up is None:
                    continue
                if use_ask:
                    up_a, dn_a = estimate_asks(win, nxt)
                    ev = evaluate({"p_up": p_up}, up_a, dn_a, edge_min=edge)
                    if ev.get("tradable"):
                        dmap[s][i] = ev["direction"]
                else:
                    mid = 0.50
                    if abs(p_up - mid) >= edge:
                        dmap[s][i] = "UP" if p_up > mid else "DOWN"
        dir_map[key] = dmap
        print(f"  sinyal {key}", flush=True)

    # F1 OHLCV-only
    try:
        from f1_signal import decide, F1_META
        for num, name, _role in F1_META:
            if num in (1, 7):
                continue
            key = f"f1_{num:02d}"
            books.append((key, f"F1#{num:02d} {name}"))
            dmap = alloc()
            short = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}
            step = 4 if num == 1 else 1  # HMM ağır
            last = {s: None for s in THREE}
            for i in range(WARMUP, n - 1):
                for s in THREE:
                    if num == 1 and (i % step) != 0:
                        dmap[s][i] = last[s]
                        continue
                    kl = _to_kl(bars_by_sym[s][max(0, i - 199): i + 1])
                    try:
                        d, _why = decide(num, short[s], kl)
                    except Exception:
                        d = None
                    last[s] = d if d in ("UP", "DOWN") else None
                    dmap[s][i] = last[s]
            dir_map[key] = dmap
            print(f"  sinyal {key}", flush=True)
    except Exception as e:
        print(f"F1 atlandı: {e}", flush=True)

    # COMBO = A1 + C101 + A2#05 V2; çatışmada yok
    books.append(("combo", "COMBO"))
    dmap = alloc()
    for i in range(WARMUP, n - 1):
        for s in THREE:
            votes = [
                dir_map.get("analiz1", {}).get(s, [None] * n)[i],
                dir_map.get("c101", {}).get(s, [None] * n)[i],
                dir_map.get("a2_05_v2", {}).get(s, [None] * n)[i],
            ]
            active = [v for v in votes if v in ("UP", "DOWN")]
            if not active:
                continue
            if "UP" in active and "DOWN" in active:
                continue
            dmap[s][i] = active[0]
    dir_map["combo"] = dmap
    print("  sinyal combo", flush=True)

    books.append(("combo2", "COMBO2"))
    dmap = alloc()
    for i in range(WARMUP, n - 1):
        dmap["BTCUSDT"][i] = dir_map.get("c101", {}).get("BTCUSDT", [None] * n)[i]
        dmap["ETHUSDT"][i] = dir_map.get("combo", {}).get("ETHUSDT", [None] * n)[i]
        dmap["SOLUSDT"][i] = dir_map.get("combo", {}).get("SOLUSDT", [None] * n)[i]
    dir_map["combo2"] = dmap

    # Meta B1#01 / #04 / #05 — kaynak walk-forward WR
    source_b101 = ["analiz6", "analiz6_v2", "analiz6_v3", "analiz15"] + [
        f"a2_{n:02d}" for n, *_ in ALGO_V2_META
    ]
    source_b105 = [k for k, _ in books if k not in (
        "b1_01", "b1_02", "b1_04", "b1_05", "analiz2", "combo", "combo2", "c101", "c101_v2",
    ) and not k.startswith("f1_")]

    def _meta_dirs(sources: list[str], min_n: int, mode: str) -> dict[str, list[str | None]]:
        dmap = alloc()
        stats = {s: {k: {"n": 0, "w": 0} for k in sources} for s in THREE}
        for i in range(WARMUP, n - 1):
            nxt_t = bars_by_sym[THREE[0]][i + 1]["open_time"]
            if nxt_t < start_ms:
                # yine de kaynak sonuçlarını işle
                pass
            for s in THREE:
                actual = "UP" if bars_by_sym[s][i + 1]["close"] > bars_by_sym[s][i + 1]["open"] else "DOWN"
                votes = {}
                for k in sources:
                    d = dir_map.get(k, {}).get(s, [None] * n)[i]
                    if d in ("UP", "DOWN"):
                        votes[k] = d
                pick = None
                if mode == "best":
                    best_k, best_wr = None, -1.0
                    for k, row in stats[s].items():
                        if row["n"] < min_n or k not in votes:
                            continue
                        wr = row["w"] / row["n"]
                        if wr > best_wr:
                            best_wr, best_k = wr, k
                    if best_k:
                        pick = votes.get(best_k)
                else:  # b104 edge-weighted majority
                    up = down = 0.0
                    for k, d in votes.items():
                        row = stats[s][k]
                        if row["n"] < min_n:
                            continue
                        edge = max(0.0, row["w"] / row["n"] - 0.5)
                        if edge <= 0:
                            continue
                        if d == "UP":
                            up += edge
                        else:
                            down += edge
                    if up > down and up > 0:
                        pick = "UP"
                    elif down > up and down > 0:
                        pick = "DOWN"
                dmap[s][i] = pick
                for k, d in votes.items():
                    stats[s][k]["n"] += 1
                    stats[s][k]["w"] += int(d == actual)
        return dmap

    books.append(("b1_01", "B1#01"))
    dir_map["b1_01"] = _meta_dirs(source_b101, 5, "best")
    print("  sinyal b1_01", flush=True)
    books.append(("b1_05", "B1#05"))
    dir_map["b1_05"] = _meta_dirs(source_b105, 5, "best")
    print("  sinyal b1_05", flush=True)
    books.append(("b1_04", "B1#04"))
    dir_map["b1_04"] = _meta_dirs(source_b101, 5, "vote")
    print("  sinyal b1_04", flush=True)

    skipped_notes = [
        {"id": "x101", "label": "X1#01 13Analiz", "why": "13 katman + canlı ask; OHLCV ile yeniden kurulmaz"},
        {"id": "a1_20", "label": "A1#20 OI", "why": "canlı open interest"},
        {"id": "a1_21", "label": "A1#21 F&G", "why": "canlı sentiment"},
        {"id": "f1_01", "label": "F1#01 HMM", "why": "saatlik HMM 1Y'de pratik değil"},
        {"id": "f1_07", "label": "F1#07 Funding", "why": "canlı funding WS"},
        {"id": "a1_13", "label": "A1#13 Grid", "why": "yön yok"},
        {"id": "a1_14", "label": "A1#14 LSTM", "why": "model yok"},
    ]

    results = []
    for key, label in books:
        extra = _z_ok if key == "a2_05_v2" else None
        rec = simulate_book(key, label, dir_map[key], bars_by_sym, start_ms, extra)
        results.append(rec)
        print(f"  sim {key}  n={rec['trades']} WR={rec['win_rate_pct']} pnl={rec['total_pnl']:+.0f}", flush=True)

    results.sort(key=lambda r: (r["total_pnl"], r.get("win_rate_pct") or 0), reverse=True)
    payload = {
        "generated_at_tr": datetime.now(_TZ).isoformat(timespec="seconds"),
        "period": f"{start.date()} → {end.date()}",
        "days": 365,
        "initial_balance": INITIAL,
        "pm_model": "ask+fee · geçmiş CLOB yok",
        "amount_tiers": "$24/36/48 · COMBO $16/24/32 · COMBO2 $64",
        "symbols": THREE,
        "note": (
            "A1 / A2 predictor (analiz1, analiz2, A15 SOL, A6V3 SOL) = RSI+MACD+EMA oy, "
            "nötr flow. Canlı weekday predict() daha ağır. :05/:07 kopya yok (aynı sinyal). "
            "Sıra net Poly P&L (ücret düşülmüş)."
        ),
        "n_tested": len(results),
        "ranked": results,
        "skipped": skipped_notes,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nkaydedildi {OUT}", flush=True)
    print("\n#  P&L     WR     n   defter")
    for i, r in enumerate(results, 1):
        print(f"{i:2d}. {r['total_pnl']:+8.0f}  {str(r['win_rate_pct']):>5}  {r['trades']:5d}  {r['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

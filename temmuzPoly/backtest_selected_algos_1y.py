#!/usr/bin/env python3
"""Seçili algoritma-islemler defterleri — 1Y walk-forward backtest + Telegram.

  python3 temmuzPoly/backtest_selected_algos_1y.py --telegram
  python3 temmuzPoly/backtest_selected_algos_1y.py --resend
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import poly_predictor_analysis as pa
from algo_signals import (
    fetch_klines as _algo_fetch_klines,
    macd_histogram_div,
    mean_reversion,
    rsi_divergence_strict,
)
from algo_signals_v2 import ALGO_V2_META
from analiz15_signal import direction_a2, direction_a6, direction_a8
from analiz6_v4_signal import _SYMBOL_ENGINE as MELEZ_ENGINE
from analiz6_v3_signal import _SYMBOL_ENGINE as A6V3_ENGINE
from backtest_analiz2 import fetch_klines_history, _neutral_preloaded
from backtest_pm import fill_position_quote, estimate_asks
from backtest_common import (
    Trade,
    print_summary,
    run_walk_forward,
    to_algo21_klines,
)
from b1_04_signal import (
    _MIN_NET_EDGE,
    _MIN_TRADES as B104_MIN_TRADES,
    _SHRINK_K,
    _EDGE_WINDOW,
    book_label as b104_label,
    score_votes,
    voter_keys,
)
from b1_05_signal import _MIN_TRADES as B105_MIN_TRADES, source_keys as b105_source_keys
from c101_signal import EDGE_MIN as C101_EDGE_DEFAULT, evaluate, parkinson_sigma, _phi, _MIN_T_REMAIN
from poly_predictor_analysis import predict
from pm_trader_helpers import wr_tier_amount, PM_LIVE_TG_TOKEN, PM_LIVE_TG_CHAT, sanal_pnl

_TZ_TR = ZoneInfo("Europe/Istanbul")
THREE = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
A1_SYMS = ["BTCUSDT", "SOLUSDT"]
INITIAL_BALANCE = 1000.0
AMT_LOW, AMT_MID, AMT_HIGH = 24.0, 36.0, 48.0
C101_V2_EDGE = 0.03
A2_05_V2_Z_GATE = (1.0, 1.5)
OUT_FILE = os.path.join(_DIR, "backtest_selected_algos_1y.json")
CHART_FILE = "/tmp/backtest_selected_algos_1y.png"

_TR_MONTHS_LC = (
    "ocak", "şubat", "mart", "nisan", "mayıs", "haziran",
    "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık",
)

SELECTED = [
    ("a2_05", "A2#05"),
    ("melez", "MELEZ"),
    ("a2_05_v2", "A2#05 V2"),
    ("analiz6_v3", "A6V3"),
    ("b1_05", "B1#05"),
    ("analiz1", "A1"),
    ("b1_04", "B1#04"),
    ("c101_v2", "C1#01 V2"),
]

_A2_FN = {f"a2_{n:02d}": fn for n, _name, _cat, kind, fn in ALGO_V2_META if kind == "fn" and fn}


def _apply_pm(pos: dict, sym: str, direction: str, amount: float,
              kslice: list, next_bar: dict) -> bool:
    q = fill_position_quote(sym, direction, amount, kslice, next_bar)
    if not q:
        return False
    pos.update(q)
    return True


def _resolve_pnl(pos: dict, win: bool) -> float:
    return sanal_pnl(pos, win)
_A6_ALGOS = {
    "BTCUSDT": macd_histogram_div,
    "SOLUSDT": macd_histogram_div,
    "ETHUSDT": rsi_divergence_strict,
}
_A6V2_ALGOS = {
    "BTCUSDT": macd_histogram_div,
    "ETHUSDT": rsi_divergence_strict,
}


def _load_env() -> None:
    env_path = os.path.join(_DIR, "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def make_amount_fn():
    def amount_fn(history, sym: str) -> float:
        rows = [{"symbol": t.symbol, "win": t.win} for t in history]
        return wr_tier_amount(rows, sym, AMT_LOW, AMT_MID, AMT_HIGH)
    return amount_fn


def _shrunk_rate(wins: int, n: int, prior: float, k: float = _SHRINK_K) -> float:
    if n <= 0:
        return prior
    return (wins + k * prior) / (n + k)


async def _dir_a1(sym: str, kslice: list, open_ms: int) -> str | None:
    pa._slot_utc_ms = open_ms
    try:
        pred = await predict(sym, preloaded=_neutral_preloaded(kslice))
    finally:
        pa._slot_utc_ms = None
    d = getattr(pred, "predicted_dir", None) if pred else None
    return d if d in ("UP", "DOWN") else None


def _dir_fn(sym: str, kslice: list, fn) -> str | None:
    kl = to_algo21_klines(kslice)
    if len(kl) < 30:
        return None
    sig = fn(kl)
    return sig if sig in ("UP", "DOWN") else None


async def signal_for_book(key: str, sym: str, kslice: list, open_ms: int) -> str | None:
    if key == "analiz1":
        return await _dir_a1(sym, kslice, open_ms)
    if key == "a2_05" or key == "a2_05_v2":
        return _dir_fn(sym, kslice, mean_reversion)
    if key == "melez":
        fn, _ = MELEZ_ENGINE.get(sym, (None, ""))
        return _dir_fn(sym, kslice, fn) if fn else None
    if key == "analiz6_v3":
        kind, _ = A6V3_ENGINE.get(sym, ("", ""))
        if kind == "a6_macd":
            return _dir_fn(sym, kslice, macd_histogram_div)
        if kind == "a6_rsi":
            return _dir_fn(sym, kslice, rsi_divergence_strict)
        if kind == "a2":
            return await direction_a2(_klines_predict(kslice), sym, open_ms)
        return None
    if key == "analiz6":
        fn = _A6_ALGOS.get(sym, macd_histogram_div)
        return _dir_fn(sym, kslice, fn)
    if key == "analiz6_v2":
        fn = _A6V2_ALGOS.get(sym, macd_histogram_div)
        return _dir_fn(sym, kslice, fn)
    if key == "analiz15":
        if sym == "BTCUSDT":
            return direction_a6(kslice)
        if sym == "ETHUSDT":
            return direction_a8(kslice, strict=True)
        if sym == "SOLUSDT":
            return await direction_a2(_klines_predict(kslice), sym, open_ms)
        return None
    if key == "b1_mum":
        from b1_mum_signal import resolve_direction
        d = resolve_direction(sym, kslice, poly_symbols_only=True)
        return d if d in ("UP", "DOWN") else None
    if key in _A2_FN:
        return _dir_fn(sym, kslice, _A2_FN[key])
    if m := re.match(r"^a2_(\d+)$", key):
        n = int(m.group(1))
        for num, _name, _cat, kind, fn in ALGO_V2_META:
            if num == n and kind == "fn" and fn:
                return _dir_fn(sym, kslice, fn)
    return None


def _klines_predict(kslice: list[dict]) -> list[dict]:
    return [
        {
            "open_time": k.get("open_time", 0),
            "open": k["open"], "high": k["high"], "low": k["low"],
            "close": k["close"], "volume": k.get("volume", 0),
            "taker_buy": k.get("taker_buy", 0),
        }
        for k in kslice
    ]


def _c101_fair_from_klines(kslice: list[dict]) -> float | None:
    kl = [{"o": k["open"], "h": k["high"], "l": k["low"], "c": k["close"], "v": k.get("volume", 0)} for k in kslice]
    if len(kl) < 14:
        return None
    cur = kl[-1]
    ptb, spot = cur["o"], cur["c"]
    if ptb <= 0 or spot <= 0:
        return None
    t_remain = max(_MIN_T_REMAIN, 0.92)
    sig_s = parkinson_sigma(kl, 12)
    sig_l = parkinson_sigma(kl, 72)
    if sig_s is None and sig_l is None:
        return None
    if sig_s is None:
        sigma_base = sig_l
    elif sig_l is None:
        sigma_base = sig_s
    else:
        sigma_base = 0.6 * sig_s + 0.4 * sig_l
    if not sigma_base or sigma_base <= 0:
        return None
    denom = sigma_base * math.sqrt(t_remain)
    if denom <= 0:
        return None
    z = math.log(spot / ptb) / denom
    return max(0.01, min(0.99, _phi(z)))


def make_simple_signal(key: str):
    async def _sig(sym, kslice, open_ms, history, amount_fn, next_bar=None):
        d = await signal_for_book(key, sym, kslice, open_ms)
        if d not in ("UP", "DOWN"):
            return None
        return {
            "predicted_dir": d,
            "amount": None,
            "entry_price": kslice[-1]["close"],
            "extra": {"book": key},
        }
    return _sig


async def signal_c101_v2(sym, kslice, open_ms, history, amount_fn, next_bar=None):
    if next_bar is None:
        return None
    p_up = _c101_fair_from_klines(kslice)
    if p_up is None:
        return None
    up_ask, down_ask = estimate_asks(kslice, next_bar)
    ev = evaluate({"p_up": p_up}, up_ask, down_ask, edge_min=C101_V2_EDGE)
    if not ev.get("tradable"):
        return None
    bal = history[-1].balance_after if history else INITIAL_BALANCE
    from c101_signal import stake_for
    stake = stake_for(bal, ev["kelly_used"])
    if stake <= 0:
        return None
    return {
        "predicted_dir": ev["direction"],
        "amount": stake,
        "entry_price": kslice[-1]["close"],
        "extra": {"edge": ev["edge"], "p_up": p_up, "ask": ev["pm_price"]},
    }


async def run_meta_b1_05(start: datetime, balance: float, bars_by_sym: dict, amount_fn) -> dict:
    """Walk-forward: coin başına geçmişte en iyi kaynak defter."""
    keys = b105_source_keys()
    symbols = THREE
    return await _run_meta_selector(
        label="B1#05",
        book_id="b1_05",
        symbols=symbols,
        source_keys=keys,
        pick_fn=_pick_best_wr,
        min_trades=B105_MIN_TRADES,
        start=start,
        balance=balance,
        bars_by_sym=bars_by_sym,
        amount_fn=amount_fn,
    )


async def run_meta_b1_04(start: datetime, balance: float, bars_by_sym: dict, amount_fn) -> dict:
    keys = voter_keys()
    symbols = THREE
    return await _run_meta_selector(
        label="B1#04",
        book_id="b1_04",
        symbols=symbols,
        source_keys=keys,
        pick_fn=lambda sym, stats, votes: _pick_b104(sym, stats, votes),
        min_trades=B104_MIN_TRADES,
        start=start,
        balance=balance,
        bars_by_sym=bars_by_sym,
        amount_fn=amount_fn,
        consensus=True,
    )


def _pick_best_wr(sym: str, stats: dict, votes: dict) -> str | None:
    best_key, best_wr, best_n = None, -1.0, 0
    for key, row in stats.get(sym, {}).items():
        n, w = row["n"], row["w"]
        if n < B105_MIN_TRADES:
            continue
        wr = w / n
        if wr > best_wr or (wr == best_wr and n > best_n):
            best_wr, best_n, best_key = wr, n, key
    return best_key


def _edges_from_stats(stats: dict) -> dict:
    out = {}
    for key, row in stats.items():
        n, w = row["n"], row["w"]
        if n < B104_MIN_TRADES:
            continue
        breakeven = 0.50
        edge = _shrunk_rate(w, n, breakeven) - breakeven
        out[key] = {
            "label": b104_label(key),
            "edge": round(edge, 4),
            "weight": round(max(0.0, edge), 4),
        }
    return out


def _pick_b104(sym: str, stats: dict, votes: dict) -> str | None:
    edges = _edges_from_stats(stats.get(sym, {}))
    clusters = {k: k for k in votes}  # walk-forward: küme = defter
    vote_list = [{"key": k, "label": b104_label(k), "dir": d} for k, d in votes.items() if d in ("UP", "DOWN")]
    if not vote_list:
        return None
    score = score_votes(vote_list, edges, clusters)
    if not score.get("passes"):
        return None
    return score["direction"]


async def _run_meta_selector(
    *,
    label: str,
    book_id: str,
    symbols: list[str],
    source_keys: list[str],
    pick_fn,
    min_trades: int,
    start: datetime,
    balance: float,
    bars_by_sym: dict,
    amount_fn,
    consensus: bool = False,
) -> dict:
    test_start_ms = int(start.timestamp() * 1000)
    min_len = min(len(bars_by_sym[s]) for s in symbols)
    warmup = 80
    balance = balance
    total_pnl = 0.0
    history: list[Trade] = []
    open_pos: dict[str, dict] = {}
    skipped = 0
    # stats[sym][key] = {w, n}
    stats: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"w": 0, "n": 0}))
    # parallel source sim for walk-forward stats
    src_open: dict[tuple[str, str], dict] = {}

    for i in range(warmup, min_len - 1):
        if bars_by_sym[symbols[0]][i]["open_time"] < test_start_ms and not open_pos and not src_open:
            if bars_by_sym[symbols[0]][i + 1]["open_time"] < test_start_ms:
                continue

        # settle meta positions
        for sym in symbols:
            pos = open_pos.get(sym)
            if pos and pos["settle_idx"] == i:
                bar = bars_by_sym[sym][i]
                entry, exit_p = pos["entry_price"], bar["close"]
                pred, actual = pos["predicted_dir"], ("UP" if exit_p >= entry else "DOWN")
                win = pred == actual
                pnl = _resolve_pnl(pos, win)
                balance = round(balance + pnl, 2)
                total_pnl = round(total_pnl + pnl, 2)
                ts_open = datetime.fromtimestamp(pos["open_ms"] / 1000, tz=timezone.utc)
                ts_close = datetime.fromtimestamp(bar["open_time"] / 1000 + 3600, tz=timezone.utc)
                if ts_open.timestamp() >= start.timestamp():
                    history.append(Trade(
                        entry_time=ts_open.astimezone(_TZ_TR).isoformat(),
                        exit_time=ts_close.astimezone(_TZ_TR).isoformat(),
                        symbol=sym, predicted_dir=pred, actual_dir=actual, win=win,
                        entry_price=entry, exit_price=exit_p, amount=pos["amount"],
                        pnl=pnl, balance_after=balance, extra=pos.get("extra"),
                    ))
                del open_pos[sym]

        # settle source stats positions
        done_keys = []
        for (sk, ssym), pos in src_open.items():
            if pos["settle_idx"] != i:
                continue
            bar = bars_by_sym[ssym][i]
            entry, exit_p = pos["entry_price"], bar["close"]
            pred, actual = pos["dir"], ("UP" if exit_p >= entry else "DOWN")
            win = pred == actual
            st = stats[ssym][sk]
            st["n"] += 1
            if win:
                st["w"] += 1
            done_keys.append((sk, ssym))
        for k in done_keys:
            del src_open[k]

        if i + 1 >= min_len:
            continue
        if bars_by_sym[symbols[0]][i + 1]["open_time"] < test_start_ms:
            continue
        open_ms = bars_by_sym[symbols[0]][i + 1]["open_time"] + 5 * 60 * 1000

        votes_by_sym: dict[str, dict[str, str]] = defaultdict(dict)
        for sym in symbols:
            kslice = bars_by_sym[sym][max(0, i - 199): i + 1]
            if len(kslice) < warmup:
                continue
            for sk in source_keys:
                d = await signal_for_book(sk, sym, kslice, open_ms)
                if d in ("UP", "DOWN"):
                    votes_by_sym[sym][sk] = d
                if (sk, sym) not in src_open and d in ("UP", "DOWN"):
                    src_open[(sk, sym)] = {
                        "dir": d, "entry_price": kslice[-1]["close"],
                        "settle_idx": i + 1, "open_ms": open_ms,
                    }

            if sym in open_pos:
                continue
            if consensus:
                direction = pick_fn(sym, stats, votes_by_sym[sym])
            else:
                best = pick_fn(sym, stats, votes_by_sym[sym])
                direction = votes_by_sym[sym].get(best) if best else None
            if direction not in ("UP", "DOWN"):
                skipped += 1
                continue
            amount = amount_fn(history, sym)
            if not amount or amount <= 0:
                skipped += 1
                continue
            next_bar = bars_by_sym[sym][i + 1]
            pos = {
                "symbol": sym, "predicted_dir": direction,
                "entry_price": kslice[-1]["close"], "amount": amount,
                "settle_idx": i + 1, "open_ms": open_ms,
                "extra": {"book": book_id, "votes": len(votes_by_sym[sym])},
            }
            if not _apply_pm(pos, sym, direction, amount, kslice, next_bar):
                skipped += 1
                continue
            open_pos[sym] = pos

    return _result_dict(label, symbols, history, balance, total_pnl, skipped, INITIAL_BALANCE)


def _result_dict(label, symbols, history, balance, total_pnl, skipped, initial_balance):
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
    first = history[0].entry_time[:10] if history else "—"
    last = history[-1].entry_time[:10] if history else "—"
    return {
        "label": label,
        "symbols": symbols,
        "period": f"{first} → {last}",
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate_pct": round(wins / total * 100, 1) if total else 0.0,
        "max_drawdown_pct": 0.0,
        "skipped_signals": skipped,
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
    }


async def run_book(book_id: str, label: str, start: datetime, balance: float, bars_cache: dict) -> dict:
    amount_fn = make_amount_fn()
    if book_id == "b1_05":
        return await run_meta_b1_05(start, balance, bars_cache, amount_fn)
    if book_id == "b1_04":
        return await run_meta_b1_04(start, balance, bars_cache, amount_fn)
    syms = A1_SYMS if book_id == "analiz1" else THREE
    sig = signal_c101_v2 if book_id == "c101_v2" else make_simple_signal(book_id)
    r = await run_walk_forward(
        label=label,
        symbols=syms,
        signal_fn=sig,
        start_date=start,
        initial_balance=balance,
        min_bars=80,
        amount_fn=amount_fn if book_id != "c101_v2" else None,
        apply_pm_fn=_apply_pm,
        resolve_pnl_fn=_resolve_pnl,
        z_gate=A2_05_V2_Z_GATE if book_id == "a2_05_v2" else None,
    )
    del r["trade_list"]
    return r


def _month_name(ym: str, dup: set[str]) -> str:
    y, m = ym.split("-")
    name = _TR_MONTHS_LC[int(m) - 1]
    if name in dup:
        name = f"{name} '{y[2:]}"
    return name


def build_telegram_message(results: list[dict], period: str) -> str:
    lines = [
        "📊 <b>1Y Backtest · Algoritma İşlemler</b>",
        period,
        f"💰 Giriş <b>${INITIAL_BALANCE:.0f}</b> · işlem ${AMT_LOW:.0f}/${AMT_MID:.0f}/${AMT_HIGH:.0f} (WR kademe)",
        "<i>Model ask (PTB+vol) · PM taker ücreti · tick/min-adet · walk-forward</i>",
        "",
    ]
    for r in results:
        monthly = r.get("monthly_pnl") or {}
        yms = sorted(monthly.keys())
        names = [_TR_MONTHS_LC[int(ym.split("-")[1]) - 1] for ym in yms]
        dup = {n for n in names if names.count(n) > 1}
        pnl = r.get("total_pnl", 0)
        fb = r.get("final_balance", 0)
        lines.append(f"<b>{r['label']}</b>  ·  {r.get('trades', 0)} işlem  WR {r.get('win_rate_pct', 0)}%")
        month_parts = []
        for ym in yms:
            pnl_m = int(round(float(monthly[ym])))
            sign = "+" if pnl_m >= 0 else ""
            star = "★" if pnl_m > 0 else ""
            month_parts.append(f"{_month_name(ym, dup)} {sign}{pnl_m}{star}")
        lines.append("  " + " · ".join(month_parts) if month_parts else "  (işlem yok)")
        sign_y = "+" if pnl >= 0 else ""
        lines.append(f"  → Yıl sonu <b>${fb:,.0f}</b> ({sign_y}${int(round(pnl)):,})")
        lines.append("")
    lines.append("<i>A2#05 V2: giriş &lt;0.40 ask atlanır · geçmiş CLOB yok → model ask</i>")
    return "\n".join(lines).strip()


def tg_send_photo(path: str, caption: str = "", *, chat_id: str | None = None, token: str | None = None) -> None:
    boundary = "----BacktestSel"
    cid = chat_id or PM_LIVE_TG_CHAT
    tok = token or PM_LIVE_TG_TOKEN
    with open(path, "rb") as f:
        img = f.read()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n"
        f"{cid}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n"
        f"{caption}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + img + f"\r\n--{boundary}--\r\n".encode()
    url = f"https://api.telegram.org/bot{tok}/sendPhoto"
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    if not data.get("ok"):
        raise RuntimeError(f"Telegram foto: {data}")


def render_chart(results: list[dict], period: str, out_path: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    n = len(results)
    cols = min(4, n)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.2 * rows), facecolor="#0a0e17")
    if n == 1:
        axes = np.array([[axes]])
    elif rows == 1:
        axes = axes.reshape(1, -1)
    fig.suptitle(f"1Y Backtest — Seçili Defterler\n{period}", color="#e8edf5", fontsize=12, fontweight="bold")

    all_yms = sorted({ym for r in results for ym in (r.get("monthly_pnl") or {})})
    for idx, r in enumerate(results):
        ax = axes[idx // cols][idx % cols]
        ax.set_facecolor("#111827")
        monthly = r.get("monthly_pnl") or {}
        yms = [ym for ym in all_yms if ym in monthly]
        vals = [monthly[ym] for ym in yms]
        colors = ["#22c55e" if v >= 0 else "#ef4444" for v in vals]
        ax.bar(range(len(vals)), vals, color=colors, width=0.7)
        ax.axhline(0, color="#374151", lw=0.8)
        ax.set_title(f"{r['label']}\n${r['final_balance']:.0f} ({r['total_pnl']:+.0f})", color="#93c5fd", fontsize=9)
        ax.tick_params(axis="both", labelsize=6, colors="#6b7280")
        if vals:
            ax.set_xticks(range(len(vals)))
            ax.set_xticklabels([m.split("-")[1] for m in yms], fontsize=6, rotation=45)
    for idx in range(n, rows * cols):
        axes[idx // cols][idx % cols].axis("off")
    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="#0a0e17")
    plt.close()
    return out_path


async def _send_telegram(results: list[dict], period: str) -> None:
    msg = build_telegram_message(results, period)
    print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or PM_LIVE_TG_TOKEN
    chat = (
        os.getenv("TELEGRAM_CHAT")
        or os.getenv("TELEGRAM_CHAT_ID")
        or os.getenv("TELEGRAM_ANALIZ1_CHAT_ID")
        or PM_LIVE_TG_CHAT
    )
    if not token or not chat:
        raise RuntimeError("Telegram token/chat bulunamadı (.env)")

    chunks: list[str] = []
    if len(msg) <= 4000:
        chunks = [msg]
    else:
        cur = ""
        for line in msg.split("\n"):
            if len(cur) + len(line) + 1 > 3900:
                chunks.append(cur)
                cur = line
            else:
                cur = cur + "\n" + line if cur else line
        if cur:
            chunks.append(cur)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for i, chunk in enumerate(chunks):
        body = json.dumps({
            "chat_id": chat,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if not data.get("ok"):
            raise RuntimeError(f"Telegram hata: {data}")
        print(f"[TG] Parça {i + 1}/{len(chunks)} gönderildi")

    chart = render_chart(results, period, CHART_FILE)
    tg_send_photo(chart, caption="1Y Backtest · seçili 8 defter · ★ kârlı ay", chat_id=chat, token=token)
    print("[TG] Tamamlandı")


async def main() -> None:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--balance", type=float, default=INITIAL_BALANCE)
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--resend", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    if args.resend:
        if not os.path.exists(OUT_FILE):
            print(f"Dosya yok: {OUT_FILE}")
            return
        payload = json.load(open(OUT_FILE, encoding="utf-8"))
        await _send_telegram(payload["algos"], payload.get("period", ""))
        return

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    period = f"{start.astimezone(_TZ_TR).strftime('%d.%m.%Y')} → {end.astimezone(_TZ_TR).strftime('%d.%m.%Y')}"

    fetch_start = start - timedelta(days=10)
    end_ms = int(end.timestamp() * 1000)
    fetch_ms = int(fetch_start.timestamp() * 1000)
    bars_cache: dict[str, list] = {}
    for sym in THREE:
        print(f"Veri: {sym} 1h ({args.days}g)...")
        bars_cache[sym] = await fetch_klines_history(sym, "1h", fetch_ms, end_ms)
        print(f"  {len(bars_cache[sym])} bar")

    results = []
    for book_id, label in SELECTED:
        print(f"\n>>> {label} ({book_id})...")
        r = await run_book(book_id, label, start, args.balance, bars_cache)
        r["id"] = book_id
        print_summary({**r, "trade_list": [], "max_drawdown_pct": r.get("max_drawdown_pct", 0)})
        results.append(r)

    payload = {
        "generated_at_tr": datetime.now(_TZ_TR).isoformat(),
        "period": period,
        "days": args.days,
        "initial_balance": args.balance,
        "amount_tiers": {"low": AMT_LOW, "mid": AMT_MID, "high": AMT_HIGH},
        "pm_model": "ask+fee",
        "algos": results,
    }
    if not args.no_save:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\nKaydedildi: {OUT_FILE}")

    if args.telegram:
        await _send_telegram(results, period)


if __name__ == "__main__":
    asyncio.run(main())

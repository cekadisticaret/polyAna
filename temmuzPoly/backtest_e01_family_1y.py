#!/usr/bin/env python3
"""A1 · C1#01 · A2#05 · COMBO — 1Y walk-forward + aylık P&L.

Kasa $1000 · kademe $24/$36/$48 WR (COMBO: 1/2/3 oy = aynı kademe).
  A1      BTC+SOL · predict() nötr flow
  C1#01   BTC/ETH/SOL · kenar 5 puan vs 0,50 mid
  A2#05   BTC/ETH/SOL · mean_reversion · bilet ≥ 0,40 (z kapısı yok)
  COMBO   aynı slottaki A1+C101+A2#05 oyları · çatışmada yok

Dolum: model ask + PM taker ücreti (geçmiş CLOB yok).
C101 kararı 0,50 mid'e karşı — tarihi Gamma mid yok; :05 spot 5m kapanış.

  python3 temmuzPoly/backtest_e01_family_1y.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
sys.path.insert(0, _DIR)

import poly_predictor_analysis as pa
from algo_signals import mean_reversion
from backtest_analiz2 import _neutral_preloaded
from backtest_common import Trade, print_summary, to_algo21_klines
from backtest_pm import fill_position_quote
from c101_signal import (
    EDGE_MIN,
    _MIN_T_REMAIN,
    _phi,
    evaluate,
    parkinson_sigma,
)
from e01_signal import STAKE_BY_VOTES
from poly_a2_algo_trader_core import entry_zscore
from poly_predictor_analysis import predict
from pm_trader_helpers import wr_tier_amount, sanal_pnl

_TZ_TR = ZoneInfo("Europe/Istanbul")
THREE = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
A1_SYMS = ["BTCUSDT", "SOLUSDT"]
A205_MIN_ASK = 0.40
OUT_FILE = os.path.join(_DIR, "backtest_e01_family_1y.json")
CHART_FILE = "/tmp/backtest_e01_family_1y.png"
_TR_MONTHS = (
    "ocak", "şubat", "mart", "nisan", "mayıs", "haziran",
    "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık",
)
_KLINE_HOSTS = (
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
)


def _load_env() -> None:
    env_path = os.path.join(_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def _wr_amount(history: list[Trade], sym: str) -> float:
    rows = [{"symbol": t.symbol, "win": t.win} for t in history]
    return wr_tier_amount(rows, sym, 24.0, 36.0, 48.0)


async def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
    """Spot kline — fapi'ye dokunmaz (IP ban)."""
    import aiohttp

    out: list[dict] = []
    cur = start_ms
    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while cur < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": cur,
                "endTime": end_ms,
                "limit": 1000,
            }
            data = None
            last_err = None
            for url in _KLINE_HOSTS:
                try:
                    async with session.get(url, params=params) as r:
                        raw = await r.json()
                    if isinstance(raw, list) and raw:
                        data = raw
                        break
                    last_err = raw
                except Exception as e:
                    last_err = e
            if not data:
                print(f"  [kline] {symbol} {interval} durdu @ {cur}: {last_err}")
                break
            for k in data:
                out.append({
                    "open_time": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
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


def _c101_p_up(kslice: list[dict], ptb: float, spot: float) -> float | None:
    kl = [{"o": k["open"], "h": k["high"], "l": k["low"], "c": k["close"]} for k in kslice]
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
    t_remain = max(_MIN_T_REMAIN, 0.92)
    z = math.log(spot / ptb) / (sigma * math.sqrt(t_remain))
    return max(0.01, min(0.99, _phi(z)))


def _dir_a205(kslice: list[dict]) -> tuple[str | None, float | None]:
    kl = to_algo21_klines(kslice)
    if len(kl) < 30:
        return None, None
    sig = mean_reversion(kl)
    z = entry_zscore(kslice)
    if sig not in ("UP", "DOWN"):
        return None, z
    return sig, z


class BookSim:
    def __init__(self, book_id: str, label: str, symbols: list[str], init: float):
        self.book_id = book_id
        self.label = label
        self.symbols = symbols
        self.init = init
        self.balance = init
        self.total_pnl = 0.0
        self.history: list[Trade] = []
        self.open: dict[str, dict] = {}
        self.skipped = 0
        self.skip_reasons: dict[str, int] = defaultdict(int)
        self.vote_hist: dict[int, int] = defaultdict(int)

    def skip(self, reason: str) -> None:
        self.skipped += 1
        self.skip_reasons[reason] += 1

    def settle(self, i: int, bars_by_sym: dict, start: datetime) -> None:
        for sym in list(self.open):
            pos = self.open[sym]
            if pos["settle_idx"] != i:
                continue
            bar = bars_by_sym[sym][i]
            entry, exit_p = pos["entry_price"], bar["close"]
            pred = pos["predicted_dir"]
            actual = "UP" if exit_p >= entry else "DOWN"
            win = pred == actual
            pnl = sanal_pnl(pos, win)
            self.balance = round(self.balance + pnl, 2)
            self.total_pnl = round(self.total_pnl + pnl, 2)
            ts_open = datetime.fromtimestamp(pos["open_ms"] / 1000, tz=timezone.utc)
            ts_close = datetime.fromtimestamp(bar["open_time"] / 1000 + 3600, tz=timezone.utc)
            if ts_open.timestamp() >= start.timestamp():
                self.history.append(Trade(
                    entry_time=ts_open.astimezone(_TZ_TR).isoformat(),
                    exit_time=ts_close.astimezone(_TZ_TR).isoformat(),
                    symbol=sym, predicted_dir=pred, actual_dir=actual, win=win,
                    entry_price=entry, exit_price=exit_p, amount=pos["amount"],
                    pnl=pnl, balance_after=self.balance, extra=pos.get("extra"),
                ))
            del self.open[sym]

    def try_open(self, sym: str, direction: str, amount: float, kslice: list,
                 next_bar: dict, open_ms: int, settle_idx: int, extra: dict,
                 min_ask: float | None = None) -> bool:
        if sym in self.open:
            self.skip("zaten_acik")
            return False
        if not amount or amount <= 0:
            self.skip("kademe_yok")
            return False
        pos = {
            "symbol": sym, "predicted_dir": direction,
            "entry_price": kslice[-1]["close"], "amount": amount,
            "settle_idx": settle_idx, "open_ms": open_ms, "extra": extra,
        }
        q = fill_position_quote(sym, direction, amount, kslice, next_bar)
        if not q:
            self.skip("dolum_yok")
            return False
        pos.update(q)
        ep = float(pos.get("pm_entry_price") or 0)
        if min_ask is not None and ep < min_ask:
            self.skip("ask_dusuk")
            return False
        self.open[sym] = pos
        return True

    def to_result(self) -> dict:
        wins = sum(1 for t in self.history if t.win)
        total = len(self.history)
        monthly: dict[str, float] = {}
        monthly_n: dict[str, int] = {}
        monthly_w: dict[str, int] = {}
        sym_stats: dict[str, dict] = {}
        peak, max_dd = self.init, 0.0
        for t in self.history:
            mk = t.entry_time[:7]
            monthly[mk] = round(monthly.get(mk, 0) + t.pnl, 2)
            monthly_n[mk] = monthly_n.get(mk, 0) + 1
            monthly_w[mk] = monthly_w.get(mk, 0) + (1 if t.win else 0)
            s = sym_stats.setdefault(t.symbol, {"w": 0, "n": 0, "pnl": 0.0})
            s["n"] += 1
            s["pnl"] = round(s["pnl"] + t.pnl, 2)
            if t.win:
                s["w"] += 1
            peak = max(peak, t.balance_after)
            if peak:
                max_dd = max(max_dd, (peak - t.balance_after) / peak * 100)
        first = self.history[0].entry_time[:10] if self.history else "—"
        last = self.history[-1].entry_time[:10] if self.history else "—"
        best_m = max(monthly, key=monthly.get) if monthly else None
        worst_m = min(monthly, key=monthly.get) if monthly else None
        return {
            "id": self.book_id,
            "label": self.label,
            "symbols": self.symbols,
            "period": f"{first} → {last}",
            "initial_balance": self.init,
            "final_balance": round(self.balance, 2),
            "total_pnl": round(self.total_pnl, 2),
            "trades": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate_pct": round(wins / total * 100, 1) if total else 0.0,
            "max_drawdown_pct": round(max_dd, 1),
            "skipped_signals": self.skipped,
            "skip_reasons": dict(self.skip_reasons),
            "vote_hist": {str(k): v for k, v in sorted(self.vote_hist.items())},
            "monthly_pnl": monthly,
            "monthly_trades": monthly_n,
            "monthly_wins": monthly_w,
            "best_month": {"ym": best_m, "pnl": monthly.get(best_m)} if best_m else None,
            "worst_month": {"ym": worst_m, "pnl": monthly.get(worst_m)} if worst_m else None,
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


async def run_family(start: datetime, bars: dict, spot5: dict) -> list[BookSim]:
    a1 = BookSim("analiz1", "A1", A1_SYMS, 1000.0)
    c101 = BookSim("c101", "C1#01", THREE, 1000.0)
    a205 = BookSim("a2_05", "A2#05", THREE, 1000.0)
    e01 = BookSim("combo", "COMBO", THREE, 1000.0)
    books = [a1, c101, a205, e01]

    # ortak zaman — BTC ekseni
    btc = bars["BTCUSDT"]
    idx = {sym: {b["open_time"]: j for j, b in enumerate(bars[sym])} for sym in THREE}
    test_ms = int(start.timestamp() * 1000)
    warmup = 80
    n = len(btc)

    for i in range(warmup, n - 1):
        hour_ms = btc[i + 1]["open_time"]
        if hour_ms < test_ms and not any(b.open for b in books):
            continue

        for b in books:
            b.settle(i, bars, start)

        if hour_ms < test_ms:
            continue

        open_ms = hour_ms + 5 * 60 * 1000
        votes: dict[str, dict[str, str | None]] = {
            "analiz1": {}, "c101": {}, "a2_05": {},
        }

        for sym in THREE:
            j = idx[sym].get(btc[i]["open_time"])
            jn = idx[sym].get(hour_ms)
            if j is None or jn is None or jn + 0 >= len(bars[sym]):
                continue
            kslice = bars[sym][max(0, j - 199): j + 1]
            next_bar = bars[sym][jn]
            if len(kslice) < warmup:
                continue

            # A1
            d_a1 = None
            if sym in A1_SYMS:
                pa._slot_utc_ms = open_ms
                try:
                    pred = await predict(sym, preloaded=_neutral_preloaded(kslice))
                finally:
                    pa._slot_utc_ms = None
                d_a1 = getattr(pred, "predicted_dir", None) if pred else None
                if d_a1 in ("UP", "DOWN"):
                    votes["analiz1"][sym] = d_a1
                    a1.try_open(
                        sym, d_a1, _wr_amount(a1.history, sym),
                        kslice, next_bar, open_ms, i + 1, {"book": "analiz1"},
                    )
                else:
                    a1.skip("sinyal_yok")

            # C101 — :05 spot (5m) vs saat açılışı, karar 0,50 mid
            d_c = None
            ptb = float(next_bar["open"])
            spot = float(spot5.get(sym, {}).get(hour_ms) or 0) or ptb
            p_up = _c101_p_up(kslice, ptb, spot)
            if p_up is None:
                c101.skip("model_yok")
            else:
                ev = evaluate({"p_up": p_up}, 0.50, 0.50, edge_min=EDGE_MIN)
                if ev.get("tradable"):
                    d_c = ev["direction"]
                    votes["c101"][sym] = d_c
                    stake = _wr_amount(c101.history, sym)
                    c101.try_open(
                        sym, d_c, stake, kslice, next_bar, open_ms, i + 1,
                        {"book": "c101", "edge": ev["edge"], "p_up": p_up},
                    )
                else:
                    c101.skip(ev.get("skip_reason") or "kenar_yok")

            # A2#05 — mean reversion, bilet tabanı 0,40 (z kapısı yok)
            d_a205, z = _dir_a205(kslice)
            if d_a205:
                votes["a2_05"][sym] = d_a205
                a205.try_open(
                    sym, d_a205, _wr_amount(a205.history, sym),
                    kslice, next_bar, open_ms, i + 1,
                    {"book": "a2_05", "z": None if z is None else round(z, 3)},
                    min_ask=A205_MIN_ASK,
                )
            else:
                a205.skip("sinyal_yok")

            # COMBO oy — A1 + C101 + A2#05
            ballots = []
            for key, lab in (("analiz1", "A1"), ("c101", "C1#01"), ("a2_05", "A2#05")):
                d = votes[key].get(sym)
                if d in ("UP", "DOWN"):
                    ballots.append((lab, d))
            ups = [lab for lab, d in ballots if d == "UP"]
            downs = [lab for lab, d in ballots if d == "DOWN"]
            if ups and downs:
                e01.skip("catisma")
                continue
            if not ballots:
                e01.skip("hepsi_sessiz")
                continue
            direction = "UP" if ups else "DOWN"
            n_votes = len(ballots)
            stake = float(STAKE_BY_VOTES.get(n_votes) or 0)
            e01.vote_hist[n_votes] += 1
            e01.try_open(
                sym, direction, stake, kslice, next_bar, open_ms, i + 1,
                {"book": "e01", "votes": n_votes, "detail": ballots},
            )

        if i % 500 == 0:
            print(f"  slot {i}/{n}  A1={len(a1.history)} C101={len(c101.history)} "
                  f"A205={len(a205.history)} COMBO={len(e01.history)}")

    return books


def _month_name(ym: str, dup: set[str]) -> str:
    y, m = ym.split("-")
    name = _TR_MONTHS[int(m) - 1]
    return f"{name} '{y[2:]}" if name in dup else name


def build_telegram(results: list[dict], period: str) -> str:
    lines = [
        "<b>1Y Backtest · A1 · C101 · A2#05 · COMBO</b>",
        period,
        "Kasa $1000 · kademe $24/$36/$48",
        "<i>Walk-forward · model ask + PM ücreti · C101 karar 0,50 mid · A2#05 bilet ≥0,40</i>",
        "",
    ]
    for r in results:
        monthly = r.get("monthly_pnl") or {}
        yms = sorted(monthly)
        names = [_TR_MONTHS[int(ym.split("-")[1]) - 1] for ym in yms]
        dup = {n for n in names if names.count(n) > 1}
        pnl = r.get("total_pnl", 0)
        wr = r.get("win_rate_pct", 0)
        lines.append(
            f"<b>{r['label']}</b>  {r.get('trades', 0)} işlem  WR {wr}%  "
            f"DD %{r.get('max_drawdown_pct', 0)}"
        )
        parts = []
        for ym in yms:
            v = int(round(float(monthly[ym])))
            n = int((r.get("monthly_trades") or {}).get(ym) or 0)
            sign = "+" if v >= 0 else ""
            parts.append(f"{_month_name(ym, dup)} {sign}{v}$ ({n})")
        lines.append("  " + " · ".join(parts) if parts else "  (işlem yok)")
        bys = r.get("by_symbol") or {}
        if bys:
            bits = []
            for sym, st in bys.items():
                bits.append(
                    f"{sym.replace('USDT', '')} {st['pnl']:+.0f}$ "
                    f"WR {st['win_rate_pct']}% n={st['trades']}"
                )
            lines.append("  " + " · ".join(bits))
        if r.get("vote_hist"):
            vh = r["vote_hist"]
            lines.append(
                "  oy: " + " · ".join(f"{k}oy×{vh[k]}" for k in sorted(vh, key=int))
            )
        sign = "+" if pnl >= 0 else ""
        lines.append(
            f"  → ${r['initial_balance']:.0f} → <b>${r['final_balance']:,.0f}</b> "
            f"({sign}${int(round(pnl)):,})"
        )
        lines.append("")
    lines.append(
        "<i>C101: geçmiş PM kotasyonu yok — karar 0,50 mid; dolum model ask. "
        "OHLCV-dışı tilt/derinlik yok. COMBO oyları bu üç simülasyondan "
        "(canlı COMBO A2#05 V2 kullanır; bu koşu A2#05).</i>"
    )
    return "\n".join(lines).strip()


def render_chart(results: list[dict], period: str, out_path: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), facecolor="#0a0e17")
    fig.suptitle(f"1Y Backtest — A1 · C101 · A2#05 · COMBO\n{period} · $1000 · $24/36/48", color="#e8edf5", fontsize=13, fontweight="bold")
    all_yms = sorted({ym for r in results for ym in (r.get("monthly_pnl") or {})})
    for idx, r in enumerate(results):
        ax = axes[idx // 2][idx % 2]
        ax.set_facecolor("#111827")
        monthly = r.get("monthly_pnl") or {}
        vals = [monthly.get(ym, 0) for ym in all_yms]
        colors = ["#22c55e" if v >= 0 else "#ef4444" for v in vals]
        ax.bar(range(len(vals)), vals, color=colors, width=0.72)
        ax.axhline(0, color="#374151", lw=0.8)
        ax.set_title(
            f"{r['label']}   ${r['final_balance']:.0f} ({r['total_pnl']:+.0f})  WR {r['win_rate_pct']}%",
            color="#93c5fd", fontsize=10,
        )
        ax.tick_params(axis="both", labelsize=7, colors="#6b7280")
        ax.set_xticks(range(len(all_yms)))
        ax.set_xticklabels([ym[5:] for ym in all_yms], fontsize=7)
        ax.set_ylabel("P&L $", color="#6b7280", fontsize=8)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight", facecolor="#0a0e17")
    plt.close()
    return out_path


def tg_send_text(token: str, chat: str, msg: str) -> None:
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
            "chat_id": chat, "text": chunk,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if not data.get("ok"):
            raise RuntimeError(f"Telegram: {data}")
        print(f"[TG] metin {i + 1}/{len(chunks)}")


def tg_send_photo(token: str, chat: str, path: str, caption: str) -> None:
    boundary = "----E01FamilyBT"
    with open(path, "rb") as f:
        img = f.read()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + img + f"\r\n--{boundary}--\r\n".encode()
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    if not data.get("ok"):
        raise RuntimeError(f"Telegram foto: {data}")


async def main() -> None:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--resend", action="store_true")
    args = ap.parse_args()

    if args.resend:
        payload = json.load(open(OUT_FILE, encoding="utf-8"))
        token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat:
            raise RuntimeError("Telegram token/chat yok")
        msg = build_telegram(payload["algos"], payload.get("period", ""))
        tg_send_text(token, chat, msg)
        if os.path.exists(CHART_FILE):
            tg_send_photo(token, chat, CHART_FILE, "1Y Backtest · E01 ailesi")
        return

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    period = (
        f"{start.astimezone(_TZ_TR).strftime('%d.%m.%Y')} → "
        f"{end.astimezone(_TZ_TR).strftime('%d.%m.%Y')}"
    )
    fetch_start = start - timedelta(days=12)
    end_ms = int(end.timestamp() * 1000)
    fetch_ms = int(fetch_start.timestamp() * 1000)

    bars: dict[str, list] = {}
    for sym in THREE:
        print(f"1h {sym}...")
        bars[sym] = await fetch_klines(sym, "1h", fetch_ms, end_ms)
        print(f"  {len(bars[sym])} bar")
        if len(bars[sym]) < 100:
            raise RuntimeError(f"yetersiz 1h {sym}")

    # ortak saat damgası
    common = set(b["open_time"] for b in bars["BTCUSDT"])
    for sym in THREE[1:]:
        common &= set(b["open_time"] for b in bars[sym])
    for sym in THREE:
        bars[sym] = [b for b in bars[sym] if b["open_time"] in common]
    print(f"ortak 1h: {len(bars['BTCUSDT'])}")

    print("5m :05 spot...")
    spot5: dict[str, dict[int, float]] = {s: {} for s in THREE}
    for sym in THREE:
        m5 = await fetch_klines(sym, "5m", fetch_ms, end_ms)
        for b in m5:
            hour = (b["open_time"] // 3_600_000) * 3_600_000
            if b["open_time"] == hour:
                spot5[sym][hour] = b["close"]
        print(f"  {sym} :05 map {len(spot5[sym])}")

    print("walk-forward...")
    books = await run_family(start, bars, spot5)
    results = []
    for b in books:
        r = b.to_result()
        print_summary({**r, "trade_list": []})
        results.append(r)

    payload = {
        "generated_at_tr": datetime.now(_TZ_TR).isoformat(),
        "period": period,
        "days": args.days,
        "notes": {
            "c101": "karar 0,50 mid (geçmiş PM yok); :05 spot=ilk 5m kapanış; tilt/derinlik yok; dolum model ask+fee; $24/36/48",
            "a2_05": "mean_reversion + ask≥0,40 (z kapısı yok); $24/36/48",
            "analiz1": "predict() nötr flow; BTC+SOL; $24/36/48",
            "combo": "aynı slottaki A1+C101+A2#05 oyları; çatışma yok; 1/2/3 oy = $24/36/48",
        },
        "algos": results,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nKaydedildi: {OUT_FILE}")

    render_chart(results, period, CHART_FILE)
    print(f"Grafik: {CHART_FILE}")

    if args.telegram:
        token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat:
            raise RuntimeError("Telegram token/chat yok")
        msg = build_telegram(results, period)
        print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
        tg_send_text(token, chat, msg)
        tg_send_photo(token, chat, CHART_FILE, "1Y Backtest · C101 · A2#05 V2 · E01 · A1")
        print("[TG] gönderildi")


if __name__ == "__main__":
    asyncio.run(main())

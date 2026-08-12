#!/usr/bin/env python3
"""A2#05 · A6V3 · MELEZ — 1 yıllık walk-forward backtest (BTC/ETH/SOL).

PM sim: $1000 başlangıç · sembol WR kademesi $36 / $48 / $72 · token 0.50

  python3 temmuzPoly/backtest_a2_a6_melez_1y.py --telegram
  python3 temmuzPoly/backtest_a2_a6_melez_1y.py --resend
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from algo_signals import macd_histogram_div, mean_reversion, rsi_divergence_strict
from analiz15_signal import direction_a2
from backtest_common import run_walk_forward, print_summary, to_algo21_klines
from pm_trader_helpers import wr_tier_amount, PM_LIVE_TG_TOKEN, PM_LIVE_TG_CHAT

_TZ_TR = ZoneInfo("Europe/Istanbul")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INITIAL_BALANCE = 1000.0
AMOUNT_LOW = 36.0
AMOUNT_MID = 48.0
AMOUNT_HIGH = 72.0
OUT_FILE = os.path.join(_DIR, "backtest_a2_a6_melez_1y.json")
CHART_FILE = "/tmp/backtest_a2_a6_melez_1y.png"

_TR_MONTHS = (
    "Oca", "Şub", "Mar", "Nis", "May", "Haz",
    "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
)
_TR_MONTHS_LC = (
    "ocak", "şubat", "mart", "nisan", "mayıs", "haziran",
    "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık",
)

ALGO_META = [
    ("a2_05", "A2#05", "Mean Reversion Z-Score"),
    ("a6v3", "A6V3", "BTC MACD · ETH RSI · SOL A2"),
    ("melez", "MELEZ", "BTC MACD · ETH/SOL Mean Rev"),
]


def _load_env() -> None:
    env_path = os.path.join(_DIR, "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def _klines_predict(kslice: list[dict]) -> list[dict]:
    return [
        {
            "open_time": k.get("open_time", 0),
            "open": k["open"],
            "high": k["high"],
            "low": k["low"],
            "close": k["close"],
            "volume": k.get("volume", 0),
            "taker_buy": k.get("taker_buy", 0),
        }
        for k in kslice
    ]


def _resolve_signal(algo_id: str, sym: str, kslice: list[dict], open_ms: int):
    kl = to_algo21_klines(kslice)
    if len(kl) < 30:
        return None, None
    if algo_id == "a2_05":
        sig = mean_reversion(kl)
        return (sig, "Mean Rev Z") if sig in ("UP", "DOWN") else (None, None)
    if algo_id == "a6v3":
        if sym == "BTCUSDT":
            sig = macd_histogram_div(kl)
            return (sig, "MACD Div") if sig in ("UP", "DOWN") else (None, None)
        if sym == "ETHUSDT":
            sig = rsi_divergence_strict(kl)
            return (sig, "RSI Div") if sig in ("UP", "DOWN") else (None, None)
        return None, "A2 Predictor"
    if algo_id == "melez":
        if sym == "BTCUSDT":
            sig = macd_histogram_div(kl)
            return (sig, "MACD Div") if sig in ("UP", "DOWN") else (None, None)
        sig = mean_reversion(kl)
        return (sig, "Mean Rev Z") if sig in ("UP", "DOWN") else (None, None)
    return None, None


def make_amount_fn(low: float, mid: float, high: float):
    def amount_fn(history, sym: str) -> float:
        rows = [{"symbol": t.symbol, "win": t.win} for t in history]
        return wr_tier_amount(rows, sym, low, mid, high)
    return amount_fn


def make_signal_fn(algo_id: str):
    async def signal(sym, kslice, open_ms, history, amount_fn):
        sig, engine = _resolve_signal(algo_id, sym, kslice, open_ms)
        if algo_id == "a6v3" and sym == "SOLUSDT":
            sig = await direction_a2(_klines_predict(kslice), sym, open_ms)
            engine = "A2 Predictor"
        if sig not in ("UP", "DOWN"):
            return None
        return {
            "predicted_dir": sig,
            "amount": None,
            "entry_price": kslice[-1]["close"],
            "extra": {"engine": engine},
        }
    return signal


def _monthly_by_symbol(trades: list[dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for t in trades:
        ym = (t.get("entry_time") or "")[:7]
        sym = t.get("symbol") or "?"
        if not ym or len(ym) < 7:
            continue
        bucket = out.setdefault(ym, {})
        row = bucket.setdefault(sym, {"n": 0, "w": 0, "pnl": 0.0})
        row["n"] += 1
        row["pnl"] = round(row["pnl"] + float(t.get("pnl") or 0), 2)
        if t.get("win"):
            row["w"] += 1
    return out


def _month_name(ym: str, dup: set[str]) -> str:
    y, m = ym.split("-")
    name = _TR_MONTHS_LC[int(m) - 1]
    if name in dup:
        name = f"{name} '{y[2:]}"
    return name


def build_simple_telegram_message(results: list[dict], period: str) -> str:
    lines = [
        "📊 <b>1Y Backtest · BTC ETH SOL</b>",
        f"{period}",
        f"💰 Giriş <b>$1.000</b> · işlem $36 / $48 / $72 (WR kademe)",
        "",
    ]
    for i, r in enumerate(results, 1):
        monthly = r.get("monthly_pnl") or {}
        yms = sorted(monthly.keys())
        names = [_TR_MONTHS_LC[int(ym.split("-")[1]) - 1] for ym in yms]
        dup = {n for n in names if names.count(n) > 1}
        fb = r.get("final_balance", 0)
        pnl = r.get("total_pnl", 0)
        lines.append(f"<b>{i}. {r['label']}</b>")
        for ym in yms:
            pnl_m = int(round(float(monthly[ym])))
            sign = "+" if pnl_m >= 0 else ""
            star = " ★" if pnl_m > 0 else ""
            lines.append(f"{_month_name(ym, dup)} {sign}{pnl_m}{star}")
        sign_y = "+" if pnl >= 0 else ""
        lines.append(f"→ Yıl sonu: <b>${fb:,.0f}</b> ({sign_y}${int(round(pnl)):,})")
        lines.append("")
    return "\n".join(lines).strip()


def render_chart(results: list[dict], period: str, out_path: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    fig = plt.figure(figsize=(14, 10), facecolor="#0a0e17")
    gs = fig.add_gridspec(4, 3, height_ratios=[0.55, 2.2, 2.2, 0.85], hspace=0.38, wspace=0.28)

    fig.text(
        0.5, 0.97,
        "1Y BACKTEST — A2#05 · A6V3 · MELEZ",
        ha="center", va="top", fontsize=16, fontweight="bold", color="#e8edf5",
    )
    fig.text(
        0.5, 0.935,
        f"{period}  ·  BTC · ETH · SOL  ·  Giriş $1.000  ·  İşlem $36 / $48 / $72",
        ha="center", va="top", fontsize=10, color="#8b9cb3",
    )

    colors_algo = ["#3b82f6", "#a855f7", "#22c55e"]
    all_yms = sorted({ym for r in results for ym in (r.get("monthly_pnl") or {})})

    for col, (r, ac) in enumerate(zip(results, colors_algo)):
        monthly = r.get("monthly_pnl") or {}
        yms = [ym for ym in all_yms if ym in monthly]
        vals = [monthly[ym] for ym in yms]
        labels = []
        names = [_TR_MONTHS[int(ym.split("-")[1]) - 1] for ym in yms]
        dup = {n for n in names if names.count(n) > 1}
        for ym in yms:
            y, m = ym.split("-")
            lbl = _TR_MONTHS[int(m) - 1]
            if lbl in dup:
                lbl = f"{lbl}'{y[2:]}"
            if monthly[ym] > 0:
                lbl += " ★"
            labels.append(lbl)

        ax = fig.add_subplot(gs[1, col])
        ax.set_facecolor("#111827")
        bar_c = ["#22c55e" if v >= 0 else "#ef4444" for v in vals]
        x = np.arange(len(vals))
        bars = ax.bar(x, vals, color=bar_c, edgecolor="#1f2937", linewidth=0.6, width=0.72)
        ax.axhline(0, color="#374151", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=7, color="#9ca3af")
        ax.set_title(r["label"], fontsize=12, fontweight="bold", color=ac, pad=8)
        ax.tick_params(axis="y", colors="#6b7280", labelsize=8)
        ax.spines[:].set_color("#1f2937")
        ax.grid(axis="y", alpha=0.15, color="#4b5563")
        for bar, v in zip(bars, vals):
            if abs(v) < 50:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (80 if v >= 0 else -80),
                f"{int(v):+d}",
                ha="center", va="bottom" if v >= 0 else "top",
                fontsize=6, color="#d1d5db",
            )

        ax2 = fig.add_subplot(gs[2, col])
        ax2.set_facecolor("#111827")
        ax2.axis("off")
        fb = r.get("final_balance", 0)
        pnl = r.get("total_pnl", 0)
        wr = r.get("win_rate_pct", 0)
        trades = r.get("trades", 0)
        pos_months = sum(1 for v in vals if v > 0)
        table_lines = [
            f"İşlem     {trades:,}",
            f"WR        {wr:.1f}%",
            f"Aylık +   {pos_months}/{len(vals)} ★",
            "",
            f"Giriş     $1.000",
            f"Yıl sonu  ${fb:,.0f}",
            f"Net P&L   {'+' if pnl >= 0 else ''}${pnl:,.0f}",
        ]
        y0 = 0.92
        for ln in table_lines:
            if not ln:
                y0 -= 0.06
                continue
            c = "#22c55e" if ln.startswith("Net") and pnl >= 0 else (
                "#ef4444" if ln.startswith("Net") else "#e5e7eb"
            )
            if ln.startswith("Yıl sonu"):
                c = "#fbbf24"
                ln = f"★ {ln}"
            ax2.text(0.08, y0, ln, transform=ax2.transAxes, fontsize=11,
                     fontweight="bold" if "Yıl sonu" in ln or "Net" in ln else "normal", color=c)
            y0 -= 0.14

    ax_sum = fig.add_subplot(gs[3, :])
    ax_sum.set_facecolor("#0a0e17")
    ax_sum.axis("off")
    summary_parts = []
    for r in results:
        fb = r.get("final_balance", 0)
        pnl = r.get("total_pnl", 0)
        summary_parts.append(
            f"{r['label']}: $1.000 → ${fb:,.0f}  ({'+' if pnl >= 0 else ''}${pnl:,.0f})"
        )
    ax_sum.text(
        0.5, 0.55, "  ·  ".join(summary_parts),
        ha="center", va="center", fontsize=11, color="#e8edf5", fontweight="bold",
    )
    ax_sum.text(
        0.5, 0.15, "★ = kârlı ay  ·  Walk-forward 1h  ·  PM sim 0.50 token",
        ha="center", va="center", fontsize=9, color="#6b7280",
    )

    green = mpatches.Patch(color="#22c55e", label="Kâr")
    red = mpatches.Patch(color="#ef4444", label="Zarar")
    fig.legend(handles=[green, red], loc="upper right", framealpha=0.2,
               facecolor="#111827", edgecolor="#374151", labelcolor="#d1d5db", fontsize=8)

    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="#0a0e17", pad_inches=0.35)
    plt.close()
    return out_path


def tg_send(text: str) -> None:
    from pm_trader_helpers import tg_send_pm_live
    if not tg_send_pm_live(text, label="1Y Backtest"):
        raise RuntimeError("Telegram metin gönderilemedi")


def tg_send_photo(path: str, caption: str = "") -> None:
    import json as _json
    boundary = "----BacktestBoundary"
    with open(path, "rb") as f:
        img = f.read()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n"
        f"{PM_LIVE_TG_CHAT}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n"
        f"{caption}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + img + f"\r\n--{boundary}--\r\n".encode()
    url = f"https://api.telegram.org/bot{PM_LIVE_TG_TOKEN}/sendPhoto"
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = _json.loads(resp.read())
    if not data.get("ok"):
        raise RuntimeError(f"Telegram foto: {data}")


async def run_all(start: datetime, balance: float) -> list[dict]:
    amount_fn = make_amount_fn(AMOUNT_LOW, AMOUNT_MID, AMOUNT_HIGH)
    results = []
    for algo_id, label, subtitle in ALGO_META:
        print(f"\n>>> {label} backtest ($1000 · $36/48/72)...")
        r = await run_walk_forward(
            label=label,
            symbols=SYMBOLS,
            signal_fn=make_signal_fn(algo_id),
            start_date=start,
            initial_balance=balance,
            min_bars=80,
            amount_fn=amount_fn,
        )
        r["id"] = algo_id
        r["subtitle"] = subtitle
        r["monthly_by_symbol"] = _monthly_by_symbol(r.get("trade_list") or [])
        print_summary(r)
        results.append(r)
    return results


async def _send_telegram(results: list[dict], period: str) -> None:
    msg = build_simple_telegram_message(results, period)
    print(f"[TG] Metin gönderiliyor...\n{msg}\n")
    tg_send(msg)
    chart = render_chart(results, period, CHART_FILE)
    print(f"[TG] Görsel: {chart}")
    tg_send_photo(chart, caption="1Y Backtest · $1000 · $36/48/72 · ★ kârlı ay")
    print("[TG] Tamamlandı (A2#16 Live kanalı)")


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

    results = await run_all(start, args.balance)

    payload = {
        "generated_at_tr": datetime.now(_TZ_TR).isoformat(),
        "period": period,
        "days": args.days,
        "amount_tiers": {"low": AMOUNT_LOW, "mid": AMOUNT_MID, "high": AMOUNT_HIGH},
        "initial_balance": args.balance,
        "algos": [{k: v for k, v in r.items() if k != "trade_list"} for r in results],
    }
    if not args.no_save:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\nKaydedildi: {OUT_FILE}")

    if args.telegram:
        await _send_telegram(results, period)


if __name__ == "__main__":
    asyncio.run(main())

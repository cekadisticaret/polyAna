#!/usr/bin/env python3
"""A2#03 · A2#05 · F16 — 1Y aylık Poly backtest PDF."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
import numpy as np

OUT = Path("/root/aiProject/temmuzPoly/a203-a205-f16-aylik.pdf")

cands = ["DejaVu Sans", "Noto Sans", "Liberation Sans", "FreeSans"]
avail = {f.name for f in font_manager.fontManager.ttflist}
family = next((c for c in cands if c in avail), "DejaVu Sans")
plt.rcParams["font.family"] = family
plt.rcParams["axes.unicode_minus"] = False

BG = "#0b1220"
CARD = "#131c2e"
TXT = "#e8edf5"
MUTED = "#8b95a8"
LINE = "#2a3548"
GOLD = "#f5c14a"
CYAN = "#3dd6f5"
GREEN = "#3dd68c"
RED = "#ff5d6c"
AMBER = "#f59e0b"

MONTHS = [
    "Ağu 25", "Eyl", "Eki", "Kas", "Ara",
    "Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu 26",
]

A203 = [33.3, 1415.89, -1122.58, 2708.2, -2789.49, 4593.84, 322.69, 767.03, 2321.6, 934.87, 5241.97, -2349.79, 3434.54]
A205 = [487.8, 2480.03, 472.94, 4953.23, 1050.3, 2193.65, -2377.87, -1573.05, 2771.28, 362.18, 904.25, -3124.68, 4849.28]
F16 = [775.62, 681.6, 1222.56, 552.5, 1821.55, 1636.51, 490.52, 1932.69, 2519.62, 2484.17, 1078.16, 1608.23, 129.79]


def cum(arr, start=1000.0):
    b = start
    out = []
    for p in arr:
        b += p
        out.append(b)
    return out


def money(n, signed=True):
    s = f"{abs(n):,.0f}".replace(",", ".")
    if not signed:
        return s
    if n > 0:
        return f"+{s}"
    if n < 0:
        return f"−{s}"
    return "0"


def card(ax, x, y, w, h, title, value, sub, accent):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            facecolor=CARD, edgecolor=accent, linewidth=1.6,
            transform=ax.transAxes, clip_on=False,
        )
    )
    ax.text(x + 0.018, y + h - 0.028, title, transform=ax.transAxes,
            fontsize=9, color=accent, fontweight="bold", va="top")
    ax.text(x + 0.018, y + h * 0.46, value, transform=ax.transAxes,
            fontsize=20, color=TXT, fontweight="bold", va="center")
    ax.text(x + 0.018, y + 0.028, sub, transform=ax.transAxes,
            fontsize=8, color=MUTED, va="bottom")


def page_cover(pdf):
    fig = plt.figure(figsize=(11.69, 8.27), facecolor=BG)
    fig.text(0.05, 0.94, "A2#03  ·  A2#05  ·  F16", fontsize=22, color=TXT, fontweight="bold")
    fig.text(
        0.05, 0.895,
        "1 yıllık Poly walk-forward  ·  aylık net P&L  ·  kasa $1.000  ·  kademe $24 / $36 / $48  ·  ask + taker",
        fontsize=9.5, color=MUTED,
    )
    fig.text(0.95, 0.94, "bursaapp", fontsize=10, color=MUTED, ha="right")

    axc = fig.add_axes([0, 0, 1, 1])
    axc.set_axis_off()
    axc.set_xlim(0, 1)
    axc.set_ylim(0, 1)
    card(axc, 0.05, 0.74, 0.28, 0.12, "A2#03  STOCH RSI", "+$15.512",
         "WR %52,4  ·  26.280 işlem  ·  10/13 ay artı", GOLD)
    card(axc, 0.36, 0.74, 0.28, 0.12, "A2#05  MEAN REV  Z", "+$13.449",
         "WR %52,4  ·  20.468 işlem  ·  10/13 ay artı", CYAN)
    card(axc, 0.67, 0.74, 0.28, 0.12, "F16  PREDICT()", "+$16.934",
         "WR %57,0  ·  3.343 işlem  ·  13/13 ay artı", GREEN)

    x = np.arange(len(MONTHS))
    w = 0.26
    ax = fig.add_axes([0.06, 0.38, 0.88, 0.32])
    ax.set_facecolor(CARD)
    ax.bar(x - w, A203, w, color=GOLD, label="A2#03", zorder=3)
    ax.bar(x, A205, w, color=CYAN, label="A2#05", zorder=3)
    ax.bar(x + w, F16, w, color=GREEN, label="F16", zorder=3)
    ax.axhline(0, color=LINE, lw=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(MONTHS, color=MUTED, fontsize=8)
    ax.tick_params(axis="y", colors=MUTED, labelsize=8)
    ax.set_ylabel("Aylık net $", color=MUTED, fontsize=8)
    for s in ax.spines.values():
        s.set_color(LINE)
    ax.grid(axis="y", color=LINE, lw=0.6, alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_title("Aylık net P&L ($)", color=TXT, fontsize=11, loc="left", pad=8)
    leg = ax.legend(loc="upper left", frameon=True, fontsize=8)
    leg.get_frame().set_facecolor(BG)
    leg.get_frame().set_edgecolor(LINE)
    for t in leg.get_texts():
        t.set_color(TXT)

    ax2 = fig.add_axes([0.06, 0.07, 0.88, 0.26])
    ax2.set_facecolor(CARD)
    ax2.plot(x, cum(A203), color=GOLD, lw=2.2, marker="o", ms=4, label="A2#03 kasa")
    ax2.plot(x, cum(A205), color=CYAN, lw=2.2, marker="o", ms=4, label="A2#05 kasa")
    ax2.plot(x, cum(F16), color=GREEN, lw=2.2, marker="o", ms=4, label="F16 kasa")
    ax2.axhline(1000, color=LINE, lw=0.8, ls="--")
    ax2.set_xticks(x)
    ax2.set_xticklabels(MONTHS, color=MUTED, fontsize=8)
    ax2.tick_params(axis="y", colors=MUTED, labelsize=8)
    ax2.set_ylabel("Kasa $", color=MUTED, fontsize=8)
    for s in ax2.spines.values():
        s.set_color(LINE)
    ax2.grid(axis="y", color=LINE, lw=0.6, alpha=0.7)
    ax2.set_axisbelow(True)
    ax2.set_title("Kümülatif kasa ($1.000 başlangıç)", color=TXT, fontsize=11, loc="left", pad=8)
    ax2.set_ylim(0, 20000)
    leg2 = ax2.legend(loc="upper left", frameon=True, fontsize=8)
    leg2.get_frame().set_facecolor(BG)
    leg2.get_frame().set_edgecolor(LINE)
    for t in leg2.get_texts():
        t.set_color(TXT)

    pdf.savefig(fig)
    plt.close(fig)


def page_table(pdf):
    fig = plt.figure(figsize=(11.69, 8.27), facecolor=BG)
    fig.text(0.05, 0.94, "Ay ay net  ·  kasa sonu", fontsize=18, color=TXT, fontweight="bold")
    fig.text(
        0.05, 0.90,
        "A2#03 ve A2#05: 30.08.2025 → 30.08.2026  ·  BTC/ETH/SOL     "
        "F16: 15.08.2025 → 15.08.2026  ·  canlı predict()  ·  yalnız BTC+SOL",
        fontsize=8.5, color=MUTED,
    )

    e203, e205, e16 = cum(A203), cum(A205), cum(F16)
    headers = ["Ay", "A2#03", "kasa", "A2#05", "kasa", "F16", "kasa"]
    cell = [headers]
    for i, m in enumerate(MONTHS):
        cell.append([
            m,
            money(A203[i]), money(e203[i], signed=False),
            money(A205[i]), money(e205[i], signed=False),
            money(F16[i]), money(e16[i], signed=False),
        ])
    cell.append([
        "YIL",
        money(sum(A203)), money(e203[-1], signed=False),
        money(sum(A205)), money(e205[-1], signed=False),
        money(sum(F16)), money(e16[-1], signed=False),
    ])

    ax = fig.add_axes([0.04, 0.38, 0.92, 0.50])
    ax.axis("off")
    tbl = ax.table(
        cellText=cell,
        loc="center",
        cellLoc="right",
        colWidths=[0.10, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.scale(1, 1.45)
    for (r, c), cell_obj in tbl.get_celld().items():
        cell_obj.set_edgecolor(LINE)
        cell_obj.set_linewidth(0.4)
        if r == 0:
            cell_obj.set_facecolor("#1a2740")
            cell_obj.set_text_props(color=TXT, fontweight="bold", ha="center")
            continue
        if r == len(cell) - 1:
            cell_obj.set_facecolor("#1e2d18" if c == 0 else "#162418")
            cell_obj.set_text_props(color=TXT, fontweight="bold")
            continue
        cell_obj.set_facecolor(CARD if r % 2 else "#101828")
        txt = cell_obj.get_text()
        txt.set_color(TXT)
        if c in (1, 3, 5) and r > 0:
            raw = [A203, A205, F16][(c - 1) // 2][r - 1]
            txt.set_color(GREEN if raw > 0 else (RED if raw < 0 else MUTED))
            txt.set_fontweight("bold")
        if c == 0:
            txt.set_ha("left")
            txt.set_color(MUTED)

    # coin bars
    coins = [
        ("A2#03", GOLD, [("ETH", 10232), ("BTC", 4014), ("SOL", 1266)]),
        ("A2#05", CYAN, [("ETH", 7951), ("BTC", 3996), ("SOL", 1502)]),
        ("F16", GREEN, [("BTC", 9981), ("SOL", 6952)]),
    ]
    for i, (name, col, parts) in enumerate(coins):
        axb = fig.add_axes([0.06 + i * 0.31, 0.08, 0.27, 0.24])
        axb.set_facecolor(CARD)
        labels = [p[0] for p in parts]
        vals = [p[1] for p in parts]
        bars = axb.barh(labels[::-1], vals[::-1], color=col, height=0.55)
        axb.set_title(f"{name}  coin net $", color=col, fontsize=10, loc="left", pad=6)
        axb.tick_params(colors=MUTED, labelsize=8)
        for s in axb.spines.values():
            s.set_color(LINE)
        axb.grid(axis="x", color=LINE, lw=0.6)
        axb.set_axisbelow(True)
        for bar, v in zip(bars, vals[::-1]):
            axb.text(v + 80, bar.get_y() + bar.get_height() / 2,
                     money(v), va="center", color=TXT, fontsize=8, fontweight="bold")
        axb.set_xlim(0, 12000)

    fig.text(
        0.05, 0.025,
        "Ağu 25 / Ağu 26 kısmi ay. F16 toplu 71-defter koşusundaki 3 oylu vekil değil — canlı predict() backtest’i. "
        "A2#03 = A1#06 Stoch RSI (aynı motor).",
        fontsize=7.5, color=MUTED,
    )
    pdf.savefig(fig)
    plt.close(fig)


def page_detail(pdf):
    fig = plt.figure(figsize=(11.69, 8.27), facecolor=BG)
    fig.text(0.05, 0.94, "Defter kartları", fontsize=18, color=TXT, fontweight="bold")
    fig.text(0.05, 0.90, "Yeşil artı ay  ·  kırmızı eksi ay  ·  çubuk üstü net $", fontsize=9, color=MUTED)

    series = [
        ("A2#03  Stochastic RSI", GOLD, A203, "+$15.512", "%52,4 WR", "BTC/ETH/SOL  ·  her saat sinyal",
         "Eksi: Eki 25 · Ara 25 · Tem 26    En iyi: Haz 26  +5.242"),
        ("A2#05  Mean Reversion (Z)", CYAN, A205, "+$13.449", "%52,4 WR", "BTC/ETH/SOL  ·  z-skor mean rev",
         "Eksi: Şub · Mar · Tem    En iyi: Kas 25  +4.953"),
        ("F16  predict()  ·  1. Analiz", GREEN, F16, "+$16.934", "%57,0 WR", "BTC+SOL  ·  weekday predict()",
         "13/13 ay artı    En iyi: Nis 26  +2.520    Ağu 26 zayıf +130"),
    ]
    x = np.arange(len(MONTHS))
    for i, (title, col, vals, pnl, wr, sub, note) in enumerate(series):
        top = 0.86 - i * 0.27
        ax = fig.add_axes([0.06, top - 0.20, 0.88, 0.20])
        ax.set_facecolor(CARD)
        colors = [GREEN if v >= 0 else RED for v in vals]
        bars = ax.bar(x, vals, color=colors, width=0.72, zorder=3)
        ax.axhline(0, color=LINE, lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(MONTHS if i == 2 else [""] * len(MONTHS), color=MUTED, fontsize=8)
        ax.tick_params(axis="y", colors=MUTED, labelsize=7)
        for s in ax.spines.values():
            s.set_color(LINE)
        ax.grid(axis="y", color=LINE, lw=0.5)
        ax.set_axisbelow(True)
        ax.set_title(f"{title}     {pnl}     {wr}", color=col, fontsize=11, loc="left", pad=6)
        ax.text(0.99, 0.92, sub, transform=ax.transAxes, ha="right", va="top", color=MUTED, fontsize=8)
        ax.text(0.01, 0.04, note, transform=ax.transAxes, color=MUTED, fontsize=7.5)
        for bar, v in zip(bars, vals):
            if abs(v) < 400:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (120 if v >= 0 else -120),
                money(v),
                ha="center", va="bottom" if v >= 0 else "top",
                fontsize=6.5, color=TXT,
            )

    fig.text(
        0.05, 0.03,
        "Kaynak: backtest_algo_islemler_1y.json (A2)  ·  backtest_selected_algos_1y.json (F16 predict)",
        fontsize=7.5, color=MUTED,
    )
    pdf.savefig(fig)
    plt.close(fig)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUT) as pdf:
        page_cover(pdf)
        page_table(pdf)
        page_detail(pdf)
        d = pdf.infodict()
        d["Title"] = "A2#03 · A2#05 · F16 — 1Y aylık Poly"
        d["Author"] = "bursaapp"
        d["Subject"] = "Walk-forward hourly Polymarket paper backtest"
    print(OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()

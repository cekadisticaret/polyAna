#!/usr/bin/env python3
"""Son 7 gün — saatlik A1/A2/A6/A10/A15 + A2 Top17 başarılı slot ısı haritası → Telegram.

15m trader'lar (110, 15M A2 vb.) dahil edilmez.

Kullanım:
  python3 temmuzPoly/weekly_slot_heatmap_all.py          # üret + gönder
  python3 temmuzPoly/weekly_slot_heatmap_all.py preview  # sadece PNG
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_TZ = ZoneInfo("Europe/Istanbul")
_DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
OUT_IMG = "/tmp/poly_weekly_slot_heatmap_all.png"

# .env — B1/A6/A15 ile aynı Telegram kanalı
_ENV = _ROOT / ".env"
if _ENV.is_file():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from telegram_poly_channels import chat_analiz4

# B1/A6/A15 Telegram kanalı (chat_analiz4 bot)
BOT_TOKEN = os.getenv(
    "TELEGRAM_ANALIZ4_BOT_TOKEN",
    "8630483764:AAFmAmG4nHAGb238wpavlWgMjJZDvIy4DzE",
)
CHAT_ID = chat_analiz4()

# Saatlik sanal kitaplar (+ A2 Top17). 15m (110 vb.) yok.
BOOKS: list[tuple[str, Path]] = [
    ("A1", _DIR / "poly_trader_analiz1_history.json"),
    ("A2", _DIR / "poly_trader_analiz2_history.json"),
    ("A6", _DIR / "poly_trader_analiz6_history.json"),
    ("A10", _DIR / "poly_trader_analiz10_history.json"),
    ("A15", _DIR / "poly_trader_analiz15_history.json"),
]
for i in range(1, 18):
    BOOKS.append((f"#{i:02d}", _DIR / f"poly_trader_a2_{i:02d}_history.json"))

CORE_LABELS = ["A1", "A2", "A6", "A10", "A15"]


def _load_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("trades") or data.get("history") or []
    return []


def _parse_entry_tr(t: dict) -> datetime | None:
    raw = t.get("entry_time_tr") or t.get("exit_time_tr")
    if not raw:
        return None
    try:
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ)
        return dt.astimezone(_TZ)
    except Exception:
        return None


def collect_wins(days: int = 7) -> tuple[dict, list[tuple], dict]:
    """wins[(dow, hour)] -> set(labels); events list; stats per label."""
    now = datetime.now(_TZ)
    cutoff = now - timedelta(days=days)
    wins: dict[tuple[int, int], set[str]] = defaultdict(set)
    events: list[tuple[datetime, str, int, int, str]] = []  # dt, label, dow, hour, sym
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"w": 0, "t": 0})

    for label, path in BOOKS:
        for t in _load_history(path):
            dt = _parse_entry_tr(t)
            if dt is None or dt < cutoff:
                continue
            dow = t.get("entry_dow")
            hour = t.get("entry_hour_tr")
            if dow is None:
                dow = dt.weekday()
            if hour is None:
                hour = dt.hour
            dow = int(dow)
            hour = int(hour)
            stats[label]["t"] += 1
            won = bool(t.get("win"))
            if won:
                stats[label]["w"] += 1
                wins[(dow, hour)].add(label)
                sym = (t.get("symbol") or "").replace("USDT", "") or "?"
                events.append((dt, label, dow, hour, sym))

    events.sort(key=lambda x: x[0])
    return wins, events, dict(stats)


def render_heatmap(wins: dict, events: list, stats: dict, days: int = 7) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    now = datetime.now(_TZ)
    # grid: count of distinct winning books
    grid = np.zeros((7, 24), dtype=float)
    labels_grid: list[list[str]] = [["" for _ in range(24)] for _ in range(7)]
    for (dow, hour), labs in wins.items():
        if not (0 <= dow <= 6 and 0 <= hour <= 23):
            continue
        ordered = sorted(labs, key=lambda x: (x.startswith("#"), x))
        grid[dow][hour] = len(ordered)
        # hücreye sığacak kadar etiket
        shown = ordered[:6]
        extra = len(ordered) - len(shown)
        txt = "\n".join(shown)
        if extra > 0:
            txt += f"\n+{extra}"
        labels_grid[dow][hour] = txt

    fig, axes = plt.subplots(
        2, 1, figsize=(16, 11), gridspec_kw={"height_ratios": [2.2, 1.0]}
    )
    fig.patch.set_facecolor("#0a0e1a")

    # ── Üst: gün × saat ──
    ax = axes[0]
    ax.set_facecolor("#0a0e1a")
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "win_heat",
        ["#141820", "#1b5e20", "#43a047", "#00e676", "#eeff41"],
        N=256,
    )
    im = ax.imshow(grid, cmap=cmap, vmin=0, vmax=max(4, grid.max()), aspect="auto")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS, fontsize=10, color="#b0bec5", fontweight="bold")
    ax.tick_params(length=0)
    for d in range(7):
        for h in range(24):
            if grid[d][h] <= 0:
                continue
            ax.text(
                h,
                d,
                labels_grid[d][h],
                ha="center",
                va="center",
                fontsize=5.5,
                color="white",
                fontweight="bold",
                linespacing=1.25,
            )
    for x in range(25):
        ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.6)
    for y in range(8):
        ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.6)

    n_evt = len(events)
    n_slots = sum(1 for v in wins.values() if v)
    ax.set_title(
        f"Son {days} gün — Başarılı slotlar (gün × saat İST)\n"
        f"{now.strftime('%d.%m.%Y %H:%M')} İST  |  {n_evt} kazanç  |  {n_slots} dolu hücre  |  "
        f"Hücre = o saatte kazanan kitaplar",
        color="#4fc3f7",
        fontsize=11,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel("Saat (İST)", color="#546e7a", fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cbar.set_label("# kazanan kitap", color="#546e7a", fontsize=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#546e7a", fontsize=7)

    # ── Alt: kitap özeti (WR son 7g) ──
    ax2 = axes[1]
    ax2.set_facecolor("#0a0e1a")
    ax2.axis("off")
    core = list(CORE_LABELS)
    lines = ["Kitap WR (son 7 gün, saatlik)", ""]
    for lab in core:
        st = stats.get(lab) or {"w": 0, "t": 0}
        wr = (100.0 * st["w"] / st["t"]) if st["t"] else 0.0
        lines.append(f"  {lab:4}  {st['w']:3}/{st['t']:<3}  %{wr:5.1f}")
    # A2 top17 özet
    a2w = sum((stats.get(f"#{i:02d}") or {}).get("w", 0) for i in range(1, 18))
    a2t = sum((stats.get(f"#{i:02d}") or {}).get("t", 0) for i in range(1, 18))
    a2wr = (100.0 * a2w / a2t) if a2t else 0.0
    lines.append(f"  A2T   {a2w:3}/{a2t:<3}  %{a2wr:5.1f}  (Top17 toplam)")
    # en sıcak A2# 
    best_a2 = sorted(
        (
            (lab, st["w"], st["t"], 100.0 * st["w"] / st["t"] if st["t"] else 0)
            for lab, st in stats.items()
            if lab.startswith("#") and st["t"] >= 2
        ),
        key=lambda x: (x[3], x[1]),
        reverse=True,
    )[:5]
    if best_a2:
        lines.append("")
        lines.append("A2 Top17 sıcak:")
        for lab, w, t, wr in best_a2:
            lines.append(f"  {lab}  {w}/{t}  %{wr:.0f}")

    ax2.text(
        0.02,
        0.98,
        "\n".join(lines),
        transform=ax2.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        color="#cfd8dc",
        family="monospace",
        linespacing=1.35,
    )

    # sağda örnek olay listesi (kısa)
    sample = []
    for dt, lab, dow, hour, sym in events[-18:]:
        sample.append(f"{_DAYS[dow]} {hour:02d}:00  {lab:4}  {sym}")
    ax2.text(
        0.45,
        0.98,
        "Son kazançlar (örnek)\n\n" + ("\n".join(sample) if sample else "—"),
        transform=ax2.transAxes,
        va="top",
        ha="left",
        fontsize=8,
        color="#90a4ae",
        family="monospace",
        linespacing=1.3,
    )

    plt.tight_layout(pad=1.4)
    plt.savefig(OUT_IMG, dpi=150, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.15)
    plt.close()
    return Path(OUT_IMG)


def format_text(wins: dict, events: list, stats: dict, days: int = 7) -> str:
    now = datetime.now(_TZ)
    # gün → saat → labels
    by_day: dict[int, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for (dow, hour), labs in wins.items():
        by_day[dow][hour] |= labs

    parts = [
        f"📊 <b>Son {days} gün — Başarılı slot haritası</b>",
        f"{now.strftime('%d.%m.%Y %H:%M')} İST",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for dow in range(7):
        hours = by_day.get(dow) or {}
        if not hours:
            continue
        parts.append(f"\n<b>{_DAYS[dow]}</b>")
        for hour in sorted(hours):
            labs = sorted(hours[hour], key=lambda x: (x.startswith("#"), x))
            # ana kitapları öne al
            core = [x for x in labs if not x.startswith("#")]
            algo = [x for x in labs if x.startswith("#")]
            shown = core + (algo[:4] if algo else [])
            if len(algo) > 4:
                shown.append(f"+{len(algo)-4}algo")
            parts.append(f"  {_DAYS[dow]} {hour:02d}:00 — {', '.join(shown)}")

    parts.append("\n━━━━━━━━━━━━━━━━━━━━")
    parts.append("<b>Kitap WR</b>")
    for lab in CORE_LABELS:
        st = stats.get(lab) or {"w": 0, "t": 0}
        wr = (100.0 * st["w"] / st["t"]) if st["t"] else 0
        parts.append(f"  {lab}: {st['w']}/{st['t']} (%{wr:.0f})")
    return "\n".join(parts)


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    boundary = "----PolyHeatBoundary"
    with open(path, "rb") as f:
        img = f.read()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"heatmap.png\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + img + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def tg_send(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps(
        {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "send"
    days = 7
    wins, events, stats = collect_wins(days=days)
    path = render_heatmap(wins, events, stats, days=days)
    print(f"PNG: {path}  events={len(events)} slots={sum(1 for v in wins.values() if v)}")
    if mode == "preview":
        return
    caption = (
        f"📊 Son {days} gün başarılı slot haritası — {datetime.now(_TZ).strftime('%d.%m.%Y %H:%M')} İST\n"
        f"A1 A2 A6 A10 A15 · A2 Top17 (saatlik; 15m yok)"
    )
    tg_send_photo(str(path), caption)
    # Telegram mesaj limiti ~4096; gerekirse kısalt
    text = format_text(wins, events, stats, days=days)
    if len(text) > 4000:
        text = text[:3900] + "\n… (kısaltıldı)"
    tg_send(text)
    print("Telegram gönderildi.")


if __name__ == "__main__":
    main()

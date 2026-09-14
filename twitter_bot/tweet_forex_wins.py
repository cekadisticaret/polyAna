#!/usr/bin/env python3
"""CEM01 (/forex/grafik) kazanan işlemleri 30 dk'da bir tweetler.

Birden fazla kazanan varsa hepsi aynı görselde + defter WR.

  python3 twitter_bot/tweet_forex_wins.py
  python3 twitter_bot/tweet_forex_wins.py --dry-run
  python3 twitter_bot/tweet_forex_wins.py --sample 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
if not os.path.exists(os.path.join(_ROOT, "EylulForex", "data", "forex_paper_history.json")):
    raise SystemExit(0)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from post_tweet import TWITTER_HANDLE, post_tweet_with_image  # noqa: E402
from render_card import render_forex_wins  # noqa: E402

_TZ = ZoneInfo("Europe/Istanbul")
HIST = os.path.join(_ROOT, "EylulForex", "data", "forex_paper_history.json")
OUT_DIR = os.path.join(_DIR, "data")
STATE_FILE = os.path.join(OUT_DIR, "forex_wins_state.json")
OUT_IMG = os.path.join(OUT_DIR, "forex_wins_latest.png")
LOOKBACK_MIN = 30
MAX_ROWS = 8
POSTED_MAX = 400
WR_SHOW_MIN = 55.0


def _now() -> datetime:
    return datetime.now(_TZ)


def _parse_close(s: str) -> datetime | None:
    try:
        return datetime.strptime(str(s), "%Y.%m.%d %H:%M:%S").replace(tzinfo=_TZ)
    except Exception:
        return None


def _load_hist() -> list[dict]:
    try:
        rows = json.load(open(HIST))
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _book_wr(hist: list[dict]) -> tuple[float, int, int]:
    n = len(hist)
    wins = sum(1 for t in hist if float(t.get("pnl") or 0) > 0)
    wr = (100.0 * wins / n) if n else 0.0
    return wr, wins, n


def _decorate(t: dict) -> dict:
    row = dict(t)
    ct = _parse_close(t.get("close_time") or "")
    row["close_clock"] = ct.strftime("%H:%M") if ct else ""
    row["_closed"] = ct
    return row


def _winners_in_window(hist: list[dict], minutes: float) -> list[dict]:
    cutoff = _now() - timedelta(minutes=minutes)
    out = []
    for t in hist:
        if float(t.get("pnl") or 0) <= 0:
            continue
        row = _decorate(t)
        if row["_closed"] and row["_closed"] >= cutoff:
            out.append(row)
    out.sort(key=lambda x: x["_closed"] or _now())
    return out[-MAX_ROWS:]


def _last_wins(hist: list[dict], n: int) -> list[dict]:
    wins = [_decorate(t) for t in hist if float(t.get("pnl") or 0) > 0]
    return wins[-max(1, min(n, MAX_ROWS)):]


def _load_state() -> dict:
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {}


def _save_state(st: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)


def _new_only(trades: list[dict], posted: set[str]) -> list[dict]:
    return [t for t in trades if str(t.get("id") or "") not in posted]


def build_caption(trades: list[dict], wr: float, wins: int, n: int) -> str:
    lines = [
        f"⚡ XAUUSD · FOREX",
        f"{len(trades)} winner{'s' if len(trades) != 1 else ''}",
    ]
    if wr > WR_SHOW_MIN:
        lines.append(f"Book WR {wr:.1f}% ({wins}/{n})")
    for t in trades[:6]:
        side = "SHORT" if str(t.get("side") or "").lower() in ("sell", "short") else "LONG"
        pnl = float(t.get("pnl") or 0)
        entry = float(t.get("entry") or 0)
        exit_px = float(t.get("exit") or 0)
        clock = t.get("close_clock") or ""
        lines.append(f"{side} {entry:,.2f} → {exit_px:,.2f}  +${pnl:.2f}  {clock}")
    lines.append(f"#Forex #Gold #XAUUSD #{TWITTER_HANDLE}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sample", type=int, nargs="?", const=3, default=0,
                    help="Son N kazananı örnek tweet olarak at (pencere yok)")
    args = ap.parse_args()

    hist = _load_hist()
    wr, wins, n = _book_wr(hist)
    if args.sample:
        trades = _last_wins(hist, args.sample)
        window = "sample"
    else:
        trades = _winners_in_window(hist, LOOKBACK_MIN)
        window = "last 30m"

    if not trades:
        print(f"Son {LOOKBACK_MIN} dk'da kazanan yok, tweet atlanıyor.")
        return

    st = _load_state()
    posted = {str(k) for k in (st.get("posted_ids") or [])}
    fresh = trades if args.sample else _new_only(trades, posted)
    if not fresh:
        print("Bu kazananlar zaten tweetlendi, atlanıyor.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    ts_label = _now().strftime("%d.%m.%Y %H:%M")
    render_forex_wins(
        fresh,
        wr=wr,
        wins=wins,
        trades_n=n,
        ts_label=ts_label,
        out_path=OUT_IMG,
        window_label=window,
    )
    caption = build_caption(fresh, wr, wins, n)
    print(caption)
    print(f"Görsel: {OUT_IMG}")

    if args.dry_run:
        print("(dry-run) tweet atılmadı.")
        return

    url = post_tweet_with_image(caption, OUT_IMG)
    print(f"Tweet atıldı: {url}")
    ids = [k for k in (st.get("posted_ids") or []) if k]
    for t in fresh:
        tid = str(t.get("id") or "")
        if tid and tid not in ids:
            ids.append(tid)
    st["posted_ids"] = ids[-POSTED_MAX:]
    st["last_url"] = url
    st["last_at"] = ts_label
    _save_state(st)


if __name__ == "__main__":
    main()

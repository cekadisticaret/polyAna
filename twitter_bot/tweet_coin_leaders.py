#!/usr/bin/env python3
"""Saatlik 'Coin liderleri' görseli üretip @ZekaChain hesabından tweet atar.

  python3 twitter_bot/tweet_coin_leaders.py            # gerçek tweet
  python3 twitter_bot/tweet_coin_leaders.py --dry-run   # sadece görsel üret, tweet atma
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
_KRIPTO = os.path.join(_ROOT, "AgustosKripto")
_TEST = os.path.join(_KRIPTO, "Test")
for p in (_KRIPTO, _TEST, _DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from render_card import render_coin_leaders  # noqa: E402
from post_tweet import post_tweet_with_image  # noqa: E402

_TZ_TR = ZoneInfo("Europe/Istanbul")
OUT_IMG = os.path.join(_DIR, "data", "coin_leaders_latest.png")


def _get_coin_leaders() -> list[dict]:
    from virtual_book import read_snapshot  # noqa: E402
    snap = read_snapshot("test", max_age=900)
    if snap and snap.get("coin_leaders"):
        return list(snap["coin_leaders"])
    import runner as test_runner  # noqa: E402
    return test_runner.compute_coin_leaders()


def build_rows(leaders: list[dict]) -> tuple[list[dict], float, int]:
    with_data = [l for l in leaders if l.get("best")]
    if not with_data:
        return [], 0.0, 0
    avg_wr = sum(float(l["best"].get("wr") or 0) for l in with_data) / len(with_data)
    rows = []
    for l in with_data[:6]:
        b = l["best"]
        rows.append({
            "symbol": l["symbol"],
            "algo": b["algo"],
            "wins": b["wins"],
            "trades": b["trades"],
            "pnl": b["pnl"],
        })
    return rows, avg_wr, len(with_data)


def build_caption(rows: list[dict], avg_wr: float, coin_count: int) -> str:
    top = rows[0] if rows else None
    lines = [
        f"📊 Saatlik Coin Liderleri — ortalama WR %{avg_wr:.0f} ({coin_count} coin)",
    ]
    if top:
        lines.append(f"🥇 {top['symbol']} · {top['algo']} — {top['wins']}/{top['trades']} işlem")
    lines.append("#Kripto #Bitcoin #Algoritma #ZekaChain")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(OUT_IMG), exist_ok=True)
    leaders = _get_coin_leaders()
    rows, avg_wr, coin_count = build_rows(leaders)
    if not rows:
        print("Yeterli veri yok, tweet atlanıyor.")
        return

    now_tr = datetime.now(_TZ_TR)
    ts_label = now_tr.strftime("%d.%m.%Y %H:%M")
    render_coin_leaders(rows, avg_wr=avg_wr, coin_count=coin_count, ts_label=ts_label, out_path=OUT_IMG)
    caption = build_caption(rows, avg_wr, coin_count)

    print(caption)
    print(f"Görsel: {OUT_IMG}")

    if args.dry_run:
        print("(dry-run) Tweet atılmadı.")
        return

    try:
        url = post_tweet_with_image(caption, OUT_IMG)
        print(f"Tweet atıldı: {url}")
    except Exception as e:
        print(f"HATA: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

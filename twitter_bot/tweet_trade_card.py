#!/usr/bin/env python3
"""Saatlik en başarılı kapanan işlemi (giriş/kapanış fiyatı + kâr) görsel kart olarak tweetler.

  python3 twitter_bot/tweet_trade_card.py            # gerçek tweet
  python3 twitter_bot/tweet_trade_card.py --dry-run   # sadece görsel üret, tweet atma
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
_KRIPTO = os.path.join(_ROOT, "AgustosKripto")
_TEST = os.path.join(_KRIPTO, "Test")
for p in (_KRIPTO, _TEST, _DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from render_card import render_trade_card  # noqa: E402
from post_tweet import post_tweet_with_image, TWITTER_HANDLE  # noqa: E402

_TZ_TR = ZoneInfo("Europe/Istanbul")
OUT_IMG = os.path.join(_DIR, "data", "trade_card_latest.png")
STATE_FILE = os.path.join(_DIR, "data", "trade_card_state.json")
LOOKBACK_HOURS = 3


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def _recent_full_trades(hours: float = LOOKBACK_HOURS) -> list[dict]:
    import runner as test_runner  # noqa: E402
    from virtual_book import load_history  # noqa: E402

    cutoff = datetime.now(_TZ_TR) - timedelta(hours=hours)
    out: list[dict] = []
    for book in test_runner.ALL_BOOKS:
        hp = test_runner._history_path_for_book(book)  # noqa: SLF001
        if not hp:
            continue
        try:
            hist = load_history(hp)
        except Exception:
            continue
        for t in hist[-8:]:
            ets = t.get("exit_time_tr") or ""
            try:
                et = datetime.fromisoformat(ets)
            except Exception:
                continue
            if et < cutoff:
                continue
            entry_px = float(t.get("entry_price") or 0)
            margin = float(t.get("margin_usd") or 0)
            if entry_px <= 0 or margin <= 0:
                continue
            row = dict(t)
            row["pnl_pct"] = round(100.0 * float(t.get("pnl") or 0) / margin, 2)
            row["_key"] = f"{row.get('symbol')}|{row.get('entry_time_tr')}|{row.get('algo')}"
            out.append(row)
    return out


def pick_best_trade(trades: list[dict], exclude_key: str | None) -> dict | None:
    wins = [t for t in trades if t.get("win") and t.get("_key") != exclude_key]
    if not wins:
        return None
    wins.sort(key=lambda t: t.get("pnl_pct", 0), reverse=True)
    return wins[0]


def build_caption(trade: dict, *, lang: str = "tr") -> str:
    symbol = str(trade.get("symbol") or "").upper().replace("USDT", "")
    side = str(trade.get("side") or "").upper()
    algo = trade.get("algo") or ""
    pnl_pct = trade.get("pnl_pct")
    pnl = float(trade.get("pnl") or 0)
    lev = trade.get("leverage")
    dir_txt = "LONG 📈" if side == "LONG" else "SHORT 📉"
    if lang == "en":
        lines = [
            f"⚡ {symbol}/USDT {dir_txt} — {algo}",
            f"Entry: ${trade.get('entry_price'):,g} → Exit: ${trade.get('exit_price'):,g}",
            f"Profit: {pnl_pct:+.1f}%" + (f" ({int(lev)}x leverage)" if lev else "") + f" · ${pnl:+.2f}",
            f"#Crypto #Bitcoin #Algo #{TWITTER_HANDLE}",
        ]
    else:
        lines = [
            f"⚡ {symbol}/USDT {dir_txt} — {algo}",
            f"Giriş: ${trade.get('entry_price'):,g} → Kapanış: ${trade.get('exit_price'):,g}",
            f"Kâr: {pnl_pct:+.1f}%" + (f" ({int(lev)}x kaldıraç)" if lev else "") + f" · ${pnl:+.2f}",
            f"#Kripto #Bitcoin #Algoritma #{TWITTER_HANDLE}",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Dedupe kontrolünü atla")
    ap.add_argument("--lang", choices=("tr", "en"), default=os.environ.get("TWITTER_LANG", "tr"))
    args = ap.parse_args()

    state = _load_state()
    trades = _recent_full_trades()
    best = pick_best_trade(trades, exclude_key=None if args.force else state.get("last_key"))
    if not best:
        print(f"Son {LOOKBACK_HOURS} saatte yeni/uygun kazanan işlem yok, tweet atlanıyor.")
        return

    os.makedirs(os.path.dirname(OUT_IMG), exist_ok=True)
    ts_label = datetime.now(_TZ_TR).strftime("%d.%m.%Y %H:%M")
    render_trade_card(best, ts_label=ts_label, out_path=OUT_IMG, lang=args.lang)
    caption = build_caption(best, lang=args.lang)

    print(caption)
    print(f"Görsel: {OUT_IMG}")

    if args.dry_run:
        print("(dry-run) Tweet atılmadı.")
        return

    try:
        url = post_tweet_with_image(caption, OUT_IMG)
        print(f"Tweet atıldı: {url}")
        state["last_key"] = best["_key"]
        _save_state(state)
    except Exception as e:
        print(f"HATA: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

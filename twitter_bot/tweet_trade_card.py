#!/usr/bin/env python3
"""Saatlik kazanan işlemleri görsel kart olarak tweetler (@tradecomio).

  python3 twitter_bot/tweet_trade_card.py
  python3 twitter_bot/tweet_trade_card.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
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
OUT_DIR = os.path.join(_DIR, "data")
STATE_FILE = os.path.join(OUT_DIR, "trade_card_state.json")
LOOKBACK_HOURS = 3
SYMBOL_COOLDOWN_HOURS = 6
RECENT_SYMBOLS_MAX = 12
POSTED_KEYS_MAX = 400
MAX_PER_RUN = 2
TWEET_GAP_SEC = 4
# Yalnızca margin üzerinden %kâr bu eşiği aşan işlemler tweetlenir (TWITTER_MIN_PNL_PCT ile override).
MIN_PNL_PCT = float(os.environ.get("TWITTER_MIN_PNL_PCT", "5"))


def _norm_symbol(sym: str) -> str:
    return str(sym or "").upper().replace("USDT", "")


def _deprioritize_symbols() -> set[str]:
    """Başka kazanan varken tweet önceliği düşük coinler (tamamen yasak değil)."""
    raw = os.environ.get("TWITTER_DEPRIORITIZE_SYMBOLS", "KAITO")
    return {_norm_symbol(s) for s in raw.split(",") if s.strip()}


def _excluded_symbols() -> set[str]:
    raw = os.environ.get("TWITTER_EXCLUDE_SYMBOLS", "")
    return {_norm_symbol(s) for s in raw.split(",") if s.strip()}


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
    except Exception:
        st = {}
    # eski last_key → posted_keys göçü
    if st.get("last_key") and not st.get("posted_keys"):
        st["posted_keys"] = [st["last_key"]]
    return st


def _save_state(state: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def _slot_key(trade: dict) -> str:
    slot = trade.get("slot")
    if slot:
        return str(slot)
    ets = trade.get("exit_time_tr") or ""
    try:
        return datetime.fromisoformat(ets).strftime("%Y-%m-%d %H:00")
    except Exception:
        return ets[:13] if ets else "unknown"


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
        for t in hist[-16:]:
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


def _posted_keys(state: dict) -> set[str]:
    keys = state.get("posted_keys") or []
    if isinstance(keys, list):
        return {str(k) for k in keys}
    return set()


def _recently_tweeted_symbols(state: dict) -> set[str]:
    cutoff = datetime.now(_TZ_TR) - timedelta(hours=SYMBOL_COOLDOWN_HOURS)
    out: set[str] = set()
    for row in state.get("recent_symbols") or []:
        if not isinstance(row, dict):
            continue
        sym = _norm_symbol(row.get("symbol") or "")
        ts = row.get("ts") or ""
        if not sym:
            continue
        try:
            if datetime.fromisoformat(ts) >= cutoff:
                out.add(sym)
        except Exception:
            continue
    return out


def _best_per_symbol(trades: list[dict]) -> list[dict]:
    by_sym: dict[str, dict] = {}
    for t in sorted(trades, key=lambda x: (-x.get("pnl_pct", 0), x.get("exit_time_tr") or "")):
        sym = _norm_symbol(t.get("symbol") or "")
        if sym and sym not in by_sym:
            by_sym[sym] = t
    return sorted(by_sym.values(), key=lambda x: (-x.get("pnl_pct", 0), x.get("exit_time_tr") or ""))


def _split_by_priority(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    dep = _deprioritize_symbols()
    preferred: list[dict] = []
    low: list[dict] = []
    for t in trades:
        if _norm_symbol(t.get("symbol") or "") in dep:
            low.append(t)
        else:
            preferred.append(t)
    return preferred, low


def select_trades(
    trades: list[dict],
    state: dict,
    *,
    force: bool = False,
) -> list[dict]:
    """Aynı slot'ta 2+ coin kazandıysa 2 tweet; KAITO varsa diğer coinlere öncelik."""
    posted = _posted_keys(state)
    blocked_syms = set() if force else _recently_tweeted_symbols(state)
    excluded = set() if force else _excluded_symbols()

    candidates = [
        t for t in trades
        if t.get("win")
        and float(t.get("pnl_pct") or 0) > MIN_PNL_PCT
        and (force or t["_key"] not in posted)
        and _norm_symbol(t.get("symbol") or "") not in excluded
        and (force or _norm_symbol(t.get("symbol") or "") not in blocked_syms)
    ]
    if not candidates:
        return []

    by_slot: dict[str, list[dict]] = defaultdict(list)
    for t in candidates:
        by_slot[_slot_key(t)].append(t)

    for slot in sorted(by_slot.keys(), reverse=True):
        per_sym = _best_per_symbol(by_slot[slot])
        preferred, low = _split_by_priority(per_sym)

        if len(preferred) >= 2:
            return preferred[:MAX_PER_RUN]
        if len(preferred) == 1:
            return preferred[:1]
        if low:
            return low[:1]

    return []


def _record_post(state: dict, trade: dict) -> None:
    key = trade["_key"]
    keys = [k for k in (state.get("posted_keys") or []) if k != key]
    keys.append(key)
    state["posted_keys"] = keys[-POSTED_KEYS_MAX:]
    state["last_key"] = key

    sym = _norm_symbol(trade.get("symbol") or "")
    now = datetime.now(_TZ_TR).isoformat()
    rows = [r for r in (state.get("recent_symbols") or []) if isinstance(r, dict)]
    rows = [r for r in rows if _norm_symbol(r.get("symbol") or "") != sym]
    rows.append({"symbol": sym, "ts": now})
    state["recent_symbols"] = rows[-RECENT_SYMBOLS_MAX:]


def build_caption(trade: dict, *, lang: str = "en") -> str:
    symbol = _norm_symbol(trade.get("symbol") or "")
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


def _img_path(trade: dict) -> str:
    sym = _norm_symbol(trade.get("symbol") or "UNK")
    algo = str(trade.get("algo") or "x").replace("#", "")
    return os.path.join(OUT_DIR, f"trade_{sym}_{algo}.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Dedupe / cooldown / exclude atla")
    ap.add_argument("--lang", choices=("tr", "en"), default=os.environ.get("TWITTER_LANG", "en"))
    args = ap.parse_args()

    state = _load_state()
    trades = _recent_full_trades()
    picks = select_trades(trades, state, force=args.force)
    if not picks:
        print(
            f"Son {LOOKBACK_HOURS} saatte >{MIN_PNL_PCT:g}% kârlı yeni kazanan yok, tweet atlanıyor."
        )
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    ts_label = datetime.now(_TZ_TR).strftime("%d.%m.%Y %H:%M")

    for i, trade in enumerate(picks):
        sym = _norm_symbol(trade.get("symbol") or "")
        out_path = _img_path(trade)
        render_trade_card(trade, ts_label=ts_label, out_path=out_path, lang=args.lang)
        caption = build_caption(trade, lang=args.lang)
        print(f"--- [{i + 1}/{len(picks)}] {sym} ---")
        print(caption)
        print(f"Görsel: {out_path}")

        if args.dry_run:
            continue

        try:
            url = post_tweet_with_image(caption, out_path)
            print(f"Tweet atıldı: {url}")
            _record_post(state, trade)
            _save_state(state)
        except Exception as e:
            print(f"HATA ({sym}): {e}")
            sys.exit(1)

        if i + 1 < len(picks):
            time.sleep(TWEET_GAP_SEC)

    if args.dry_run:
        print(f"(dry-run) {len(picks)} kart üretildi, tweet atılmadı.")


if __name__ == "__main__":
    main()

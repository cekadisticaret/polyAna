#!/usr/bin/env python3
"""A2#05 Mean Reversion sinyal — 2.Poly/data/algo_signals_v2.json"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from bootstrap import DATA, init

ALGO_NUM = 5
ALGO_NAME = "Mean Reversion (Z-Score)"


def run() -> dict:
    init()
    from mean_reversion import SYMBOLS, fetch_klines, mean_reversion

    entry: dict = {sym: "NEUTRAL" for sym in SYMBOLS}
    entry["name"] = ALGO_NAME

    for sym, pair in SYMBOLS.items():
        try:
            kl = fetch_klines(pair, "1h", 200)
            entry[sym] = mean_reversion(kl) if kl else "NEUTRAL"
        except Exception as e:
            print(f"[2.Poly A2#05] {sym} fetch hata: {e}")
            entry[sym] = "NEUTRAL"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "2.Poly/signals.py",
        "algo_num": ALGO_NUM,
        "signals": {str(ALGO_NUM): entry},
    }
    out = DATA / "algo_signals_v2.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[2.Poly A2#05] sinyal yazıldı → {out}")
    for sym in SYMBOLS:
        print(f"  {sym}: {entry[sym]}")
    return payload


if __name__ == "__main__":
    run()

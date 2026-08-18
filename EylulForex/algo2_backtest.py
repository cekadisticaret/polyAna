"""Algoritma 2 — geçmiş 5m mumları üzerinde kapı simülasyonu.

Emir göndermez. Çıktı `data/algo2_backtest.json` — canlı katman 10 bunu okur.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from algo2_engine import _BACKTEST, evaluate, rows_to_df
from forex_data import get_xau_klines
from forex_signal import sr_levels


def run(bars: int = 160) -> dict:
    m5, src = get_xau_klines("5m", max(80, bars))
    m15, _ = get_xau_klines("15m", 80)
    h1, _ = get_xau_klines("1h", 80)
    if len(m5) < 50:
        out = {"ok": False, "n": 0, "error": "yetersiz mum", "src": src}
        _write(out)
        return out

    m15d, h1d = rows_to_df(m15), rows_to_df(h1)
    start = max(40, len(m5) - bars)
    hits = 0
    wins = 0
    last_open = None
    for i in range(start, len(m5) - 1):
        window = m5[: i + 1]
        levels = sr_levels(window[-80:] if len(window) > 80 else window)
        mid = float(window[-1]["close"])
        quote = {"mid": mid, "bid": mid - 0.15, "ask": mid + 0.15, "spread": 0.30, "src": "backtest"}
        packed = evaluate(
            rows_to_df(window), rows_to_df(window), m15d, h1d,
            quote=quote, levels=levels, persist=False,
        )
        if not packed.get("allow_entry"):
            continue
        direction = packed["direction"]
        nxt = m5[i + 1]
        fwd = float(nxt["close"]) - mid
        won = (fwd > 0) if direction == "UP" else (fwd < 0)
        hits += 1
        wins += int(won)
        last_open = {"i": i, "dir": direction, "px": mid, "won": won}

    wr = (100.0 * wins / hits) if hits else 0.0
    out = {
        "ok": True,
        "n": hits,
        "wins": wins,
        "wr": round(wr, 1),
        "bars": len(m5) - start,
        "src": src,
        "note": "sonraki 5m kapanış yönü (komisyonsuz)",
        "last": last_open,
    }
    _write(out)
    return out


def _write(out: dict) -> None:
    _BACKTEST.parent.mkdir(parents=True, exist_ok=True)
    _BACKTEST.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    res = run()
    print(json.dumps(res, ensure_ascii=False, indent=2))

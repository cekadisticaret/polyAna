"""
15M 114 SOL — 110 tabanlı filtreli sanal PM
============================================
110 15m sinyali + filtreler:
  · 1h A8 ve ALFA ile aynı yön (ters ise pas)
  · Gece 09:00–23:00 İST dışı pas
  · 3 ardışık kayıp → 4 slot mola

Sanal: PM_5M_114_REAL_ENABLED=false, $8/$10/$12 (WR).
Cron: */15 * * * * — +4 sn gecikme
Modlar: open / weekly / stats / recent [N]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analiz_114_15m_filter import analyze_114_15m, on_close_114, slot_filter_114
from poly_trader_15m_dir_runner import Dir15mTrader, Dir15mTraderConfig

_DIR = os.path.dirname(os.path.abspath(__file__))

CFG = Dir15mTraderConfig(
    label="15M 114",
    state_file=os.path.join(_DIR, "poly_trader_5m_sol_114_state.json"),
    history_file=os.path.join(_DIR, "poly_trader_5m_sol_114_history.json"),
    weekly_img="/tmp/poly_15m_sol_114_weekly.png",
    pm_live_env="PM_5M_114_REAL_ENABLED",
    analyze_fn=analyze_114_15m,
    open_delay_sec=4,
    stats_blurb="110 + 1h ALFA/A8 · gece 09-23 · 3 kayıp→4 slot mola",
    slot_filter=slot_filter_114,
    on_close=on_close_114,
)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    Dir15mTrader(CFG).cli(mode)

"""
15M 112 SOL — Jesse A8 @ 15m (sanal PM)
========================================
Algoritma: analiz_15m_a8 (Jesse GoldenCross). Bağımsız $300 state.

Sanal: PM_5M_112_REAL_ENABLED=false, işlem $8/$10/$12 (WR).
Cron: */15 * * * * — 15dk kapanış (:00/:15/:30/:45) +2 sn gecikme
Modlar: open (varsayılan close+open) / weekly / stats
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analiz_15m_a3a8_adapter import analyze_15m_a8
from poly_trader_15m_dir_runner import Dir15mTrader, Dir15mTraderConfig

_DIR = os.path.dirname(os.path.abspath(__file__))

CFG = Dir15mTraderConfig(
    label="15M 112 A8",
    state_file=os.path.join(_DIR, "poly_trader_5m_sol_112_state.json"),
    history_file=os.path.join(_DIR, "poly_trader_5m_sol_112_history.json"),
    weekly_img="/tmp/poly_15m_sol_112_weekly.png",
    pm_live_env="PM_5M_112_REAL_ENABLED",
    analyze_fn=analyze_15m_a8,
    open_delay_sec=2,
    stats_blurb="SOL only · Jesse A8 15m · $8/$10/$12 (WR)",
)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    Dir15mTrader(CFG).cli(mode)

#!/usr/bin/env python3
"""A2#03 Stochastic RSI LIVE — gerçek Polymarket $4–5–6.

Sanal A2#03 ayrı devam eder. Env: PM_A2_03_LIVE_ENABLED=true
Cron: close :02 · open :07
Dashboard: a2_03_live aç/kapa (varsayılan kapalı)
"""
from __future__ import annotations

from poly_a2_algo_live_core import A2LiveSpec, main

SPEC = A2LiveSpec(
    algo_num=3,
    algo_name="Stochastic RSI",
    label="A2#03 Stoch RSI Live",
    amount_system="a2_03",
    env_flag="PM_A2_03_LIVE_ENABLED",
    default_amount=5.0,
)

if __name__ == "__main__":
    main(SPEC)

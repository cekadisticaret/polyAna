#!/usr/bin/env python3
"""A2#04 Schaff Trend Cycle LIVE — gerçek Polymarket $4–5–6.

Sanal A2#04 ayrı devam eder. Env: PM_A2_04_LIVE_ENABLED=true
Cron: close :02 · open :06
Dashboard: a2_04_live aç/kapa (varsayılan kapalı)
"""
from __future__ import annotations

from poly_a2_algo_live_core import A2LiveSpec, main

SPEC = A2LiveSpec(
    algo_num=4,
    algo_name="Schaff Trend Cycle",
    label="A2#04 Schaff Live",
    amount_system="a2_04",
    env_flag="PM_A2_04_LIVE_ENABLED",
    default_amount=5.0,
)

if __name__ == "__main__":
    main(SPEC)

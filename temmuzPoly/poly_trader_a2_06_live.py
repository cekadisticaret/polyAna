#!/usr/bin/env python3
"""A2#06 Z-Score Mean Reversion LIVE — gerçek Polymarket $4–5–6.

Sanal A2#06 ayrı devam eder. Env: PM_A2_06_LIVE_ENABLED=true
Cron: close :02 · open :06
Dashboard: a2_06_live aç/kapa (varsayılan kapalı)
"""
from __future__ import annotations

from poly_a2_algo_live_core import A2LiveSpec, main

SPEC = A2LiveSpec(
    algo_num=6,
    algo_name="Z-Score Mean Reversion",
    label="A2#06 Z-Score MR Live",
    amount_system="a2_06",
    env_flag="PM_A2_06_LIVE_ENABLED",
    default_amount=5.0,
)

if __name__ == "__main__":
    main(SPEC)

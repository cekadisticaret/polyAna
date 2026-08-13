#!/usr/bin/env python3
"""A2#05 Mean Reversion LIVE — gerçek Polymarket $4–5–6.

Sanal A2#05 ayrı devam eder. Env: PM_A2_05_LIVE_ENABLED=true
Cron: close :02 · open :05+10sn (sanal :05:00 sonrası)
Dashboard: a2_05_live aç/kapa (varsayılan kapalı)
"""
from __future__ import annotations

from poly_a2_algo_live_core import A2LiveSpec, main

SPEC = A2LiveSpec(
    algo_num=5,
    algo_name="Mean Reversion (Z-Score)",
    label="A2#05 Mean Rev Live",
    amount_system="a2_05",
    env_flag="PM_A2_05_LIVE_ENABLED",
    default_amount=5.0,
)

if __name__ == "__main__":
    main(SPEC)

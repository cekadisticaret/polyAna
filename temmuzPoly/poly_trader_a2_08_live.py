#!/usr/bin/env python3
"""A2#08 Williams %R LIVE — gerçek Polymarket $4–5–6.

Sanal A2#08 ayrı devam eder. Env: PM_A2_08_LIVE_ENABLED=true
Cron: close :02 · open :05+10sn (sanal :05:00 sonrası)
Dashboard: a2_08_live aç/kapa
"""
from __future__ import annotations

from poly_a2_algo_live_core import A2LiveSpec, main

SPEC = A2LiveSpec(
    algo_num=8,
    algo_name="Williams %R",
    label="A2#08 Williams Live",
    amount_system="a2_08",
    env_flag="PM_A2_08_LIVE_ENABLED",
    default_amount=5.0,
)

if __name__ == "__main__":
    main(SPEC)

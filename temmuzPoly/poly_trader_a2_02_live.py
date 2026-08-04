#!/usr/bin/env python3
"""A2#02 RSI Diverjansı (14) Katı LIVE — gerçek Polymarket $4–5–6.

Sanal A2#02 ayrı devam eder. Env: PM_A2_02_LIVE_ENABLED=true
Cron: close :02 · open :06
Dashboard: a2_02_live aç/kapa
"""
from __future__ import annotations

from poly_a2_algo_live_core import A2LiveSpec, main

SPEC = A2LiveSpec(
    algo_num=2,
    algo_name="RSI Diverjansı (14) Katı",
    label="A2#02 RSI Div Live",
    amount_system="a2_02",
    env_flag="PM_A2_02_LIVE_ENABLED",
    default_amount=5.0,
)

if __name__ == "__main__":
    main(SPEC)

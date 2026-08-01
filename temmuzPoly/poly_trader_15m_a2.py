#!/usr/bin/env python3
"""15M A2 Top3 runner — Squeeze Mom / Supertrend / SuperTrend v2.

Modlar:
  open [309|316|317|all]  → close önceki + open yeni (*/15)
  weekly [309|316|317|all]

Örnek:
  python3 poly_trader_15m_a2.py open
  python3 poly_trader_15m_a2.py open 316
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poly_15m_a2_algo_trader_core import ALL_CONFIGS, CONFIG_BY_NUM, run_all, run_weekly


def _pick(arg: str | None):
    if not arg or arg == "all":
        return ALL_CONFIGS
    try:
        num = int(arg)
    except ValueError:
        print(f"Geçersiz numara: {arg} (309|316|317|all)")
        sys.exit(1)
    cfg = CONFIG_BY_NUM.get(num)
    if not cfg:
        print(f"#{num} yok — geçerli: 309, 316, 317")
        sys.exit(1)
    return [cfg]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    pick = sys.argv[2] if len(sys.argv) > 2 else "all"
    cfgs = _pick(pick)
    if mode in ("open", "run"):
        # 309 Live: sanal run_open içinde aynı sinyal/anda mirror ($3)
        run_all(cfgs)
    elif mode == "weekly":
        run_weekly(cfgs)
    else:
        print(f"Bilinmeyen mod: {mode}")
        sys.exit(1)

#!/usr/bin/env python3
"""Analiz 2 — 17 kârlı algo sanal trader runner.

Modlar:
  close [NN|all]  → önceki saat sonuçları (:01)
  open  [NN|all]  → yeni işlemler (:02; sinyal :01)
  weekly [NN|all] → haftalık özet

Örnek:
  python3 poly_trader_a2.py open
  python3 poly_trader_a2.py close 3
"""
from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poly_a2_algo_trader_core import ALL_CONFIGS, CONFIG_BY_NUM, run_mode


def _pick_configs(arg: str | None):
    if not arg or arg == "all":
        return ALL_CONFIGS
    try:
        num = int(arg)
    except ValueError:
        print(f"Geçersiz algo numarası: {arg}")
        sys.exit(1)
    cfg = CONFIG_BY_NUM.get(num)
    if not cfg:
        print(f"Algo #{num} bulunamadı (1-17)")
        sys.exit(1)
    return [cfg]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    pick = sys.argv[2] if len(sys.argv) > 2 else "all"
    cfgs = _pick_configs(pick)
    asyncio.run(run_mode(mode, cfgs))

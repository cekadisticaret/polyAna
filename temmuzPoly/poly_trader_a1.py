#!/usr/bin/env python3
"""ALGO1 — 34 yön algoritması, bağımsız sanal Poly defter.

A2 Top-17 ile aynı çekirdek (pm_sanal_fill · $24/36/48 · 7/24).
Sinyal: /tmp/algo_signals.json (algo_signals.py · :01 erken + :04:40).
Grid (#13) ve LSTM (#14) yok — yön üretmezler.
Gerçek PM yok (live_mirror=False). Manuel open yok — cron :01 close / :02 open.

  python3 poly_trader_a1.py close
  python3 poly_trader_a1.py open 11
  python3 poly_trader_a1.py weekly
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from algo_signals import ALGO_META, SKIP
from poly_a2_algo_trader_core import (
    A2Config,
    _load_history,
    _load_state,
    run_close,
    run_open,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
_A1_SIGNALS = "/tmp/algo_signals.json"


def _build_configs() -> list[A2Config]:
    out: list[A2Config] = []
    for num, name in ALGO_META:
        if num in SKIP:
            continue
        key = f"a1_{num:02d}"
        out.append(
            A2Config(
                algo_num=num,
                key=key,
                label=f"A1#{num:02d} {name}",
                algo_name=name,
                state_file=os.path.join(_DIR, f"poly_trader_{key}_state.json"),
                history_file=os.path.join(_DIR, f"poly_trader_{key}_history.json"),
                live_mirror=False,
                init_balance=1000.0,
                signals_file=_A1_SIGNALS,
            )
        )
    return out


ALL_CONFIGS = _build_configs()
CONFIG_BY_NUM = {c.algo_num: c for c in ALL_CONFIGS}
CONFIG_BY_KEY = {c.key: c for c in ALL_CONFIGS}
A1_KEYS = [c.key for c in ALL_CONFIGS]


def _pick_configs(arg: str | None) -> list[A2Config]:
    if not arg or arg == "all":
        return ALL_CONFIGS
    try:
        num = int(arg)
    except ValueError:
        print(f"Geçersiz algo numarası: {arg}")
        sys.exit(1)
    cfg = CONFIG_BY_NUM.get(num)
    if not cfg:
        print(f"A1#{num:02d} yok (SKIP={sorted(SKIP)})")
        sys.exit(1)
    return [cfg]


async def run_mode(mode: str, configs: list[A2Config] | None = None) -> None:
    """A2 run_mode kullanılmaz — TG başlığı ve ALFA yönlendirmesi A2'ye özel."""
    cfgs = configs or ALL_CONFIGS
    if mode == "close":
        for cfg in cfgs:
            await run_close(cfg, notify=False)
        return
    if mode == "open":
        for cfg in cfgs:
            await run_open(cfg, notify=False)
        return
    if mode == "weekly":
        ranked: list[tuple[float, str]] = []
        for cfg in cfgs:
            hist = _load_history(cfg)
            state = _load_state(cfg)
            total = len(hist)
            if not total:
                continue
            wins = sum(1 for t in hist if t.get("win"))
            wr = wins / total * 100
            pnl = state.get("total_pnl", 0.0)
            ranked.append((
                wr,
                f"  {cfg.label}: %{wr:.0f} ({wins}/{total})  "
                f"P&L {'+' if pnl >= 0 else ''}{pnl:.1f}$",
            ))
        ranked.sort(key=lambda x: x[0], reverse=True)
        print("A1 Top-34 haftalık")
        print("\n".join(r for _, r in ranked) if ranked else "Henüz veri yok.")
        return
    raise ValueError(f"Bilinmeyen mod: {mode}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "close"
    pick = sys.argv[2] if len(sys.argv) > 2 else "all"
    asyncio.run(run_mode(mode, _pick_configs(pick)))

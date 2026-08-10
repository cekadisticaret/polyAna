#!/usr/bin/env python3
"""Algoritma-islemler — açık pozisyonları kapat, bakiyeyi $300'e sıfırla, cron open'a bırak.

Kullanım:
  python3 algo_islemler_fresh_start.py           # close + reset $300
  python3 algo_islemler_fresh_start.py --reset-only   # sadece bakiye (close atla)

Not: open çalıştırmaz — :05 / :06 cron kendi açar.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ_TR = ZoneInfo("Europe/Istanbul")
_BALANCE = 300.0

ALGO_ISLEMLER_KEYS = [
    "analiz1", "analiz2",
    "analiz6", "analiz6_v2", "analiz6_v3", "analiz15",
    "b1_01", "b1_02", "b1_mum",
] + [f"a2_{i:02d}" for i in range(1, 18)]

_STANDALONE_CLOSE = [
    "analiz1", "analiz2", "analiz6", "analiz6_v2", "analiz6_v3", "analiz15",
    "b1_01", "b1_02", "b1_mum",
]


def _state_path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_{key}_state.json")


def _run_close_all() -> None:
    py = sys.executable
    for key in _STANDALONE_CLOSE:
        script = os.path.join(_DIR, f"poly_trader_{key}.py")
        if not os.path.isfile(script):
            continue
        print(f"[close] {key} …")
        subprocess.run([py, script, "close"], cwd=_DIR, check=False)
    a2 = os.path.join(_DIR, "poly_trader_a2.py")
    if os.path.isfile(a2):
        print("[close] A2 Top-17 (batch) …")
        subprocess.run([py, a2, "close", "all"], cwd=_DIR, check=False)


def _reset_balances(now_tr: datetime) -> tuple[int, int]:
    reset_n = 0
    cleared_open = 0
    note = "algoritma-islemler toplu reset $300 — geçmiş korundu"
    for key in ALGO_ISLEMLER_KEYS:
        path = _state_path(key)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            continue
        cleared_open += len(state.get("open_positions") or [])
        state["balance"] = _BALANCE
        state["open_positions"] = []
        state["total_pnl"] = 0.0
        state["balance_reset_at_tr"] = now_tr.isoformat()
        state["balance_reset_note"] = note
        state.pop("defer_cleared_at_tr", None)
        state.pop("defer_note", None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        reset_n += 1
        print(f"  reset {key} → ${_BALANCE:.0f}")
    return reset_n, cleared_open


def main() -> None:
    parser = argparse.ArgumentParser(description="Algoritma-islemler fresh start ($300)")
    parser.add_argument("--reset-only", action="store_true", help="close atla, sadece bakiye sıfırla")
    args = parser.parse_args()

    sys.path.insert(0, _DIR)
    from pm_balance_guard import clear_algo_islemler_open_after
    clear_algo_islemler_open_after(source="algo_islemler_fresh_start")

    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if not args.reset_only:
        _run_close_all()
    reset_n, cleared = _reset_balances(now_tr)
    nxt = (now_tr.hour + 1) % 24
    print(
        f"\n✓ {reset_n} defter → ${_BALANCE:.0f}  |  kalan açık temizlendi: {cleared}\n"
        f"  Sonraki otomatik open: ~{nxt:02d}:05–:06 İST (cron)\n"
        f"  Manuel open çalıştırılmadı."
    )


if __name__ == "__main__":
    main()

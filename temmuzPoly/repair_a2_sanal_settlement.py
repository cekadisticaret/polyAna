#!/usr/bin/env python3
"""A2 Poly sanal — post-reset geçmişi PM slot open/close ile yeniden hesapla."""
from __future__ import annotations

import json
import os
import re
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)
from pm_trader_helpers import SANAL_INITIAL_BALANCE, pm_sanal_settle_trade, pm_sanal_slot_candle

RESET_DEFAULT = "2026-08-01T08:59:43.520965+03:00"
_candle_cache: dict[tuple[str, str], tuple[float, float] | None] = {}


def _slot_key(symbol: str, entry_time_tr: str) -> tuple[str, str]:
    return symbol, entry_time_tr[:13]  # YYYY-MM-DDTHH


def _candle(symbol: str, entry_time_tr: str) -> tuple[float, float] | None:
    key = _slot_key(symbol, entry_time_tr)
    if key not in _candle_cache:
        _candle_cache[key] = pm_sanal_slot_candle(symbol, entry_time_tr)
        time.sleep(0.04)
    return _candle_cache[key]


def repair_key(key: str, *, dry_run: bool = False) -> dict:
    hist_path = os.path.join(_DIR, f"poly_trader_{key}_history.json")
    state_path = os.path.join(_DIR, f"poly_trader_{key}_state.json")
    with open(hist_path, encoding="utf-8") as f:
        history = json.load(f)
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)

    reset_at = state.get("balance_reset_at_tr") or RESET_DEFAULT
    changed = 0
    post_pnl = 0.0

    for t in history:
        et = t.get("entry_time_tr")
        xt = t.get("exit_time_tr") or ""
        if not et or xt < reset_at:
            continue
        sym = t.get("symbol")
        if not sym:
            continue
        candle = _candle(sym, et)
        if not candle:
            continue
        settled = pm_sanal_settle_trade(t, candle[0], candle[1])
        post_pnl += settled["pnl"]
        if (
            t.get("win") != settled["win"]
            or abs(float(t.get("pnl") or 0) - settled["pnl"]) > 0.02
            or t.get("actual_dir") != settled["actual_dir"]
        ):
            changed += 1
            if not dry_run:
                t["win"] = settled["win"]
                t["pnl"] = settled["pnl"]
                t["actual_dir"] = settled["actual_dir"]
                t["entry_price"] = settled["entry_price"]
                t["exit_price"] = settled["exit_price"]

    new_bal = round(SANAL_INITIAL_BALANCE + post_pnl, 2)
    old_bal = round(float(state.get("balance") or SANAL_INITIAL_BALANCE), 2)

    if not dry_run and changed:
        state["balance"] = new_bal
        state["total_pnl"] = round(new_bal - SANAL_INITIAL_BALANCE, 2)
        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
            f.write("\n")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return {
        "key": key,
        "changed": changed,
        "old_bal": old_bal,
        "new_bal": new_bal,
        "delta": round(new_bal - old_bal, 2),
    }


def main() -> None:
    dry = "--dry-run" in sys.argv
    keys = sorted(
        m.group(1)
        for f in os.listdir(_DIR)
        if (m := re.match(r"poly_trader_(a2_\d+)_history\.json$", f))
    )
    print(f"repair_a2_sanal_settlement {'(dry-run)' if dry else ''}")
    for key in keys:
        r = repair_key(key, dry_run=dry)
        if r["changed"] or abs(r["delta"]) > 0.01:
            print(
                f"  {r['key']}: {r['changed']} trade fixed | "
                f"${r['old_bal']:.2f} -> ${r['new_bal']:.2f} ({r['delta']:+.2f})"
            )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Algoritma-islemler tüm defterler — PM slot settlement + bakiye onarımı.

Yanlış kapanış (spot giriş vs anlık close) kullanan defterlerin geçmişini
pm_sanal_settle_trade ile yeniden hesaplar; bakiyeyi reset sonrası işlemlerden türetir.

Kullanım:
  python3 repair_algo_islemler_all.py           # onar
  python3 repair_algo_islemler_all.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)
sys.path.insert(0, os.path.join(_DIR, "..", "web"))

import poly_dashboard as dash
from pm_trader_helpers import pm_sanal_settle_trade, pm_sanal_slot_candle, pm_stake_fields

RESET_DEFAULT = "2026-08-01T08:59:43.520965+03:00"
_DEBIT_ON_OPEN = frozenset({"analiz2"})
_candle_cache: dict[tuple[str, str], tuple[float, float] | None] = {}


def _candle(sym: str, entry_time_tr: str) -> tuple[float, float] | None:
    key = (sym, entry_time_tr[:13])
    if key not in _candle_cache:
        _candle_cache[key] = pm_sanal_slot_candle(sym, entry_time_tr)
        time.sleep(0.03)
    return _candle_cache[key]


def _open_stake(state: dict) -> float:
    total = 0.0
    for p in state.get("open_positions") or []:
        spent, _, _ = pm_stake_fields(p)
        total += spent or float(p.get("amount") or 0)
    return round(total, 2)


def repair_key(key: str, *, dry_run: bool = False) -> dict:
    hpath = dash._trader_history_path(key)
    spath = dash._trader_state_path(key)
    init = float(dash._OVERVIEW_INIT_BAL.get(key) or 300)

    if not os.path.exists(hpath) and not os.path.exists(spath):
        return {"key": key, "skipped": True, "reason": "dosya yok"}

    history = json.load(open(hpath, encoding="utf-8")) if os.path.exists(hpath) else []
    state = json.load(open(spath, encoding="utf-8")) if os.path.exists(spath) else {
        "balance": init, "open_positions": [], "total_pnl": 0.0,
    }

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
            or abs(float(t.get("entry_price") or 0) - settled["entry_price"]) > 0.01
        ):
            changed += 1
            if not dry_run:
                t["win"] = settled["win"]
                t["pnl"] = settled["pnl"]
                t["actual_dir"] = settled["actual_dir"]
                t["entry_price"] = settled["entry_price"]
                t["exit_price"] = settled["exit_price"]

    post_pnl = round(post_pnl, 2)
    open_stake = _open_stake(state) if key in _DEBIT_ON_OPEN else 0.0
    new_bal = round(init + post_pnl - open_stake, 2)
    new_total = round(new_bal - init + open_stake, 2)  # total_pnl = kapalı net
    old_bal = round(float(state.get("balance") or init), 2)
    bal_fix = abs(old_bal - new_bal) > 0.05

    if not dry_run and (changed or bal_fix):
        state["balance"] = new_bal
        state["total_pnl"] = new_total
        with open(hpath, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
            f.write("\n")
        with open(spath, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return {
        "key": key,
        "changed": changed,
        "bal_fix": bal_fix,
        "old_bal": old_bal,
        "new_bal": new_bal,
        "delta": round(new_bal - old_bal, 2),
        "post_trades": sum(
            1 for t in history
            if (t.get("exit_time_tr") or "") >= reset_at
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    label = " (dry-run)" if args.dry_run else ""
    print(f"repair_algo_islemler_all{label}")
    fixed = 0
    for key in dash._ALGO_ISLEMLER_KEYS:
        r = repair_key(key, dry_run=args.dry_run)
        if r.get("skipped"):
            continue
        if r["changed"] or r["bal_fix"]:
            fixed += 1
            print(
                f"  {r['key']}: {r['changed']} trade | "
                f"bal ${r['old_bal']:.2f} → ${r['new_bal']:.2f} ({r['delta']:+.2f})"
            )
    print(f"✓ {fixed} defter onarıldı")


if __name__ == "__main__":
    main()

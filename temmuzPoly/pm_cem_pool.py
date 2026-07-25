"""CEM-ANALİZ ortak sanal havuz — A1 + A2 + 110 mirror ($300)."""
from __future__ import annotations

import json
import os
import fcntl
from contextlib import contextmanager

from pm_trader_helpers import pm_stake_fields, sanal_pnl, SANAL_INITIAL_BALANCE

_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_FILE = os.path.join(_DIR, "poly_trader_cem_pool_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_cem_history.json")
POOL_LOCK = POOL_FILE + ".lock"

POOL_ALGOS = ("a1", "a2", "110")
SOURCE_LABELS = {"a1": "A1", "a2": "A2", "110": "110"}


@contextmanager
def _pool_lock():
    os.makedirs(os.path.dirname(POOL_LOCK) or ".", exist_ok=True)
    with open(POOL_LOCK, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _default_pool() -> dict:
    return {
        "balance": float(SANAL_INITIAL_BALANCE),
        "total_pnl": 0.0,
        "open_positions": [],
        "initial_balance": float(SANAL_INITIAL_BALANCE),
    }


def _read_pool() -> dict:
    if not os.path.exists(POOL_FILE):
        return _default_pool()
    try:
        with open(POOL_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _default_pool()
    data.setdefault("balance", SANAL_INITIAL_BALANCE)
    data.setdefault("total_pnl", 0.0)
    data.setdefault("open_positions", [])
    return data


def _write_pool(data: dict) -> None:
    tmp = POOL_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, POOL_FILE)


def _stake(pos: dict) -> float:
    spent, _, _ = pm_stake_fields(pos)
    if spent > 0:
        return float(spent)
    return float(pos.get("amount") or pos.get("pm_spent") or 0)


def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: list) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def pool_view() -> dict:
    with _pool_lock():
        pool = _read_pool()
        return {
            "balance": round(float(pool["balance"]), 2),
            "total_pnl": round(float(pool.get("total_pnl", 0)), 2),
            "open_positions": list(pool.get("open_positions", [])),
        }


def _pos_id(algo: str, pos: dict) -> tuple:
    return (
        algo,
        pos.get("symbol"),
        pos.get("entry_time_tr"),
        pos.get("ts_period") or pos.get("ts_5m"),
    )


def has_position(algo: str, pos: dict) -> bool:
    pid = _pos_id(algo, pos)
    with _pool_lock():
        pool = _read_pool()
        for p in pool.get("open_positions", []):
            if _pos_id(p.get("pool_algo", ""), p) == pid:
                return True
    return False


def try_open(algo: str, pos: dict) -> bool:
    stake = _stake(pos)
    if stake <= 0:
        return False
    with _pool_lock():
        pool = _read_pool()
        if float(pool["balance"]) + 1e-9 < stake:
            return False
        cp = dict(pos)
        cp["pool_algo"] = algo
        pool["balance"] = round(float(pool["balance"]) - stake, 2)
        pool["open_positions"].append(cp)
        _write_pool(pool)
        return True


def settle(algo: str, pos: dict, win: bool) -> float:
    pnl = sanal_pnl(pos, win)
    _, size, _ = pm_stake_fields(pos)
    pid = _pos_id(algo, pos)
    with _pool_lock():
        pool = _read_pool()
        remaining = []
        removed = False
        for p in pool.get("open_positions", []):
            if not removed and _pos_id(p.get("pool_algo", ""), p) == pid:
                removed = True
                continue
            remaining.append(p)
        pool["open_positions"] = remaining
        if win and size > 0:
            pool["balance"] = round(float(pool["balance"]) + float(size), 2)
        pool["total_pnl"] = round(float(pool.get("total_pnl", 0)) + pnl, 2)
        _write_pool(pool)
    return pnl


def replace_algo_positions(algo: str, positions: list) -> None:
    with _pool_lock():
        pool = _read_pool()
        others = [p for p in pool.get("open_positions", []) if p.get("pool_algo") != algo]
        tagged = []
        for p in positions:
            cp = dict(p)
            cp["pool_algo"] = algo
            tagged.append(cp)
        pool["open_positions"] = others + tagged
        _write_pool(pool)


def positions_for(algos: tuple[str, ...]) -> list:
    with _pool_lock():
        pool = _read_pool()
        return [p for p in pool.get("open_positions", []) if p.get("pool_algo") in algos]


def pool_status() -> dict:
    with _pool_lock():
        pool = _read_pool()
        by_algo = {a: [] for a in POOL_ALGOS}
        for p in pool.get("open_positions", []):
            a = p.get("pool_algo")
            if a in by_algo:
                by_algo[a].append(p)
        at_risk = sum(_stake(p) for p in pool.get("open_positions", []))
        return {
            "balance": round(float(pool["balance"]), 2),
            "total_pnl": round(float(pool.get("total_pnl", 0)), 2),
            "initial_balance": float(pool.get("initial_balance", SANAL_INITIAL_BALANCE)),
            "at_risk": round(at_risk, 2),
            "open_total": len(pool.get("open_positions", [])),
            "by_algo": {a: len(v) for a, v in by_algo.items()},
            "positions": pool.get("open_positions", []),
        }


def reset_pool(balance: float | None = None) -> None:
    with _pool_lock():
        b = float(balance if balance is not None else SANAL_INITIAL_BALANCE)
        _write_pool({
            "balance": b,
            "total_pnl": 0.0,
            "open_positions": [],
            "initial_balance": b,
        })

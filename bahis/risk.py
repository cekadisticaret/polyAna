"""Kağıt kasa tavanı + circuit breaker. Emir yok.

Günlük %8 · haftalık %20 · drawdown %25. Durum `data/risk_state.json`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")
PATH = os.path.join(os.path.dirname(__file__), "data", "risk_state.json")
BANKROLL = 10000.0
MAX_DAILY = 0.08
MAX_WEEKLY = 0.20
MAX_DD = 0.25


def _now() -> datetime:
    return datetime.now(TR)


def _monday(d: datetime) -> str:
    return (d - timedelta(days=d.weekday())).date().isoformat()


def _empty() -> dict:
    n = _now()
    return {
        "bankroll": BANKROLL,
        "peak": BANKROLL,
        "daily_date": n.date().isoformat(),
        "daily_risk": 0.0,
        "week_start": _monday(n),
        "weekly_risk": 0.0,
        "halted": False,
        "halt_reason": "",
        "updated": None,
    }


def load() -> dict:
    if os.path.isfile(PATH):
        try:
            with open(PATH, encoding="utf-8") as f:
                st = json.load(f)
            if isinstance(st, dict):
                return {**_empty(), **st}
        except (OSError, json.JSONDecodeError):
            pass
    return _empty()


def save(st: dict) -> None:
    st["updated"] = _now().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def roll(st: dict | None = None) -> dict:
    st = dict(st or load())
    n = _now()
    today = n.date().isoformat()
    week = _monday(n)
    if st.get("daily_date") != today:
        st["daily_date"] = today
        st["daily_risk"] = 0.0
    if st.get("week_start") != week:
        st["week_start"] = week
        st["weekly_risk"] = 0.0
    bal = float(st.get("bankroll") or BANKROLL)
    peak = max(float(st.get("peak") or bal), bal)
    st["peak"] = peak
    dd = (peak - bal) / peak if peak else 0.0
    if dd >= MAX_DD:
        st["halted"] = True
        st["halt_reason"] = f"drawdown %{dd*100:.1f} ≥ %{int(MAX_DD*100)}"
    return st


def snapshot() -> dict:
    st = roll()
    bal = float(st["bankroll"])
    daily_left = max(0.0, bal * MAX_DAILY - float(st["daily_risk"]))
    weekly_left = max(0.0, bal * MAX_WEEKLY - float(st["weekly_risk"]))
    return {
        **st,
        "daily_left": round(daily_left, 2),
        "weekly_left": round(weekly_left, 2),
        "max_daily_pct": MAX_DAILY,
        "max_weekly_pct": MAX_WEEKLY,
        "max_dd_pct": MAX_DD,
        "orders": False,
    }


def allow(stake: float) -> tuple[bool, str, float]:
    st = roll()
    if st.get("halted"):
        return False, st.get("halt_reason") or "devre kesici", 0.0
    left = min(
        float(st["bankroll"]) * MAX_DAILY - float(st["daily_risk"]),
        float(st["bankroll"]) * MAX_WEEKLY - float(st["weekly_risk"]),
    )
    if left <= 0:
        return False, "günlük/haftalık risk tavanı", 0.0
    return True, "", round(min(float(stake), left), 2)


def record_stake(stake: float) -> dict:
    st = roll()
    st["daily_risk"] = round(float(st["daily_risk"]) + float(stake), 2)
    st["weekly_risk"] = round(float(st["weekly_risk"]) + float(stake), 2)
    save(st)
    return st


def record_pnl(pnl: float) -> dict:
    st = roll()
    st["bankroll"] = round(float(st["bankroll"]) + float(pnl), 2)
    st["peak"] = max(float(st["peak"]), st["bankroll"])
    st = roll(st)
    save(st)
    return st


def reset_halt() -> dict:
    st = roll()
    st["halted"] = False
    st["halt_reason"] = ""
    save(st)
    return st

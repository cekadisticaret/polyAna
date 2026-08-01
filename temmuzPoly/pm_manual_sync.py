"""Manuel PM — Polymarket activity → poly_trader_manual_state senkronu."""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from pm_poly_history import _fetch_activity, _slug_ts

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH = os.path.join(_DIR, "poly_trader_manual_state.json")
_INDEX_PATH = os.path.join(_DIR, "poly_trader_manual_orders.json")
_TZ_TR = ZoneInfo("Europe/Istanbul")

_DESK_5M = re.compile(r"^(btc|sol)-updown-5m-\d+$")
_DESK_15M = re.compile(r"^(btc|sol)-updown-15m-\d+$")
_DESK_1H = re.compile(r"^(bitcoin|solana|ethereum)-up-or-down-.+-et$")
_SYM_FROM_SLUG = {
    "btc": "BTCUSDT",
    "sol": "SOLUSDT",
    "bitcoin": "BTCUSDT",
    "solana": "SOLUSDT",
    "ethereum": "ETHUSDT",
}
_ALL_TRADER_KEYS = (
    "manual",
    "analiz5",
    "analiz2_live",
    "5m_sol_110",
)


def _desk_timeframe(slug: str) -> str | None:
    if _DESK_5M.match(slug or ""):
        return "5m"
    if _DESK_15M.match(slug or ""):
        return "15m"
    if _DESK_1H.match(slug or ""):
        return "1h"
    return None


def _symbol_from_slug(slug: str) -> str:
    head = (slug or "").split("-")[0].lower()
    return _SYM_FROM_SLUG.get(head, "SOLUSDT")


def _dir_from_outcome(outcome: str) -> str:
    o = (outcome or "").upper()
    if o in ("UP", "YES"):
        return "UP"
    if o in ("DOWN", "NO"):
        return "DOWN"
    return o or "?"


def _load_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_manual_order_index() -> set[str]:
    data = _load_json(_INDEX_PATH) or []
    return {
        str(x.get("pm_order_id"))
        for x in data
        if x.get("pm_order_id") and str(x.get("pm_order_id")) not in ("DRY_RUN", "")
    }


def register_manual_order(pos: dict) -> None:
    """İşlem masasından açılan emri indekse yaz (senkron için)."""
    oid = pos.get("pm_order_id")
    if not oid or str(oid) in ("DRY_RUN", ""):
        return
    data = _load_json(_INDEX_PATH) or []
    oid = str(oid)
    if any(str(x.get("pm_order_id")) == oid for x in data):
        return
    data.append({
        "pm_order_id": oid,
        "pm_slug": pos.get("pm_slug", ""),
        "symbol": pos.get("symbol", ""),
        "dir": pos.get("predicted_dir", ""),
        "registered_at": datetime.now(_TZ_TR).isoformat(),
    })
    data = data[-500:]
    with open(_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _collect_known_orders() -> tuple[set[str], set[str], set[str], set[str]]:
    """all_order_ids, manual_hist_ids, manual_closed_ids, manual_index_ids"""
    all_ids: set[str] = set()
    manual_hist_ids: set[str] = set()
    manual_closed: set[str] = set()

    for key in _ALL_TRADER_KEYS:
        hist = _load_json(os.path.join(_DIR, f"poly_trader_{key}_history.json")) or []
        for t in hist:
            oid = t.get("pm_order_id")
            if not oid or str(oid) in ("DRY_RUN", ""):
                continue
            oid = str(oid)
            all_ids.add(oid)
            if key == "manual":
                manual_hist_ids.add(oid)
                if t.get("win") is not None:
                    manual_closed.add(oid)
        state = _load_json(os.path.join(_DIR, f"poly_trader_{key}_state.json")) or {}
        for p in state.get("open_positions", []):
            oid = p.get("pm_order_id")
            if oid:
                all_ids.add(str(oid))

    return all_ids, manual_hist_ids, manual_closed, _load_manual_order_index()


def _leg_key(act: dict) -> tuple[str, str, str]:
    slug = act.get("slug") or act.get("eventSlug") or "?"
    outcome = act.get("outcome") or str(act.get("outcomeIndex", ""))
    return slug, outcome, _dir_from_outcome(outcome)


def _open_buy_rows(acts: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for a in acts:
        if a.get("type") not in ("TRADE", "REDEEM"):
            continue
        groups[_leg_key(a)].append(a)

    rows: list[dict] = []
    for key, items in groups.items():
        slug, _, direction = key
        if not _desk_timeframe(slug):
            continue
        items.sort(key=lambda x: x.get("timestamp", 0))
        buy_total = sum(
            float(a.get("usdcSize") or 0)
            for a in items if a.get("type") == "TRADE" and a.get("side") == "BUY"
        )
        out_total = sum(
            float(a.get("usdcSize") or 0)
            for a in items
            if a.get("type") == "TRADE" and a.get("side") == "SELL"
        )
        out_total += sum(float(a.get("usdcSize") or 0) for a in items if a.get("type") == "REDEEM")
        if buy_total <= 0 or buy_total <= out_total + 0.02:
            continue
        buys = [a for a in items if a.get("type") == "TRADE" and a.get("side") == "BUY"]
        buys.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        remaining = out_total
        for a in buys:
            sz = float(a.get("usdcSize") or 0)
            if remaining >= sz - 0.05:
                remaining -= sz
                continue
            rows.append({**a, "_slug": slug, "_direction": direction})
    rows.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return rows


def _pos_id(pos: dict) -> str:
    oid = pos.get("pm_order_id")
    if oid and str(oid) not in ("DRY_RUN", ""):
        return str(oid)
    slug = pos.get("pm_slug") or ""
    et = pos.get("entry_time_tr") or ""
    return f"{slug}:{et}"


def _activity_to_pos(act: dict) -> dict:
    slug = act.get("_slug") or act.get("slug") or ""
    direction = act.get("_direction") or _dir_from_outcome(act.get("outcome") or "")
    timeframe = _desk_timeframe(slug) or "15m"
    ts = int(act.get("timestamp") or time.time())
    entry_tr = datetime.fromtimestamp(ts, _TZ_TR)
    pos = {
        "symbol": _symbol_from_slug(slug),
        "predicted_dir": direction,
        "entry_price": 0.0,
        "amount": round(float(act.get("usdcSize") or 0), 2),
        "pm_spent": round(float(act.get("usdcSize") or 0), 2),
        "to_win": round(float(act.get("size") or 0), 4),
        "token_price": float(act.get("price") or 0),
        "entry_time_tr": entry_tr.isoformat(),
        "entry_dow": entry_tr.weekday(),
        "entry_hour_tr": entry_tr.hour,
        "entry_is_weekend": entry_tr.weekday() >= 5,
        "timeframe": timeframe,
        "pm_slug": slug,
        "pm_token_dir": direction,
        "pm_token_id": act.get("asset") or "",
        "pm_size": round(float(act.get("size") or 0), 4),
        "pm_entry_price": float(act.get("price") or 0),
        "pm_order_id": act.get("transactionHash") or "",
        "manual": True,
        "synced_from_chain": True,
    }
    if timeframe == "5m":
        ts_period = _slug_ts(slug) or ts
        pos["ts_period"] = ts_period
        pos["ts_5m"] = ts_period
        pos["entry_period_min"] = 5
    elif timeframe == "15m":
        ts_period = _slug_ts(slug) or ts
        pos["ts_period"] = ts_period
        pos["ts_5m"] = ts_period
        pos["entry_period_min"] = 15
    return pos


def _should_sync_buy(
    act: dict,
    *,
    oid: str,
    all_ids: set[str],
    manual_hist_ids: set[str],
    manual_index_ids: set[str],
    manual_closed: set[str],
    cutoff: float,
) -> bool:
    if oid in manual_closed:
        return False
    slug = act.get("_slug") or ""
    tf = _desk_timeframe(slug)
    ts = int(act.get("timestamp") or 0)

    if oid in manual_hist_ids or oid in manual_index_ids:
        return True

    if oid in all_ids or ts < cutoff:
        return False

    # 5/15dk: son 12 saat, bot kaydı yok — desk'ten açılmış olabilir
    if tf in ("5m", "15m"):
        return ts >= time.time() - 12 * 3600

    return False


def sync_manual_open_positions(
    *,
    max_age_hours: int = 48,
    activity_limit: int = 200,
    replace: bool = False,
) -> dict:
    """Zincirdeki açık manuel BUY'ları state'e yazar."""
    state = _load_json(_STATE_PATH) or {"balance": 0, "open_positions": [], "total_pnl": 0}
    open_positions: list[dict] = [] if replace else list(state.get("open_positions") or [])
    existing_ids = {_pos_id(p) for p in open_positions}

    all_ids, manual_hist_ids, manual_closed, manual_index_ids = _collect_known_orders()
    acts = _fetch_activity(limit=activity_limit)
    cutoff = time.time() - max_age_hours * 3600
    added: list[dict] = []
    skipped = 0

    for act in _open_buy_rows(acts):
        oid = str(act.get("transactionHash") or "")
        if not oid or oid in existing_ids:
            skipped += 1
            continue
        if not _should_sync_buy(
            act,
            oid=oid,
            all_ids=all_ids,
            manual_hist_ids=manual_hist_ids,
            manual_index_ids=manual_index_ids,
            manual_closed=manual_closed,
            cutoff=cutoff,
        ):
            skipped += 1
            continue

        pos = _activity_to_pos(act)
        open_positions.append(pos)
        existing_ids.add(_pos_id(pos))
        ts = int(act.get("timestamp") or 0)
        added.append({
            "order_id": oid,
            "slug": act.get("_slug") or "",
            "sym": pos["symbol"].replace("USDT", ""),
            "dir": pos["predicted_dir"],
            "spent": pos["pm_spent"],
            "time": datetime.fromtimestamp(ts, _TZ_TR).strftime("%Y-%m-%d %H:%M"),
        })

    state["open_positions"] = open_positions
    with open(_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "added": added,
        "added_count": len(added),
        "skipped": skipped,
        "open_count": len(open_positions),
    }

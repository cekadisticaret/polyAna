#!/usr/bin/env python3
"""Saatlik analiz/algo slot verilerini diske kaydet (15m yok).

Çıktılar:
  temmuzPoly/slot_data/latest.json
  temmuzPoly/slot_data/daily/YYYY-MM-DD.json
  temmuzPoly/slot_data/hourly/YYYY-MM-DD_HH.json
  temmuzPoly/slot_data/events.jsonl          # append-only kazanç/kayıp olayları
  temmuzPoly/slot_data/force_hot_latest.json # WR>%85 saatler

Cron: her saat :15 UTC (~:15+3 İST wall; close:02 sonrası)
  python3 temmuzPoly/slot_data_archive.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_DIR = Path(__file__).resolve().parent
_TZ = ZoneInfo("Europe/Istanbul")
_OUT = _DIR / "slot_data"
_DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

BOOKS: list[tuple[str, Path]] = [
    ("A1", _DIR / "poly_trader_analiz1_history.json"),
    ("A2", _DIR / "poly_trader_analiz2_history.json"),
    ("A4", _DIR / "poly_trader_analiz4_history.json"),
    ("A6", _DIR / "poly_trader_analiz6_history.json"),
    ("A10", _DIR / "poly_trader_analiz10_history.json"),
    ("A15", _DIR / "poly_trader_analiz15_history.json"),
]
for i in range(1, 18):
    BOOKS.append((f"#{i:02d}", _DIR / f"poly_trader_a2_{i:02d}_history.json"))

FORCE_WR = 85.0
MIN_TRADES_FORCE = 3


def _load_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("trades") or data.get("history") or []
    return []


def _parse_tr(t: dict) -> datetime | None:
    raw = t.get("entry_time_tr") or t.get("exit_time_tr")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ)
        return dt.astimezone(_TZ)
    except Exception:
        return None


def _pnl(t: dict) -> float:
    if t.get("pnl") is not None:
        try:
            return float(t["pnl"])
        except Exception:
            pass
    amt = float(t.get("amount") or t.get("pm_spent") or 0)
    spent = float(t.get("pm_spent") or amt or 0)
    size = float(t.get("pm_size") or 0)
    if t.get("win") and size and spent:
        return size - spent
    return amt if t.get("win") else -amt


def _slot_key(dow: int, hour: int) -> str:
    return f"{dow}_{hour:02d}"


def build_book_stats(history: list[dict], *, days: int | None = 7) -> dict:
    now = datetime.now(_TZ)
    cutoff = now - timedelta(days=days) if days is not None else None
    # hour-only aggregates + dow×hour
    by_hour: dict[int, dict[str, float]] = defaultdict(lambda: {"w": 0, "t": 0, "pnl": 0.0})
    by_slot: dict[str, dict[str, float]] = defaultdict(lambda: {"w": 0, "t": 0, "pnl": 0.0})
    events = []
    for t in history:
        dt = _parse_tr(t)
        if dt is None:
            continue
        if cutoff is not None and dt < cutoff:
            continue
        dow = t.get("entry_dow")
        hour = t.get("entry_hour_tr")
        if dow is None:
            dow = dt.weekday()
        if hour is None:
            hour = dt.hour
        dow, hour = int(dow), int(hour)
        won = bool(t.get("win"))
        pnl = _pnl(t)
        by_hour[hour]["t"] += 1
        by_hour[hour]["pnl"] += pnl
        if won:
            by_hour[hour]["w"] += 1
        sk = _slot_key(dow, hour)
        by_slot[sk]["t"] += 1
        by_slot[sk]["pnl"] += pnl
        if won:
            by_slot[sk]["w"] += 1
        events.append(
            {
                "entry_time_tr": dt.isoformat(),
                "dow": dow,
                "day": _DAYS[dow],
                "hour": hour,
                "win": won,
                "pnl": round(pnl, 4),
                "symbol": (t.get("symbol") or "").replace("USDT", ""),
                "amount": float(t.get("amount") or t.get("pm_spent") or 0),
            }
        )

    def _pack(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            t = int(v["t"])
            w = int(v["w"])
            out[str(k)] = {
                "w": w,
                "t": t,
                "wr": round(100.0 * w / t, 2) if t else 0.0,
                "pnl": round(float(v["pnl"]), 4),
            }
        return out

    hours = _pack(by_hour)
    slots = _pack(by_slot)
    force_hot = sorted(
        int(h)
        for h, v in hours.items()
        if v["t"] >= MIN_TRADES_FORCE and v["wr"] > FORCE_WR
    )
    total_t = sum(v["t"] for v in hours.values())
    total_w = sum(v["w"] for v in hours.values())
    total_pnl = sum(v["pnl"] for v in hours.values())
    return {
        "trades": total_t,
        "wins": total_w,
        "wr": round(100.0 * total_w / total_t, 2) if total_t else 0.0,
        "pnl": round(total_pnl, 4),
        "force_hot_hours": force_hot,
        "by_hour": hours,
        "by_dow_hour": slots,
        "events": events,
    }


def archive_once() -> dict:
    _OUT.mkdir(parents=True, exist_ok=True)
    (_OUT / "daily").mkdir(exist_ok=True)
    (_OUT / "hourly").mkdir(exist_ok=True)

    now = datetime.now(_TZ)
    snap = {
        "ts_tr": now.isoformat(),
        "tz": "Europe/Istanbul",
        "window_days": 7,
        "note": "saatlik A1/A2/A4/A6/A10/A15 + A2 Top17; 15m yok",
        "books": {},
        "winners_prev_hour": [],
    }

    prev_hour = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    winners_prev = []
    events_lines = []

    for lab, path in BOOKS:
        hist = _load_history(path)
        st7 = build_book_stats(hist, days=7)
        st30 = build_book_stats(hist, days=30)
        # slim events in book blob — keep counts; full events go to jsonl
        book_blob = {
            "history_file": path.name,
            "d7": {k: v for k, v in st7.items() if k != "events"},
            "d30": {k: v for k, v in st30.items() if k != "events"},
        }
        snap["books"][lab] = book_blob

        for ev in st7["events"]:
            # prev hour winners
            try:
                edt = datetime.fromisoformat(ev["entry_time_tr"])
            except Exception:
                continue
            if edt.replace(minute=0, second=0, microsecond=0) == prev_hour and ev["win"]:
                winners_prev.append({"book": lab, **ev})
            events_lines.append({"book": lab, **ev, "archived_at_tr": now.isoformat()})

    snap["winners_prev_hour"] = winners_prev
    snap["prev_hour_tr"] = prev_hour.isoformat()

    force_all = {
        lab: snap["books"][lab]["d7"]["force_hot_hours"]
        for lab in snap["books"]
        if snap["books"][lab]["d7"]["force_hot_hours"]
    }
    force_doc = {
        "ts_tr": now.isoformat(),
        "threshold_wr": FORCE_WR,
        "min_trades": MIN_TRADES_FORCE,
        "by_book_d7": force_all,
    }

    # write files
    latest = _OUT / "latest.json"
    daily = _OUT / "daily" / f"{now.strftime('%Y-%m-%d')}.json"
    hourly = _OUT / "hourly" / f"{now.strftime('%Y-%m-%d_%H')}.json"
    force_path = _OUT / "force_hot_latest.json"

    text = json.dumps(snap, ensure_ascii=False, indent=2)
    latest.write_text(text + "\n", encoding="utf-8")
    daily.write_text(text + "\n", encoding="utf-8")
    hourly.write_text(text + "\n", encoding="utf-8")
    force_path.write_text(json.dumps(force_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # append only NEW events (by entry_time+book+symbol) — dedupe via seen file
    seen_path = _OUT / ".seen_event_keys"
    seen: set[str] = set()
    if seen_path.is_file():
        seen = set(seen_path.read_text(encoding="utf-8").splitlines())
    new_keys = []
    with (_OUT / "events.jsonl").open("a", encoding="utf-8") as f:
        for ev in events_lines:
            key = f"{ev['book']}|{ev['entry_time_tr']}|{ev.get('symbol')}|{ev.get('win')}|{ev.get('pnl')}"
            if key in seen:
                continue
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            new_keys.append(key)
            seen.add(key)
    if new_keys:
        # keep seen file from exploding — last 50k keys
        keep = list(seen)[-50000:]
        seen_path.write_text("\n".join(keep) + "\n", encoding="utf-8")

    summary = {
        "ts_tr": now.isoformat(),
        "books": len(snap["books"]),
        "new_events": len(new_keys),
        "winners_prev_hour": len(winners_prev),
        "force_books": len(force_all),
        "paths": {
            "latest": str(latest),
            "daily": str(daily),
            "hourly": str(hourly),
            "force": str(force_path),
            "events": str(_OUT / "events.jsonl"),
        },
    }
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> None:
    archive_once()


if __name__ == "__main__":
    main()

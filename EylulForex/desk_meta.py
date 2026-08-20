"""Forex masa meta — başlangıç bakiyesi + ilk çalışma anı.

İşlem mantığına dokunmaz. Bir kez yazılır, sonra yalnız okunur.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Istanbul")
_PATH = Path(__file__).resolve().parent / "data" / "forex_desk_meta.json"


def _now() -> str:
    return datetime.now(_TZ).strftime("%Y.%m.%d %H:%M:%S")


def _norm(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        ts = float(v)
        if ts > 1e12:
            ts /= 1000.0
        if ts > 1e9:
            return datetime.fromtimestamp(ts, _TZ).strftime("%Y.%m.%d %H:%M:%S")
        return None
    s = str(v).strip()
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s[:19], fmt).replace(tzinfo=_TZ)
            return dt.strftime("%Y.%m.%d %H:%M:%S")
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ)
        return dt.astimezone(_TZ).strftime("%Y.%m.%d %H:%M:%S")
    except ValueError:
        pass
    if len(s) >= 16 and s[4] == ".":
        return s[:19]
    return None


def _from_hist(hist) -> str | None:
    times = []
    for t in hist or []:
        n = _norm((t or {}).get("open_time") or (t or {}).get("close_time"))
        if n:
            times.append(n)
    return min(times) if times else None


def _mtime(path) -> str | None:
    try:
        p = Path(path) if path else None
        if p and p.exists():
            return datetime.fromtimestamp(p.stat().st_mtime, _TZ).strftime("%Y.%m.%d %H:%M:%S")
    except OSError:
        pass
    return None


def _load() -> dict:
    if not _PATH.exists():
        return {}
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(rows: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_PATH)


def stamp(key: str, *, init=None, hist=None, positions=None, state_path=None) -> dict:
    key = str(key or "desk")
    rows = _load()
    cur = dict(rows.get(key) or {})
    dirty = False
    inferred = _from_hist(hist) or _from_hist(positions) or _mtime(state_path)
    started = cur.get("started_at")
    if not started:
        cur["started_at"] = inferred or _now()
        dirty = True
    elif inferred and inferred < started:
        cur["started_at"] = inferred
        dirty = True
    if cur.get("init_balance") is None and init is not None:
        try:
            cur["init_balance"] = round(float(init), 2)
            dirty = True
        except (TypeError, ValueError):
            pass
    if dirty:
        rows[key] = cur
        _save(rows)
    return cur


def attach(out: dict, key: str, *, hist=None, positions=None, state_path=None, init=None) -> dict:
    meta = stamp(
        key,
        init=init if init is not None else out.get("init_balance"),
        hist=hist,
        positions=positions if positions is not None else out.get("positions"),
        state_path=state_path,
    )
    if meta.get("init_balance") is not None:
        out["init_balance"] = meta["init_balance"]
    if meta.get("started_at"):
        out["started_at"] = meta["started_at"]
    return out

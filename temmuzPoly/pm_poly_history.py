"""Polymarket data-api — gerçek işlem geçmişi (activity → slug bazlı P&L)."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_DIR, "..", ".env")
_TZ_TR = ZoneInfo("Europe/Istanbul")
_DATA_API = "https://data-api.polymarket.com"

_CACHE: dict = {"ts": 0.0, "settled": [], "open": []}
_CACHE_TTL = 45


def _load_env() -> None:
    if not os.path.exists(_ENV_FILE):
        return
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _sym_from_title(title: str) -> str:
    t = (title or "").lower()
    if "solana" in t or " sol " in t:
        return "SOL"
    if "bitcoin" in t or " btc" in t:
        return "BTC"
    if "ethereum" in t or " eth" in t:
        return "ETH"
    return "?"


def _dir_from_outcome(outcome: str) -> str:
    o = (outcome or "").upper()
    if o in ("UP", "YES"):
        return "UP"
    if o in ("DOWN", "NO"):
        return "DOWN"
    return o or "?"


def _fetch_activity(limit: int = 150) -> list[dict]:
    _load_env()
    funder = os.getenv("POLY_FUNDER", "")
    if not funder:
        return []
    url = f"{_DATA_API}/activity?user={funder}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    return data if isinstance(data, list) else []


def _slug_ts(slug: str) -> int | None:
    m = re.search(r"-(\d{9,})$", slug or "")
    return int(m.group(1)) if m else None


def build_slug_label_index(history_loaders: list) -> dict[str, str]:
    """history_loaders: [(label, load_history_fn), ...]"""
    index: dict[str, str] = {}
    for label, loader in history_loaders:
        try:
            hist = loader()
        except Exception:
            continue
        for t in hist or []:
            slug = t.get("pm_slug")
            if slug:
                index[slug] = label
    return index


def _match_label(slug: str, end_ts: int, index: dict[str, str]) -> str:
    if slug in index:
        return index[slug]
    ts = _slug_ts(slug)
    if ts:
        for s, label in index.items():
            if _slug_ts(s) == ts:
                return label
    return "PM"


def _group_activity(acts: list[dict]) -> tuple[list[dict], list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in acts:
        if a.get("type") not in ("TRADE", "REDEEM"):
            continue
        slug = a.get("slug") or a.get("eventSlug") or a.get("conditionId") or "?"
        groups[slug].append(a)

    settled: list[dict] = []
    open_rounds: list[dict] = []
    for slug, items in groups.items():
        items.sort(key=lambda x: x.get("timestamp", 0))
        buys = [a for a in items if a.get("type") == "TRADE" and a.get("side") == "BUY"]
        buy = sum(float(a.get("usdcSize") or 0) for a in buys)
        sell = sum(float(a.get("usdcSize") or 0) for a in items
                   if a.get("type") == "TRADE" and a.get("side") == "SELL")
        redeem = sum(float(a.get("usdcSize") or 0) for a in items if a.get("type") == "REDEEM")
        out = sell + redeem
        if buy <= 0:
            continue
        title = items[0].get("title") or slug
        outcome = items[0].get("outcome") or ""
        base = {
            "slug": slug,
            "sym": _sym_from_title(title),
            "dir": _dir_from_outcome(outcome),
            "spent": round(buy, 2),
            "title": title,
        }
        if out <= 0:
            act_ts = max(int(a.get("timestamp") or 0) for a in buys) if buys else 0
            open_rounds.append({
                **base,
                "act_ts": act_ts,
                "time": datetime.fromtimestamp(act_ts, _TZ_TR).strftime("%Y-%m-%d %H:%M"),
            })
            continue
        pnl = round(out - buy, 2)
        end_ts = int(items[-1].get("timestamp") or 0)
        settled.append({
            **base,
            "win": pnl >= 0,
            "pnl": pnl,
            "end_ts": end_ts,
            "time": datetime.fromtimestamp(end_ts, _TZ_TR).strftime("%Y-%m-%d %H:%M"),
        })

    settled.sort(key=lambda x: x["end_ts"], reverse=True)
    open_rounds.sort(key=lambda x: x["act_ts"], reverse=True)
    return settled, open_rounds


def _refresh_cache(limit: int, use_cache: bool) -> tuple[list[dict], list[dict]]:
    now = time.time()
    if use_cache and _CACHE["settled"] and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["settled"], _CACHE["open"]
    acts = _fetch_activity(limit=max(limit * 8, 120))
    settled, open_rounds = _group_activity(acts)
    _CACHE["ts"] = now
    _CACHE["settled"] = settled
    _CACHE["open"] = open_rounds
    return settled, open_rounds


def _format_trade_row(r: dict, slug_labels: dict[str, str], ts_key: str, pending: bool) -> dict:
    ts = int(r.get(ts_key) or 0)
    row = {
        "sym": r["sym"],
        "dir": r["dir"],
        "spent": r["spent"],
        "time": r["time"],
        "analiz": _match_label(r["slug"], ts, slug_labels),
        "source": "polymarket",
        "pending": pending,
        "slug": r.get("slug") or "",
    }
    if pending:
        row["pnl"] = None
    else:
        row["win"] = r["win"]
        row["pnl"] = r["pnl"]
    return row


def get_recent_pm_trades(
    limit: int = 20,
    slug_labels: dict[str, str] | None = None,
    use_cache: bool = True,
) -> list[dict]:
    settled, _ = _refresh_cache(limit, use_cache)
    slug_labels = slug_labels or {}
    return [
        _format_trade_row(r, slug_labels, "end_ts", pending=False)
        for r in settled[:limit]
    ]


def get_open_pm_trades(
    limit: int = 10,
    slug_labels: dict[str, str] | None = None,
    use_cache: bool = True,
) -> list[dict]:
    _, open_rounds = _refresh_cache(limit, use_cache)
    slug_labels = slug_labels or {}
    return [
        _format_trade_row(r, slug_labels, "act_ts", pending=True)
        for r in open_rounds[:limit]
    ]

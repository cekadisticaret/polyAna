"""Bitmiş maç + tahmin isabeti. Kaynak `data/results_book.json`. Emir yok."""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from bahis.league import team_info
from bahis.leagues_cfg import current_league, get as get_league, set_league

TR = ZoneInfo("Europe/Istanbul")
BOOK = os.path.join(os.path.dirname(__file__), "data", "results_book.json")


def load() -> dict:
    if not os.path.isfile(BOOK):
        return {"updated": None, "src": [], "matches": {}, "stats": {}}
    try:
        with open(BOOK, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"updated": None, "src": [], "matches": {}, "stats": {}}


def grade_of(mid: str) -> dict | None:
    row = (load().get("matches") or {}).get(mid)
    if not row:
        return None
    return row


def _pub(row: dict) -> dict:
    h = team_info(row.get("home") or "")
    a = team_info(row.get("away") or "")
    return {
        **row,
        "home": h if isinstance(row.get("home"), str) else (row.get("home") or h),
        "away": a if isinstance(row.get("away"), str) else (row.get("away") or a),
    }


def finished(limit: int = 40, league: str | None = None) -> dict:
    lid = set_league(league) if league else current_league()
    pack = load()
    rows = list((pack.get("matches") or {}).values())
    rows = [r for r in rows if (r.get("league") or "tr") == lid]
    done = [r for r in rows if r.get("played") and r.get("hg") is not None]
    done.sort(key=lambda r: r.get("kickoff") or "", reverse=True)
    graded = [r for r in done if r.get("hit") is not None]
    hits = sum(1 for r in graded if r.get("hit"))
    return {
        "ok": True,
        "league": get_league(lid)["name"],
        "league_id": lid,
        "updated": pack.get("updated"),
        "src": pack.get("src") or [],
        "n": len(done),
        "graded_n": len(graded),
        "hits": hits,
        "wr": round(hits / len(graded) * 100, 1) if graded else None,
        "clv": pack.get("clv") or {},
        "matches": [_pub(r) for r in done[:limit]],
        "note": "Ensemble 1X2 · maç öncesi kilit · CLV kapanış. Kupon açılmaz.",
    }

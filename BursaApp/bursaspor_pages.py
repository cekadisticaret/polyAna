"""Bursaspor web + mobil API veri paketi."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ = ZoneInfo("Europe/Istanbul")


def _read_json(path: str, default: Any):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _match_item(m, *, now: datetime) -> dict:
    played = m.home_score is not None and m.away_score is not None
    kickoff = m.kickoff_at
    if kickoff and kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=_TZ)
    return {
        "id": m.id,
        "week": m.week,
        "competition": m.competition,
        "kickoff_at": m.kickoff_at.strftime("%d.%m.%Y %H:%M") if m.kickoff_at else "",
        "kickoff_date": m.kickoff_at.strftime("%d.%m.%Y") if m.kickoff_at else "",
        "kickoff_time": m.kickoff_at.strftime("%H:%M") if m.kickoff_at else "",
        "kickoff_raw": m.kickoff_at.isoformat() if m.kickoff_at else None,
        "home_team": m.home_team,
        "away_team": m.away_team,
        "home_score": m.home_score,
        "away_score": m.away_score,
        "venue": m.venue,
        "is_home": m.is_home,
        "ticket_price": m.ticket_price,
        "ticket_url": m.ticket_url,
        "status": m.status,
        "note": m.note,
        "played": played,
        "kickoff_ts": kickoff.timestamp() if kickoff else None,
    }


def build_bursaspor_payload(db) -> dict:
    """Web /bursaspor ve mobil API için ortak veri."""
    from models import SportMatch
    from news_pages import load_bursaspor_videos

    now = datetime.now(_TZ)
    rows = (
        db.query(SportMatch)
        .filter(SportMatch.club == "bursaspor", SportMatch.season == "2026-27")
        .order_by(SportMatch.week.asc().nullslast(), SportMatch.kickoff_at.asc().nullslast())
        .all()
    )

    matches: list[dict] = []
    next_match = None
    upcoming: list[dict] = []
    played_items: list[dict] = []

    for m in rows:
        item = _match_item(m, now=now)
        item.pop("kickoff_ts", None)
        matches.append(item)
        if item["played"]:
            played_items.append(item)
        elif m.kickoff_at:
            kickoff = m.kickoff_at
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=_TZ)
            if next_match is None and kickoff >= now:
                next_match = item
            if len(upcoming) < 8 and kickoff >= now:
                upcoming.append(item)

    recent = list(reversed(played_items[-3:]))

    standings = _read_json(os.path.join(_DIR, "data", "bursaspor_standings.json"), [])
    if not isinstance(standings, list):
        standings = []
    bs_row = next((r for r in standings if "Bursaspor" in (r.get("team") or "")), None)

    feed = _read_json(os.path.join(_DIR, "data", "bursaspor_feed.json"), {})
    if not isinstance(feed, dict):
        feed = {}
    desk = feed.get("desk") or {}

    if not next_match and desk.get("next_match"):
        nm = desk["next_match"]
        next_match = {
            "home_team": nm.get("home") or "",
            "away_team": nm.get("away") or "",
            "kickoff_at": nm.get("kickoff") or "",
            "kickoff_date": (nm.get("kickoff") or "").split(" ")[0],
            "kickoff_time": (nm.get("kickoff") or "").split(" ")[-1] if nm.get("kickoff") else "",
            "venue": nm.get("venue") or "",
            "is_home": nm.get("is_home"),
            "ticket_url": "https://www.bursaspor.org.tr/",
            "played": False,
        }

    hero_bg = "/static/cache/bursaspor/cover-1.jpg"
    pool = _read_json(os.path.join(_DIR, "static", "cache", "bursaspor", "manifest.json"), [])
    if isinstance(pool, list) and pool:
        hero_bg = pool[0]

    videos = []
    for v in load_bursaspor_videos(limit=6):
        videos.append(
            {
                "id": v.get("id"),
                "title": v.get("title"),
                "channel": v.get("channel"),
                "topic": v.get("topic"),
                "published_at": v.get("published_at"),
                "date_label": v.get("date_label"),
                "watch_url": v.get("watch_url"),
                "thumb": v.get("thumb"),
            }
        )

    news = []
    for n in feed.get("news") or []:
        if not isinstance(n, dict):
            continue
        news.append(
            {
                "id": n.get("id"),
                "title": n.get("title"),
                "blurb": n.get("blurb"),
                "published_at": n.get("published_at"),
                "source": n.get("source"),
                "topic": n.get("topic") or "genel",
                "url": n.get("url"),
                "img_url": n.get("img_url"),
            }
        )

    return {
        "generated_at": feed.get("generated_at") or "",
        "disclaimer": feed.get("disclaimer") or "",
        "hero_bg": hero_bg,
        "desk": desk,
        "news": news,
        "standings": standings,
        "bs_row": bs_row,
        "matches": matches,
        "upcoming": upcoming,
        "recent": recent,
        "next_match": next_match,
        "videos": videos,
        "league": "Trendyol 1. Lig",
    }

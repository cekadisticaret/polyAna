"""Ana sayfa ve API için mekan sayaçları."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import Place

_DIR = os.path.dirname(os.path.abspath(__file__))
NIGHTLY_LAST = "/tmp/bursaapp_nightly_last.json"


def _read_nightly() -> dict:
    try:
        return json.load(open(NIGHTLY_LAST, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def home_stats(db: Session) -> dict:
    approved = db.query(Place).filter(Place.status == "approved")
    place_count = approved.count()
    visit_count = approved.filter(Place.category == "visit").count()
    nightly = _read_nightly()
    new_last = int(nightly.get("new") or 0)
    since = datetime.utcnow() - timedelta(days=7)
    new_week = (
        db.query(Place)
        .filter(Place.status == "approved", Place.created_at >= since)
        .count()
    )
    synced = nightly.get("ended_utc") or nightly.get("started_utc") or ""
    return {
        "place_count": place_count,
        "visit_count": visit_count,
        "places_new_last_night": new_last,
        "places_new_week": new_week,
        "places_synced_at": synced,
    }

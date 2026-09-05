"""Admin dashboard grafik verisi."""
from __future__ import annotations

from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo

    _IST = ZoneInfo("Europe/Istanbul")
except Exception:  # pragma: no cover
    from datetime import timezone

    _IST = timezone(timedelta(hours=3))

from catalog import CAT_BY_KEY
from models import ActivityLog

_WD_TR = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


def _fmt_day(day: str) -> str:
    parts = (day or "").split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}"
    return day


def _ist_day_bounds_utc(d):
    from datetime import time, timezone

    start = datetime.combine(d, time.min, tzinfo=_IST)
    end = start + timedelta(days=1)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def login_stats(db, *, days: int = 14) -> dict:
    """Günlük üye giriş sayıları — İstanbul günü."""
    labels: list[str] = []
    series: list[int] = []
    rows: list[dict] = []
    today = datetime.now(_IST).date()
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        start, end = _ist_day_bounds_utc(d)
        cnt = (
            db.query(ActivityLog)
            .filter(
                ActivityLog.kind == "login",
                ActivityLog.created_at >= start,
                ActivityLog.created_at < end,
            )
            .count()
        )
        labels.append(d.strftime("%d.%m"))
        series.append(cnt)
        rows.append(
            {
                "iso": d.isoformat(),
                "label": d.strftime("%d.%m.%Y"),
                "weekday": _WD_TR[d.weekday()],
                "count": cnt,
            }
        )
    return {
        "labels": labels,
        "series": series,
        "rows": list(reversed(rows)),
        "today": series[-1] if series else 0,
        "yesterday": series[-2] if len(series) >= 2 else 0,
        "total": sum(series),
        "total_7d": sum(series[-7:]),
        "days": days,
    }


def _activity_series(db, *, days: int = 7) -> dict:
    labels: list[str] = []
    register: list[int] = []
    login: list[int] = []
    submit: list[int] = []
    today = datetime.now(_IST).date()
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        start, end = _ist_day_bounds_utc(d)
        labels.append(d.strftime("%d.%m"))
        register.append(
            db.query(ActivityLog)
            .filter(
                ActivityLog.kind == "register",
                ActivityLog.created_at >= start,
                ActivityLog.created_at < end,
            )
            .count()
        )
        login.append(
            db.query(ActivityLog)
            .filter(
                ActivityLog.kind == "login",
                ActivityLog.created_at >= start,
                ActivityLog.created_at < end,
            )
            .count()
        )
        submit.append(
            db.query(ActivityLog)
            .filter(
                ActivityLog.kind == "place_submit",
                ActivityLog.created_at >= start,
                ActivityLog.created_at < end,
            )
            .count()
        )
    return {
        "labels": labels,
        "register": register,
        "login": login,
        "submit": submit,
    }


def build_dashboard_charts(db, *, traffic, page_traffic, by_cat, badges) -> dict:
    series = (traffic or {}).get("series") or []
    traffic_chart = {
        "labels": [_fmt_day(s["day"]) for s in series],
        "visitors": [int(s.get("visitors") or 0) for s in series],
        "pageviews": [int(s.get("pageviews") or 0) for s in series],
    }

    cat_sorted = sorted(by_cat or [], key=lambda x: -(x[1] or 0))[:14]
    categories_chart = {
        "labels": [
            CAT_BY_KEY.get(cat, {}).get("label", cat or "?") for cat, _ in cat_sorted
        ],
        "series": [int(n or 0) for _, n in cat_sorted],
    }

    tops = ((page_traffic or {}).get("period_pages") or [])[:10]
    top_pages_chart = {
        "labels": [(p.get("label") or p.get("path") or "?")[:36] for p in tops],
        "series": [int(p.get("pageviews") or 0) for p in tops],
    }

    moderation_chart = {
        "labels": [
            "Yer",
            "Foto",
            "Yorum",
            "Gönderi",
            "Ziyaret notu",
            "İşletme talebi",
            "Kampanya",
        ],
        "series": [
            int(badges.get("pending_places") or 0),
            int(badges.get("pending_photos") or 0),
            int(badges.get("pending_reviews") or 0),
            int(badges.get("pending_posts") or 0),
            int(badges.get("pending_visit_notes") or 0),
            int(badges.get("pending_claims") or 0),
            int(badges.get("pending_campaigns") or 0),
        ],
    }

    return {
        "traffic": traffic_chart,
        "categories": categories_chart,
        "top_pages": top_pages_chart,
        "activity": _activity_series(db, days=7),
        "logins": login_stats(db, days=14),
        "moderation": moderation_chart,
    }
